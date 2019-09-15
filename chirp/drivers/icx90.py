# -*- coding: utf-8 -*-
# Copyright 2018-2019 Jaroslav Škarvada <jskarvad@redhat.com>
# Based on icx8x code by Dan Smith <dsmith@danplanet.com>

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

ICX90_MEM_ITEM_FORMAT = """
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

ICX90_MEM_FORMAT = """
#seekto 0x2a93;
ul16 mem_channel;
u8 unknown_1[10];
u8 squelch_level;

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

import logging

import icf
import struct
from chirp import chirp_common, bitwise, errors, directory
from chirp.memmap import MemoryMap
from chirp.settings import RadioSetting, RadioSettingGroup, \
    RadioSettingValueInteger, RadioSettingValueList, \
    RadioSettingValueBoolean, RadioSettingValueString, \
    RadioSettingValueFloat, InvalidValueError, RadioSettings

LOG = logging.getLogger(__name__)

POS_BANK = 0
POS_BANK_INDEX = 1

BANK_OFFS = 0x2260

MEM_LOC_SIZE = 16

ICX90_DUPLEXES = ["", "-", "+", ""]
ICX90_DTCS_POLARITIES = ["NN", "NR", "RN", "RR"]
ICX90_TONE_MODES = ["", "Tone", "TSQL", "DTCS"]
ICX90_TUNE_STEPS = [5.0, 6.25, 8.33, 9.0, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0, 200.0]
ICX90_MODES = ["FM", "WFM", "AM"]

def bank_name(index):
    char = chr(ord("A") + index)
    return "BANK-%s" % char

def is_used(mmap, number):
    if number == ICX90_SPECIAL["C"]:
        return True

    return (ord(mmap[POS_FLAGS_START + number]) & 0x20) == 0

def set_used(mmap, number, used=True):
    if number == ICX90_SPECIAL["C"]:
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

def clear_tx_inhibit(mmap):
    txi = struct.unpack("B", mmap[POS_TXI])[0]
    txi |= 0x40
    mmap[POS_TXI] = txi

def erase_memory(_map, number):
#    set_used(_map, number, False)

    return _map

class ICx90BankModel(icf.IcomIndexedBankModel):
    bank_indexes = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "L", "N", "O",
                    "P", "Q", "R", "T", "U", "Y"]

    def get_mappings(self):
        banks = []

        if (self._radio._num_banks != len(type(self).bank_indexes)):
            raise Exception("Invalid number of banks %d, supported only %d banks" %
                (self._radio._num_banks, len(type(self).bank_indexes)))

        for i in range(0, self._radio._num_banks):
            index = type(self).bank_indexes[i]
            bank = self._radio._bank_class(self, index, "BANK-%s" % index)
            bank.index = i
            banks.append(bank)

        return banks

@directory.register
class ICx90Radio(icf.IcomCloneModeRadio):
    """Icom IC-E/T90"""
    VENDOR = "Icom"
    MODEL = "IC-E90/T90"

    _model = "\x25\x07\x00\x01"
    _memsize = 0x2d40
    _endframe = "Icom Inc\x2e\xfd"

    _ranges = [(0x0000, 0x2d40, 32)]
    _num_banks = 18
    _bank_index_bounds = (0, 99)
    _can_hispeed = False
    _check_clone_status = False

    def _get_bank(self, loc):
        return get_bank(self._mmap, loc)

    def _set_bank(self, loc, bank):
        return set_bank(self._mmap, loc, bank)

    def _get_bank_index(self, loc):
        return get_bank_index(self._mmap, loc)

    def _set_bank_index(self, loc, index):
        return set_bank_index(self._mmap, loc, index)

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_settings = True
        rf.has_name = True
        rf.has_bank = False
        rf.has_bank_index = True
        rf.has_bank_names = False
        rf.memory_bounds = (0, 499)
#        rf.valid_power_levels = [chirp_common.PowerLevel("High", watts = 5.0),
#                                 chirp_common.PowerLevel("Low", watts = 0.5)]
        rf.valid_modes = list(ICX90_MODES)
        rf.valid_tmodes = list(ICX90_TONE_MODES)
        rf.valid_duplexes = list(ICX90_DUPLEXES)[:-1]
        rf.valid_tuning_steps = list(ICX90_TUNE_STEPS)
        rf.valid_bands = [(495000, 999990000)]
        rf.valid_skips = ["", "S"]
        rf.valid_name_length = 6
#        rf.valid_special_chans = sorted(ICx90_SPECIAL.keys())

        return rf

    def get_settings(self):
        try:
            _squelch = 1
            basic = RadioSettingGroup("basic", "Basic Settings")
            group = RadioSettings(basic)
            rs = RadioSetting("squelch", "Carrier Squelch Level",
                              RadioSettingValueInteger(0, 9, _squelch))
            basic.append(rs)
            return group
        except:
            import traceback
            LOG.error("Failed to parse settings: %s", traceback.format_exc())
            return None

    def set_settings(self, settings):
        pass

    def __init__(self, pipe):
        icf.IcomCloneModeRadio.__init__(self, pipe)

    def sync_in(self):
#        self._get_type()
#        icf.IcomCloneModeRadio.sync_in(self)
#        self._mmap[0x1930] = self._isuhf and 1 or 0
        self._mmap = icf.read_file("/var/tmp/ice90u.icf")[1]

    def sync_out(self):
        self._get_type()
        icf.IcomCloneModeRadio.sync_out(self)
        return

    def get_memory(self, number):
        if not self._mmap:
            self.sync_in()

#    if not is_used(_map, number):
#        mem = chirp_common.Memory()
#        if number < 200:
#            mem.number = number
#            mem.empty = True
#            return mem
#    else:
#        mmap = self.get_raw_memory(number)
#        mem = _get_memory(_map, mmap, base)

        mmap = self.get_raw_memory(number)
        mem = chirp_common.Memory()

        memobj = bitwise.parse(ICX90_MEM_ITEM_FORMAT, mmap)

        mem.freq = freq_icom2chirp(memobj.mem_item.freq, memobj.mem_item.freq_mult)
        mem.name = memobj.mem_item.name
        mem.rtone = chirp_common.TONES[(memobj.mem_item.tx_tone_hi << 4) + memobj.mem_item.tx_tone_lo]
        mem.ctone = chirp_common.TONES[memobj.mem_item.rx_tone]
        mem.dtcs = chirp_common.DTCS_CODES[memobj.mem_item.dtcs]
        mem.dtcs_polarity = ICX90_DTCS_POLARITIES[memobj.mem_item.dtcs_polarity]
        mem.offset = freq_icom2chirp(memobj.mem_item.offset_freq, memobj.mem_item.offset_freq_mult)
        mem.duplex = ICX90_DUPLEXES[memobj.mem_item.duplex]
        mem.tmode = ICX90_TONE_MODES[memobj.mem_item.tone_mode]
        mem_tuning_step = ICX90_TUNE_STEPS[memobj.mem_item.tune_step]
        mem.mode = ICX90_MODES[memobj.mem_item.mode]

        mem.number = number

        #mem.skip = get_skip(self._mmap, number)
        return mem

    def set_memory(self, memory):
        if not self._mmap:
            self.sync_in()

        mmap = self.get_raw_memory(memory.number)
        memobj = bitwise.parse(ICX90_MEM_ITEM_FORMAT, mmap)

        (memobj.mem_item.freq, memobj.mem_item.freq_mult) = freq_chirp2icom(memory.freq)
        memobj.mem_item.name = memory.name
        memobj.mem_item.tx_tone_hi = chirp_common.TONES.index(memory.rtone) >> 4
        memobj.mem_item.tx_tone_lo = chirp_common.TONES.index(memory.rtone) & 0x0f
        memobj.mem_item.rx_tone = chirp_common.TONES.index(memory.ctone)
        memobj.mem_item.dtcs = chirp_common.DTCS_CODES.index(memory.dtcs)
        memobj.mem_item.dtcs_polarity = ICX90_DTCS_POLARITIES.index(memory.dtcs_polarity)
        (memobj.mem_item.offset_freq, memobj.mem_item.offset_freq_mult) = freq_chirp2icom(memory.offset)
        memobj.mem_item.duplex = ICX90_DUPLEXES.index(memory.duplex)
        memobj.mem_item.tone_mode = ICX90_TONE_MODES.index(memory.tmode)
        memobj.mem_item.tune_step = ICX90_TUNE_STEPS.index(memory.tuning_step)
        memobj.mem_item.mode = ICX90_MODES.index(memory.mode)

        self._mmap[get_mem_offset(mem.number)] = mmap.get_packed()

    def get_raw_memory(self, number):
        offset = get_mem_offset(number)
        return MemoryMap(self._mmap[offset:offset + MEM_LOC_SIZE])

    def get_bank_model(self):
        return ICx90BankModel(self)

from chirp import memmap

def _read(ser):
    f2 = open("/var/tmp/clone3.bin", "w")
    ser.sync_in()
    for x in range(0, 11584):
      f2.write(ser._mmap[x])

def _write(ser):
    f = open("/var/tmp/clone3.bin", "r")
    addr = 0
    ser._mmap = memmap.MemoryMap(chr(0x00) * 11584)
    b = f.read(1)
    while b != "":
      ser._mmap[addr] = ord(b)
      addr += 1
      b = f.read(1)
#    ser._mmap = icf.read_file("/var/tmp/ice90u.icf")[1]
    ser.sync_out()

def _read_icf(ser):
    ser._mmap = icf.read_file("/var/tmp/ice90u.icf")[1]
    f2 = open("/var/tmp/clone3.bin", "w")
    for x in range(0, 11584):
      f2.write(ser._mmap[x])

def _test():
    import serial
    ser = ICx90Radio(serial.Serial(port=None,
                                   baudrate=9600, timeout=0.1))
    _read_icf(ser)
    print(ser.get_index_bounds())

if __name__ == "__main__":
    _test()
