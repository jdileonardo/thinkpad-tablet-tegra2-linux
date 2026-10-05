// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * N-Trig DuoSense SPI transport for the ThinkPad Tablet Indigo.
 * Protocol and board power sequence derived from N-Trig's 2011 GPL driver
 * in the pinned Lenovo/Compal Android kernel. No calibration or DFU writes.
 */
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/input.h>
#include <linux/input/mt.h>
#include <linux/input/touchscreen.h>
#include <linux/interrupt.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/spi/spi.h>
#include <linux/unaligned.h>
#include <linux/workqueue.h>

#define NTRIG_G3 136
#define NTRIG_G4 264
#define NTRIG_CONTACTS 10
#define NTRIG_MAX_MSG 264

struct ntrig {
	struct spi_device *spi;
	struct input_dev *touch, *pen;
	struct touchscreen_properties touch_props, pen_props;
	struct gpio_desc *power, *enable, *ready;
	struct mutex lock;
	struct delayed_work poll;
	bool stopping, irq_masked;
	unsigned int transfer_len, prefix, have, expected, ticks;
	u64 transfers, packets, invalid, mt_reports, pen_reports, errors;
	u16 last_x, last_y, last_pressure;
	u8 last_flags, last[32];
	u8 frame[NTRIG_MAX_MSG];
	u8 tx[NTRIG_G4] __aligned(4);
	u8 rx[NTRIG_G4] __aligned(4);
};

static void ntrig_mt(struct ntrig *n, const u8 *p, unsigned int size, bool g4)
{
	unsigned int max = g4 ? 10 : 6;
	unsigned int count, i;

	/* report-id, frame-counter, fixed finger array, then contact count */
	if (size < 3 + max * 15 + 1)
		goto invalid;
	count = p[3 + max * 15];
	if (count > max)
		goto invalid;
	for (i = 0; i < count; i++) {
		const u8 *f = p + 3 + i * 15;
		unsigned int key = get_unaligned_le16(f + 1);
		/* Raw SPI confidence is 1 while present; stock TrackLib inverted it. */
		bool active = f[11] && !f[13];
		int slot = input_mt_get_slot_by_key(n->touch, key);

		if (slot < 0)
			continue;
		input_mt_slot(n->touch, slot);
		input_mt_report_slot_state(n->touch, MT_TOOL_FINGER, active);
		if (active) {
			u16 x = get_unaligned_le16(f + 3);
			u16 y = get_unaligned_le16(f + 5);
			u16 dx = get_unaligned_le16(f + 7);
			u16 dy = get_unaligned_le16(f + 9);
			touchscreen_report_pos(n->touch, &n->touch_props, x, y, true);
			input_report_abs(n->touch, ABS_MT_TOUCH_MAJOR, max(dx, dy));
			input_report_abs(n->touch, ABS_MT_TOUCH_MINOR, min(dx, dy));
		}
	}
	input_mt_sync_frame(n->touch);
	input_sync(n->touch);
	n->mt_reports++;
	return;
invalid:
	n->invalid++;
}

static void ntrig_pen(struct ntrig *n, const u8 *p, unsigned int size)
{
	bool in_range, eraser;
	u8 flags;
	u16 x, y, pressure;

	if (size < 9) {
		n->invalid++;
		return;
	}
	flags = p[1];
	x = get_unaligned_le16(p + 2);
	y = get_unaligned_le16(p + 4);
	pressure = get_unaligned_le16(p + 6);
	in_range = flags & BIT(0);
	eraser = flags & (BIT(3) | BIT(4));
	input_report_key(n->pen, BTN_TOUCH, in_range && (flags & (BIT(1) | BIT(4))));
	input_report_key(n->pen, BTN_TOOL_PEN, in_range && !eraser);
	input_report_key(n->pen, BTN_TOOL_RUBBER, in_range && eraser);
	input_report_key(n->pen, BTN_STYLUS, in_range && (flags & BIT(2)));
	touchscreen_report_pos(n->pen, &n->pen_props, x, y, false);
	input_report_abs(n->pen, ABS_PRESSURE, in_range ? min_t(u16, pressure, 255) : 0);
	input_report_abs(n->pen, ABS_DISTANCE, in_range && !(flags & (BIT(1) | BIT(4))));
	input_sync(n->pen);
	n->last_x = x;
	n->last_y = y;
	n->last_pressure = pressure;
	n->last_flags = flags;
	n->pen_reports++;
}

static void ntrig_packet(struct ntrig *n)
{
	const u8 *f = n->frame;
	unsigned int size = n->expected - 6;

	n->packets++;
	memset(n->last, 0, sizeof(n->last));
	memcpy(n->last, f, min_t(unsigned int, n->expected, sizeof(n->last)));
	if (f[3] & 0x80)
		n->transfer_len = NTRIG_G4;
	if (f[0] != 1)
		return; /* Control replies are counted, never interpreted as input. */
	if (f[4] == 1 && f[5] == 3)
		ntrig_mt(n, f + 6, size, f[3] & 0x80);
	else if (f[4] == 3 && f[5] == 1)
		ntrig_pen(n, f + 6, size);
	else if (f[4] == 2 && f[5] == 2 && size >= 10) {
		const u8 *p = f + 6;
		bool active = p[1] & BIT(1);
		input_mt_slot(n->touch, 0);
		input_mt_report_slot_state(n->touch, MT_TOOL_FINGER, active);
		if (active)
			touchscreen_report_pos(n->touch, &n->touch_props,
				get_unaligned_le16(p + 2), get_unaligned_le16(p + 4), true);
		input_mt_sync_frame(n->touch);
		input_sync(n->touch);
		n->mt_reports++;
	}
}

/* Streaming parser: messages and even the prefix can straddle SPI transfers. */
static void ntrig_feed(struct ntrig *n, const u8 *buf, unsigned int len)
{
	static const u8 signature[] = { 0xff, 0xff, 0xff, 0xff, 0xa5, 0x5a, 0xe7, 0x7e };
	unsigned int i;

	for (i = 0; i < len; i++) {
		u8 b = buf[i];
		if (n->prefix < sizeof(signature)) {
			if (b == signature[n->prefix])
				n->prefix++;
			else if (b == 0xff)
				n->prefix = n->prefix <= 4 ? min(n->prefix + 1, 4U) : 1;
			else
				n->prefix = 0;
			continue;
		}
		n->frame[n->have++] = b;
		if (n->have == 3) {
			n->expected = get_unaligned_le16(n->frame + 1);
			if (n->expected < 6 || n->expected > sizeof(n->frame)) {
				n->invalid++;
				n->prefix = n->have = n->expected = 0;
				continue;
			}
		}
		if (n->expected && n->have == n->expected) {
			ntrig_packet(n);
			n->prefix = n->have = n->expected = 0;
		}
	}
}

static int ntrig_transfer(struct ntrig *n)
{
	struct spi_transfer xfer = {
		.tx_buf = n->tx, .rx_buf = n->rx, .len = n->transfer_len,
	};
	int err = spi_sync_transfer(n->spi, &xfer, 1);

	n->transfers++;
	memset(n->tx, 0xff, sizeof(n->tx));
	if (err)
		n->errors++;
	else
		ntrig_feed(n, n->rx, xfer.len);
	return err;
}

static void ntrig_alive(struct ntrig *n)
{
	static const u8 alive[] = {
		0xff, 0xff, 0xff, 0xff, 0xa5, 0x5a, 0xe7, 0x7e,
		2, 14, 0, 0, 0, 6, 0xa1, 1, 0x0a, 3, 0, 1, 0, 4,
	};
	memcpy(n->tx, alive, sizeof(alive));
	ntrig_transfer(n);
}

static bool ntrig_drain(struct ntrig *n)
{
	unsigned int i;
	for (i = 0; i < 32; i++) {
		if (ntrig_transfer(n))
			return false;
		if (!gpiod_get_value_cansleep(n->ready) && !n->have)
			return true;
	}
	return false;
}

static irqreturn_t ntrig_irq(int irq, void *data)
{
	struct ntrig *n = data;
	mutex_lock(&n->lock);
	if (!n->stopping) {
		if (!n->irq_masked) {
			disable_irq_nosync(irq);
			n->irq_masked = true;
		}
		if (ntrig_drain(n)) {
			n->irq_masked = false;
			enable_irq(irq);
		} else {
			mod_delayed_work(system_wq, &n->poll, msecs_to_jiffies(100));
		}
	}
	mutex_unlock(&n->lock);
	return IRQ_HANDLED;
}

static void ntrig_poll(struct work_struct *work)
{
	struct ntrig *n = container_of(to_delayed_work(work), struct ntrig, poll);
	mutex_lock(&n->lock);
	if (!n->stopping) {
		if (++n->ticks >= 10) {
			ntrig_alive(n);
			n->ticks = 0;
		}
		if ((n->irq_masked || gpiod_get_value_cansleep(n->ready) || n->have)
		    && ntrig_drain(n) && n->irq_masked) {
			n->irq_masked = false;
			enable_irq(n->spi->irq);
		}
		schedule_delayed_work(&n->poll, msecs_to_jiffies(100));
	}
	mutex_unlock(&n->lock);
}

static ssize_t stats_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct ntrig *n = dev_get_drvdata(dev);
	ssize_t count;
	mutex_lock(&n->lock);
	count = sysfs_emit(buf,
		"transfers=%llu packets=%llu invalid=%llu touch=%llu pen=%llu errors=%llu transfer_size=%u ready=%d pen_x=%u pen_y=%u pressure=%u flags=0x%02x last=%*ph rx=%*ph\n",
		n->transfers, n->packets, n->invalid, n->mt_reports, n->pen_reports,
		n->errors, n->transfer_len, gpiod_get_value_cansleep(n->ready),
		n->last_x, n->last_y, n->last_pressure, n->last_flags, 32, n->last, 48, n->rx);
	mutex_unlock(&n->lock);
	return count;
}
static DEVICE_ATTR_RO(stats);

static struct input_dev *ntrig_input(struct ntrig *n, bool pen)
{
	struct device *dev = &n->spi->dev;
	struct input_dev *input = devm_input_allocate_device(dev);
	struct touchscreen_properties *props = pen ? &n->pen_props : &n->touch_props;
	int err;
	if (!input)
		return ERR_PTR(-ENOMEM);
	input->name = pen ? "N-Trig Indigo Pen" : "N-Trig Indigo Touchscreen";
	input->id.bustype = BUS_SPI;
	input->id.vendor = 0x1b96;
	input->id.product = 1;
	input->dev.parent = dev;
	__set_bit(INPUT_PROP_DIRECT, input->propbit);
	if (pen) {
		input_set_capability(input, EV_KEY, BTN_TOUCH);
		input_set_capability(input, EV_KEY, BTN_TOOL_PEN);
		input_set_capability(input, EV_KEY, BTN_TOOL_RUBBER);
		input_set_capability(input, EV_KEY, BTN_STYLUS);
		input_set_abs_params(input, ABS_X, 0, 9600, 0, 0);
		input_set_abs_params(input, ABS_Y, 0, 7200, 0, 0);
		input_set_abs_params(input, ABS_PRESSURE, 0, 255, 0, 0);
		input_set_abs_params(input, ABS_DISTANCE, 0, 1, 0, 0);
	} else {
		input_set_abs_params(input, ABS_MT_POSITION_X, 0, 9600, 0, 0);
		input_set_abs_params(input, ABS_MT_POSITION_Y, 0, 7200, 0, 0);
		input_set_abs_params(input, ABS_MT_TOUCH_MAJOR, 0, 9600, 0, 0);
		input_set_abs_params(input, ABS_MT_TOUCH_MINOR, 0, 9600, 0, 0);
	}
	touchscreen_parse_properties(input, !pen, props);
	/* libinput requires tablet axis resolution (units/mm). LP101WX1 is 229x149 mm. */
	input_abs_set_res(input, pen ? ABS_X : ABS_MT_POSITION_X, 42);
	input_abs_set_res(input, pen ? ABS_Y : ABS_MT_POSITION_Y, 48);
	if (!pen) {
		err = input_mt_init_slots(input, NTRIG_CONTACTS, INPUT_MT_DIRECT | INPUT_MT_DROP_UNUSED);
		if (err)
			return ERR_PTR(err);
	}
	err = input_register_device(input);
	return err ? ERR_PTR(err) : input;
}

static void ntrig_power_off(void *data)
{
	struct ntrig *n = data;
	gpiod_set_value_cansleep(n->enable, 0);
	gpiod_set_value_cansleep(n->power, 0);
}

static int ntrig_probe(struct spi_device *spi)
{
	struct device *dev = &spi->dev;
	struct ntrig *n = devm_kzalloc(dev, sizeof(*n), GFP_KERNEL);
	int err;
	if (!n)
		return -ENOMEM;
	n->spi = spi;
	n->transfer_len = NTRIG_G3;
	memset(n->tx, 0xff, sizeof(n->tx));
	mutex_init(&n->lock);
	INIT_DELAYED_WORK(&n->poll, ntrig_poll);
	spi_set_drvdata(spi, n);
	n->power = devm_gpiod_get(dev, "power", GPIOD_OUT_LOW);
	if (IS_ERR(n->power))
		return dev_err_probe(dev, PTR_ERR(n->power), "power GPIO\n");
	n->enable = devm_gpiod_get(dev, "enable", GPIOD_OUT_LOW);
	if (IS_ERR(n->enable))
		return dev_err_probe(dev, PTR_ERR(n->enable), "enable GPIO\n");
	err = devm_add_action_or_reset(dev, ntrig_power_off, n);
	if (err)
		return err;
	n->ready = devm_gpiod_get(dev, "interrupt", GPIOD_IN);
	if (IS_ERR(n->ready))
		return dev_err_probe(dev, PTR_ERR(n->ready), "interrupt GPIO\n");
	spi->bits_per_word = 8;
	err = spi_setup(spi);
	if (err)
		return err;
	n->touch = ntrig_input(n, false);
	if (IS_ERR(n->touch))
		return PTR_ERR(n->touch);
	n->pen = ntrig_input(n, true);
	if (IS_ERR(n->pen))
		return PTR_ERR(n->pen);
	msleep(50);
	gpiod_set_value_cansleep(n->power, 1);
	msleep(500);
	gpiod_set_value_cansleep(n->enable, 1);
	msleep(50);
	err = devm_request_threaded_irq(dev, spi->irq, NULL, ntrig_irq,
					IRQF_ONESHOT | IRQF_TRIGGER_HIGH, dev_name(dev), n);
	if (err)
		return dev_err_probe(dev, err, "interrupt registration\n");
	err = device_create_file(dev, &dev_attr_stats);
	if (err)
		return err;
	mutex_lock(&n->lock);
	memset(n->tx, 0xff, sizeof(n->tx));
	ntrig_alive(n);
	mutex_unlock(&n->lock);
	schedule_delayed_work(&n->poll, msecs_to_jiffies(100));
	dev_info(dev, "Indigo SPI touch/pen ready at %u Hz\n", spi->max_speed_hz);
	return 0;
}

static void ntrig_remove(struct spi_device *spi)
{
	struct ntrig *n = spi_get_drvdata(spi);
	mutex_lock(&n->lock);
	n->stopping = true;
	mutex_unlock(&n->lock);
	devm_free_irq(&spi->dev, spi->irq, n);
	cancel_delayed_work_sync(&n->poll);
	device_remove_file(&spi->dev, &dev_attr_stats);
}

static const struct of_device_id ntrig_of_match[] = {
	{ .compatible = "ntrig,duosense-spi" }, {}
};
MODULE_DEVICE_TABLE(of, ntrig_of_match);
static const struct spi_device_id ntrig_ids[] = { { "duosense-spi", 0 }, {} };
MODULE_DEVICE_TABLE(spi, ntrig_ids);
static struct spi_driver ntrig_driver = {
	.driver = { .name = "ntrig-indigo", .of_match_table = ntrig_of_match },
	.probe = ntrig_probe, .remove = ntrig_remove, .id_table = ntrig_ids,
};
module_spi_driver(ntrig_driver);
MODULE_DESCRIPTION("ThinkPad Tablet N-Trig SPI touch and pen");
MODULE_LICENSE("GPL");
