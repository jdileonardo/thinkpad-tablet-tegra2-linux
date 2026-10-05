#!/usr/bin/env python3
"""Exercise the driver's actual streaming parser with ASan/UBSan on the host."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
driver = (root / 'port/ntrig-spi/ntrig_indigo.c').read_text()
parser = driver[driver.index('static void ntrig_feed('):driver.index('static int ntrig_transfer(')]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef uint8_t u8;
#define min(a,b) ((a)<(b)?(a):(b))
static unsigned get_unaligned_le16(const u8 *p) { return p[0] | (p[1]<<8); }
struct ntrig { unsigned prefix, have, expected, invalid, packets; u8 frame[264]; };
static void ntrig_packet(struct ntrig *n) { assert(n->expected>=6 && n->expected<=264); n->packets++; }
'''
harness += parser
harness += r'''
static const u8 good[] = {255,255,255,255,0xa5,0x5a,0xe7,0x7e,1,9,0,0,3,1,0x10,0x20,0x30};
int main(void) {
    for (unsigned split=0; split<=sizeof(good); split++) {
        struct ntrig n={0};
        ntrig_feed(&n,good,split); ntrig_feed(&n,good+split,sizeof(good)-split);
        assert(n.packets==1 && n.invalid==0 && n.have==0);
        assert(n.frame[8]==0x30);
    }
    struct ntrig n={0};
    for (unsigned i=0;i<sizeof(good);i++) ntrig_feed(&n,good+i,1);
    assert(n.packets==1);
    for (unsigned len=0;len<6;len++) {
        u8 bad[]={255,255,255,255,0xa5,0x5a,0xe7,0x7e,1,len,0};
        ntrig_feed(&n,bad,sizeof(bad)); ntrig_feed(&n,good,sizeof(good));
    }
    assert(n.invalid==6 && n.packets==7);
    const u8 oversized[]={255,255,255,255,0xa5,0x5a,0xe7,0x7e,1,255,255};
    ntrig_feed(&n,oversized,sizeof(oversized)); ntrig_feed(&n,good,sizeof(good));
    assert(n.invalid==7 && n.packets==8);
    // Extra idle bytes and a damaged signature must resynchronize.
    const u8 noise[]={255,255,255,255,255,0xa5,255};
    ntrig_feed(&n,noise,sizeof(noise)); ntrig_feed(&n,good,sizeof(good));
    assert(n.packets==9);
    // Largest accepted message, split across one-byte transfers.
    u8 large[272]={255,255,255,255,0xa5,0x5a,0xe7,0x7e,1,8,1};
    for (unsigned i=0;i<sizeof(large);i++) ntrig_feed(&n,large+i,1);
    assert(n.packets==10);
    // Untrusted byte streams must stay within the parser's fixed buffer.
    uint32_t random=123456;
    for (unsigned i=0;i<1000000;i++) {
        random^=random<<13; random^=random>>17; random^=random<<5;
        u8 b=random; ntrig_feed(&n,&b,1);
        assert(n.have<=sizeof(n.frame));
    }
    puts("PASS: fragmented packets, corruption recovery, length bounds, 1M random bytes");
}
'''
with tempfile.TemporaryDirectory(prefix='ntrig-parser-') as directory:
    source = Path(directory) / 'test.c'
    binary = Path(directory) / 'test'
    source.write_text(harness)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
