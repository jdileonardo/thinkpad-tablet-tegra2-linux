#!/usr/bin/env python3
"""Test real SPI report decoding, including raw confidence and pen tool flags."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
driver = (root / 'port/ntrig-spi/ntrig_indigo.c').read_text()
decoders = driver[driver.index('static void ntrig_mt('):driver.index('static void ntrig_packet(')]
source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <linux/input.h>
typedef uint8_t u8; typedef uint16_t u16;
#define BIT(n) (1U<<(n))
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define min_t(t,a,b) min((t)(a),(t)(b))
struct input_dev { unsigned states, active, x, y, syncs; int keys[KEY_MAX+1], abs[ABS_MAX+1]; };
struct touchscreen_properties { int unused; };
struct ntrig { struct input_dev *touch,*pen; struct touchscreen_properties touch_props,pen_props;
 unsigned mt_reports,pen_reports,invalid,last_x,last_y,last_pressure,last_flags; };
static unsigned get_unaligned_le16(const u8 *p) { return p[0] | p[1]<<8; }
static int input_mt_get_slot_by_key(struct input_dev *d,unsigned key) { (void)d; return key%10; }
static void input_mt_slot(struct input_dev *d,int slot) { (void)d;(void)slot; }
static void input_mt_report_slot_state(struct input_dev *d,int tool,bool active) {
 (void)tool; d->states++; d->active+=active;
}
static void touchscreen_report_pos(struct input_dev *d,struct touchscreen_properties *p,
 unsigned x,unsigned y,bool mt) { (void)p;(void)mt; d->x=x; d->y=y; }
static void input_report_abs(struct input_dev *d,unsigned code,int value) { d->abs[code]=value; }
static void input_report_key(struct input_dev *d,unsigned code,int value) { d->keys[code]=value; }
static void input_mt_sync_frame(struct input_dev *d) { (void)d; }
static void input_sync(struct input_dev *d) { d->syncs++; }
'''+decoders+r'''
int main(void) {
 struct input_dev touch={0},pen={0}; struct ntrig n={.touch=&touch,.pen=&pen};
 u8 report[154]={3,1,0}; u8 *f=report+3;
 f[0]=7; f[1]=4; f[3]=0x86; f[4]=0x10; f[5]=0x46; f[6]=0x1b;
 f[7]=250; f[9]=150; f[11]=1; report[93]=1;
 ntrig_mt(&n,report,94,false);
 assert(touch.active==1 && touch.x==4230 && touch.y==6982);
 assert(touch.abs[ABS_MT_TOUCH_MAJOR]==250 && touch.abs[ABS_MT_TOUCH_MINOR]==150);
 // Raw SPI confidence 0 is release; TrackLib's processed removed flag is inverted.
 f[11]=0; ntrig_mt(&n,report,94,false); assert(touch.states==2 && touch.active==1);
 f[11]=1; f[13]=1; ntrig_mt(&n,report,94,false); assert(touch.active==1);
 ntrig_mt(&n,report,93,false); assert(n.invalid==1 && touch.states==3);
 report[93]=7; ntrig_mt(&n,report,94,false); assert(n.invalid==2 && touch.states==3);
 for(unsigned i=0;i<10;i++) { report[3+i*15+1]=i; report[3+i*15+11]=1; report[3+i*15+13]=0; }
 report[153]=10; ntrig_mt(&n,report,154,true); assert(touch.active==11);
 u8 p[]={2,1,0x34,0x12,0x78,0x16,0,0,0};
 ntrig_pen(&n,p,9); assert(pen.keys[BTN_TOOL_PEN] && !pen.keys[BTN_TOUCH] && pen.abs[ABS_DISTANCE]==1);
 p[1]=7; p[6]=123; ntrig_pen(&n,p,9);
 assert(pen.keys[BTN_TOUCH] && pen.keys[BTN_STYLUS] && pen.abs[ABS_PRESSURE]==123);
 assert(pen.x==0x1234 && pen.y==0x1678);
 p[1]=0x19; p[6]=255; p[7]=255; ntrig_pen(&n,p,9);
 assert(pen.keys[BTN_TOOL_RUBBER] && !pen.keys[BTN_TOOL_PEN] && pen.abs[ABS_PRESSURE]==255);
 assert(!pen.keys[BTN_STYLUS2]); // Inversion is a tool flag, not a second barrel button.
 p[1]=0; ntrig_pen(&n,p,9);
 assert(!pen.keys[BTN_TOOL_RUBBER] && !pen.keys[BTN_TOUCH] && !pen.abs[ABS_PRESSURE]);
 ntrig_pen(&n,p,8); assert(n.invalid==3 && n.pen_reports==4);
 puts("PASS: SPI confidence/release, palm exclusion, G3/G4 bounds, pen hover/tip/button/eraser");
}
'''
with tempfile.TemporaryDirectory(prefix='ntrig-reports-') as directory:
    path = Path(directory) / 'test.c'
    binary = Path(directory) / 'test'
    path.write_text(source)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
