# -*- coding: utf-8 -*-
# Copyright 2018-2019 Jaroslav Škarvada <jskarvad@redhat.com>
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

ICX9X_MEM_ITEM_FORMAT = """
struct {
  ul24 freq;
  u8 dtcs_polarity:2,
     unknown_1:2,
     offset_freq_mult:1,
     unknown_2:2,
     freq_mult:1;
  u8 unknown_3:1,
     duplex:2,
     mode:2,
     tone_mode:3;
  ul16 offset_freq;
  u8 dtcs;
  u8 tx_tone_lo:4,
     tune_step:4;
  u8 rx_tone:6,
     tx_tone_hi:2;
  char name[6];
} mem_item;
"""

ICX9X_MEM_FORMAT = """
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

from chirp import chirp_common, bitwise, errors
from chirp.memmap import MemoryMap
from chirp.chirp_common import to_MHz

POS_BANK = 0
POS_BANK_INDEX = 1

BANK_OFFS = 0x2260

MEM_LOC_SIZE = 16

ICX9X_DUPLEXES = ["", "-", "+", ""]
ICX9X_DTCS_POLARITIES = ["NN", "NR", "RN", "RR"]
ICX9X_TONE_MODES = ["", "Tone", "TSQL", "DTCS"]
ICX9X_TUNE_STEPS = [5.0, 6.25, 8.33, 9.0, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0, 200.0]
ICX9X_MODES = ["FM", "WFM", "AM"]

def bank_name(index):
    char = chr(ord("A") + index)
    return "BANK-%s" % char

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

def freq_chirp2icom(freq):
    if chirp_common.is_fractional_step(freq):
        mult = 6250
    else:
        mult = 5000

    return (freq / mult, mult)

def freq_icom2chirp(freq, mult):
    return freq * (6250 if mult else 5000)

def _get_memory(_map, mmap):
    mem = chirp_common.Memory()

    memobj = bitwise.parse(ICX9X_MEM_ITEM_FORMAT, mmap)

    mem.freq = freq_icom2chirp(memobj.mem_item.freq, memobj.mem_item.freq_mult)
    mem.name = memobj.mem_item.name
    mem.rtone = chirp_common.TONES[(memobj.mem_item.tx_tone_hi << 4) + memobj.mem_item.tx_tone_lo]
    mem.ctone = chirp_common.TONES[memobj.mem_item.rx_tone]
    mem.dtcs = chirp_common.DTCS_CODES[memobj.mem_item.dtcs]
    mem.dtcs_polarity = ICX9X_DTCS_POLARITIES[memobj.mem_item.dtcs_polarity]
    mem.offset = freq_icom2chirp(memobj.mem_item.offset_freq, memobj.mem_item.offset_freq_mult)
    mem.duplex = ICX9X_DUPLEXES[memobj.mem_item.duplex]
    mem.tmode = ICX9X_TONE_MODES[memobj.mem_item.tone_mode]
    mem_tuning_step = ICX9X_TUNE_STEPS[memobj.mem_item.tune_step]
    mem.mode = ICX9X_MODES[memobj.mem_item.mode]

    return mem

def get_memory(_map, number):
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
    mem = _get_memory(_map, mmap)
    mem.number = number

    #mem.skip = get_skip(_map, number)

    return mem

def clear_tx_inhibit(mmap):
    txi = struct.unpack("B", mmap[POS_TXI])[0]
    txi |= 0x40
    mmap[POS_TXI] = txi

def set_memory(_map, mem):
    mmap = get_raw_memory(_map, mem.number)
    memobj = bitwise.parse(ICX9X_MEM_ITEM_FORMAT, mmap)

    (memobj.mem_item.freq, memobj.mem_item.freq_mult) = freq_chirp2icom(mem.freq)
    memobj.mem_item.name = mem.name
    memobj.mem_item.tx_tone_hi = chirp_common.TONES.index(mem.rtone) >> 4
    memobj.mem_item.tx_tone_lo = chirp_common.TONES.index(mem.rtone) & 0x0f
    memobj.mem_item.rx_tone = chirp_common.TONES.index(mem.ctone)
    memobj.mem_item.dtcs = chirp_common.DTCS_CODES.index(mem.dtcs)
    memobj.mem_item.dtcs_polarity = ICX9X_DTCS_POLARITIES.index(mem.dtcs_polarity)
    (memobj.mem_item.offset_freq, memobj.mem_item.offset_freq_mult) = freq_chirp2icom(mem.offset)
    memobj.mem_item.duplex = ICX9X_DUPLEXES.index(mem.duplex)
    memobj.mem_item.tone_mode = ICX9X_TONE_MODES.index(mem.tmode)
    memobj.mem_item.tune_step = ICX9X_TUNE_STEPS.index(mem.tuning_step)
    memobj.mem_item.mode = ICX9X_MODES.index(mem.mode)

    _map[get_mem_offset(mem.number)] = mmap.get_packed()

    return _map


def erase_memory(_map, number):
#    set_used(_map, number, False)

    return _map
