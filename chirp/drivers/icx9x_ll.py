# -*- coding: utf-8 -*-
# Copyright 2018 Jaroslav Škarvada <jskarvad@redhat.com>
# Based on icx8x code by Dan Smith <dsmith@danplanet.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

ICX9X_MEM_FORMAT = """
#seekto 0x0010;
struct {
  lbcd rx_freq[4];
  u8 rxtone;
  lbcd offset[4];
  u8 txtone;
  u8 ishighpower:1,
     iswide:1,
     dtcsinvt:1,
     unknown1:1,
     dtcsinvr:1,
     unknown2:1,
     duplex:2;
  u8 unknown;
  lbcd tx_freq[4];
} tx_memory[99];

#seekto 0x0780;
struct {
  lbcd lower_vhf[2];
  lbcd upper_vhf[2];
  lbcd lower_uhf[2];
  lbcd upper_uhf[2];
} limits;

struct vfosettings {
  lbcd freq[4];
  u8   rxtone;
  u8   unknown1;
  lbcd offset[3];
  u8   txtone;
  u8   power:1,
       bandwidth:1,
       unknown2:4,
       duplex:2;
  u8   step;
  u8   unknown3[4];
};

#seekto 0x0790;
struct {
  struct vfosettings uhf;
  struct vfosettings vhf;
} vfo;

#seekto 0x07C2;
struct {
  u8 squelch;
  u8 vox;
  u8 timeout;
  u8 save:1,
     unknown_1:1,
     dw:1,
     ste:1,
     beep:1,
     unknown_2:1,
     bclo:1,
     ch_flag:1;
  u8 backlight:2,
     relaym:1,
     scanm:1,
     pri:1,
     unknown_3:3;
  u8 unknown_4[3];
  u8 pri_ch;
} settings;

#seekto 0x07E0;
u16 fm_presets[16];

#seekto 0x0810;
struct {
  lbcd rx_freq[4];
  u8 rxtone;
  lbcd offset[4];
  u8 txtone;
  u8 ishighpower:1,
     iswide:1,
     dtcsinvt:1,
     unknown1:1,
     dtcsinvr:1,
     unknown2:1,
     duplex:2;
  u8 unknown;
  lbcd tx_freq[4];
} rx_memory[99];

#seekto 0x1008;
struct {
  u8 unknown[8];
  u8 name[6];
  u8 pad[2];
} names[128];
"""

import struct

from chirp import chirp_common, errors
from chirp.memmap import MemoryMap
from chirp.chirp_common import to_MHz

POS_FREQ_START = 0
POS_FREQ_END = 2
POS_OFFSET = 5
POS_NAME_START = 10
POS_NAME_END = 15
POS_RTONE1 = 8
POS_RTONE2 = 9
POS_CTONE = 9
POS_DTCS = 7
POS_TUNE_STEP = 8
POS_TMODE = 4
POS_MODE = 4
POS_MULT_FLAG = 3
POS_DTCS_POL = 3
POS_DUPLEX = 4
POS_BANK = 0
POS_BANK_INDEX = 1

BANK_OFFS = 0x2260

MEM_LOC_SIZE = 16

TUNING_STEPS = [5.0, 6.25, 8.33, 9.0, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0, 200.0]


def bank_name(index):
    char = chr(ord("A") + index)
    return "BANK-%s" % char


def get_freq(mmap, base):
    if (ord(mmap[POS_MULT_FLAG]) & 0x01) == 0x01:
        mult = 6250
    else:
        mult = 5000

    val = struct.unpack("<H", mmap[POS_FREQ_START:POS_FREQ_END])[0]

    return (val * mult) + to_MHz(base)


def set_freq(mmap, freq, base):
    tflag = ord(mmap[POS_MULT_FLAG]) & 0xfe

    if chirp_common.is_fractional_step(freq):
        mult = 6250
        tflag |= 0x01
    else:
        mult = 5000

    value = (freq - to_MHz(base)) / mult

    mmap[POS_MULT_FLAG] = tflag
    mmap[POS_FREQ_START] = struct.pack("<H", value)


def get_name(mmap):
    return mmap[POS_NAME_START:POS_NAME_END].strip()


def set_name(mmap, name):
    mmap[POS_NAME_START] = name.ljust(6)[:6]


def get_rtone(mmap):
    idx = ord(mmap[POS_RTONE1]) & 0xf0 + (ord(mmap[POS_RTONE2]) & 0x03) << 4

    return chirp_common.TONES[idx]


def set_rtone(mmap, tone):
    idx = chirp_common.TONES.index(tone)
    mmap[POS_RTONE2] &= 0xfc
    mmap[POS_RTONE2] |= (idx >> 4) & 0x03
    mmap[POS_RTONE1] &= 0x0f
    mmap[POS_RTONE1] |= idx & 0x0f


def get_ctone(mmap):
    idx, = struct.unpack("B", mmap[POS_CTONE])
    idx >>= 2
    return chirp_common.TONES[idx]


def set_ctone(mmap, tone):
    mmap[POS_CTONE] &= 0x03
    mmap[POS_CTONE] |= chirp_common.TONES.index(tone) << 2


def get_dtcs(mmap):
    idx, = struct.unpack("B", mmap[POS_DTCS])

    return chirp_common.DTCS_CODES[idx]


def set_dtcs(mmap, code):
    mmap[POS_DTCS] = chirp_common.DTCS_CODES.index(code)


def get_dtcs_polarity(mmap):
    val = struct.unpack("B", mmap[POS_DTCS_POL])[0] & 0xC0

    pol_values = {
        0x00: "NN",
        0x40: "NR",
        0x80: "RN",
        0xC0: "RR"}

    return pol_values[val]


def set_dtcs_polarity(mmap, polarity):
    val = struct.unpack("B", mmap[POS_DTCS_POL])[0] & 0x3F
    pol_values = {"NN": 0x00,
                  "NR": 0x40,
                  "RN": 0x80,
                  "RR": 0xC0}
    val |= pol_values[polarity]

    mmap[POS_DTCS_POL] = val


def get_dup_offset(mmap):
    if (ord(mmap[POS_MULT_FLAG]) & 0x08) == 0x08:
        mult = 6250
    else:
        mult = 5000
    val = struct.unpack("<H", mmap[POS_OFFSET:POS_OFFSET+2])[0]
    return val * mult


def set_dup_offset(mmap, offset):
    if chirp_common.is_fractional_step(offset):
        mult = 6250
        flag = 0x08
    else:
        mult = 5000
        flag = 0x00
    val = struct.pack("<H", offset / mult)
    mmap[POS_OFFSET] = val
    mmap[POS_MULT_FLAG] &= 0xf7
    mmap[POS_MULT_FLAG] |= flag


def get_duplex(mmap):
    val = struct.unpack("B", mmap[POS_DUPLEX])[0] & 0x30

    if val == 0x10:
        return "-"
    elif val == 0x20:
        return "+"
    else:
        return ""


def set_duplex(mmap, duplex):
    val = struct.unpack("B", mmap[POS_DUPLEX])[0] & 0xCF

    if duplex == "-":
        val |= 0x10
    elif duplex == "+":
        val |= 0x20

    mmap[POS_DUPLEX] = val


def get_tone_enabled(mmap):
    val = struct.unpack("B", mmap[POS_TMODE])[0] & 0x03

    if val == 0x01:
        return "Tone"
    elif val == 0x02:
        return "TSQL"
    elif val == 0x04:
        return "DTCS"
    else:
        return ""


def set_tone_enabled(mmap, tmode):
    val = struct.unpack("B", mmap[POS_TMODE])[0] & 0xF8

    if tmode == "Tone":
        val |= 0x01
    elif tmode == "TSQL":
        val |= 0x02
    elif tmode == "DTCS":
        val |= 0x04

    mmap[POS_TMODE] = val


def get_tune_step(mmap):
    tsidx = struct.unpack("B", mmap[POS_TUNE_STEP])[0] & 0x0f
    icx9x_ts = list(TUNING_STEPS)

    try:
        return icx9x_ts[tsidx]
    except IndexError:
        raise errors.InvalidDataError("TS index %i out of range (%i)" %
                                      (tsidx, len(icx9x_ts)))


def set_tune_step(mmap, tstep):
    val = struct.unpack("B", mmap[POS_TUNE_STEP])[0] & 0xf0
    icx9x_ts = list(TUNING_STEPS)

    tsidx = icx9x_ts.index(tstep)
    mmap[POS_TUNE_STEP] = val


def get_mode(mmap):
    val = (struct.unpack("B", mmap[POS_MODE])[0] & 0x18)

    if val == 0x00:
        return "FM"
    elif val == 0x08:
        return "WFM"
    elif val == 0x10:
        return "AM"


def set_mode(mmap, mode):
    val = struct.unpack("B", mmap[POS_MODE])[0] & 0xe7

    if mode == "FM":
        pass
    elif mode == "WFM":
        val |= 0x08
    elif mode == "AM":
        val |= 0x10
    else:
        raise errors.InvalidDataError("%s mode not supported" % mode)

    mmap[POS_MODE] = val


def is_used(mmap, number):
    if number == ICx9x_SPECIAL["C"]:
        return True

    return (ord(mmap[POS_FLAGS_START + number]) & 0x20) == 0


def set_used(mmap, number, used=True):
    if number == ICx9x_SPECIAL["C"]:
        return

    val = struct.unpack("B", mmap[POS_FLAGS_START + number])[0] & 0xDF

    if not used:
        val |= 0x20

    mmap[POS_FLAGS_START + number] = val


def get_skip(mmap, number):
    val = struct.unpack("B", mmap[POS_FLAGS_START + number])[0] & 0x10

    if val != 0:
        return "S"
    else:
        return ""


def set_skip(mmap, number, skip):
    if skip == "P":
        raise errors.InvalidDataError("PSKIP not supported by this model")

    val = struct.unpack("B", mmap[POS_FLAGS_START + number])[0] & 0xEF

    if skip == "S":
        val |= 0x10

    mmap[POS_FLAGS_START + number] = val


def get_mem_offset(number):
    return number * MEM_LOC_SIZE


def get_raw_memory(mmap, number):
    offset = get_mem_offset(number)
    return MemoryMap(mmap[offset:offset + MEM_LOC_SIZE])

def get_bank(mmap, number):
    val = ord(mmap[POS_BANK + (number << 1) + BANK_OFFS]) & 0x0F
    return val

def set_bank(mmap, number, bank):
    offs = POS_BANK + (number << 1) + BANK_OFFS
    val = ord(mmap[offs]) & 0xF0
    val |= bank
    mmap[offs] = val

def get_bank_index(mmap, number):
    return ord(mmap[POS_BANK_INDEX + (number << 1) + BANK_OFFS])

def set_bank_index(mmap, number, index):
    mmap[POS_BANK_INDEX + (number << 1) + BANK_OFFS] = index

def _get_memory(_map, mmap, base):
    mem = chirp_common.Memory()

    mem.freq = get_freq(mmap, base)
    mem.name = get_name(mmap)
    mem.rtone = get_rtone(mmap)
    mem.ctone = get_ctone(mmap)
    mem.dtcs = get_dtcs(mmap)
    mem.dtcs_polarity = get_dtcs_polarity(mmap)
    mem.offset = get_dup_offset(mmap)
    mem.duplex = get_duplex(mmap)
    mem.tmode = get_tone_enabled(mmap)
    mem.tuning_step = get_tune_step(mmap)
    mem.mode = get_mode(mmap)

    return mem


def get_memory(_map, number, base):
#    if not is_used(_map, number):
#        mem = chirp_common.Memory()
#        if number < 200:
#            mem.number = number
#            mem.empty = True
#            return mem
#    else:
#        mmap = get_raw_memory(_map, number)
#        mem = _get_memory(_map, mmap, base)

    mmap = get_raw_memory(_map, number)
    mem = _get_memory(_map, mmap, base)
    mem.number = number

    #mem.skip = get_skip(_map, number)

    return mem


def clear_tx_inhibit(mmap):
    txi = struct.unpack("B", mmap[POS_TXI])[0]
    txi |= 0x40
    mmap[POS_TXI] = txi


def set_memory(_map, memory, base):
    mmap = get_raw_memory(_map, memory.number)

    set_freq(mmap, memory.freq, base)
    set_name(mmap, memory.name)
    set_rtone(mmap, memory.rtone)
    set_ctone(mmap, memory.ctone)
    set_dtcs(mmap, memory.dtcs)
    set_dtcs_polarity(mmap, memory.dtcs_polarity)
    set_dup_offset(mmap, memory.offset)
    set_duplex(mmap, memory.duplex)
    set_tone_enabled(mmap, memory.tmode)
    set_tune_step(mmap, memory.tuning_step)
    set_mode(mmap, memory.mode)
    #set_skip(_map, memory.number, memory.skip)

    _map[get_mem_offset(memory.number)] = mmap.get_packed()

    return _map


def erase_memory(_map, number):
#    set_used(_map, number, False)

    return _map
