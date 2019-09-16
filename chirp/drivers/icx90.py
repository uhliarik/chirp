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

ICX90_MEM_FORMAT = """
struct mem_item {
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
};
struct bank_item {
  u8 unknown_4:1,
     prog_skip:1,
     mem_skip:1,
     bank_index:5;
  u8 bank_channel;
};
struct tv_mem_item {
  u8 fixed:7,
     modulation:1;
  ul24 freq;
  char name[4];
};

struct mem_item memory[500];
struct mem_item scan_edges[50];
struct bank_item banks[500];
u8 unknown_5[120];
struct mem_item vfo_a_band[10];
struct mem_item vfo_b_band[10];
struct mem_item call_channels[5];
struct tv_mem_item tv_memory[68];
u8 unknown_6[35];
ul16 mem_channel;
u8 unknown_7[10];
u8 squelch_level;
struct {
  u8 dtmf_digits[16];
} dtmf_codes[10];
u8 tv_channel_skip[68];
u8 unknown_8[128];
u8 scan_resume;
u8 scan_pause;
u8 unknown_9;
u8 beep_volume;
u8 beep;
u8 back_light;
u8 busy_led;
u8 auto_power_off;
u8 power_save;
u8 monitor;
u8 dial_speedup;
u8 unknown_10;
u8 auto_repeater;
u8 dtmf_speed;
u8 hm_75a_function;
u8 wx_alert;
u8 expand_1;
u8 scan_stop_beep;
u8 scan_stop_light;
u8 unknown_11;
u8 light_position;
u8 ligth_color;
u8 unknown_12;
u8 band_edge_beep;
u8 auto_power_on;
u8 key_lock;
u8 ptt_lock;
u8 lcd_contrast;
u8 opening_message;
u8 expand_2;
u8 unknown_13;
u8 busy_lock_out;
u8 timeout_timer;
u8 unknown_14;
u8 active_band;
u8 fm_narrow;
u8 morse_code_enable;
u8 morse_code_speed;
u8 unknown_15[22];
char opening_message_text[6];
u8 unknown_16[186];
u8 tune_step;
u8 unknown_17[4];
u8 band_selected;
u8 unknown_18[2];
u8 memory_display:1,
   memory_name:1,
   dial_select:1,
   power:1,
   vfo:1,
   attenuator:1,
   unknown_19:2;
u8 unknown_20[2];
u8 mode;
u8 unknown_21;
char alpha_tag[6];
u8 vfo_scan;
u8 memory_scan;
u8 unknown_22;
u8 tv_channel;
u8 wx_channel;
char comment[16];
"""

# in bytes
MEM_ITEM_SIZE = 16

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

BANK_INDEXES = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "L", "N", "O",
                "P", "Q", "R", "T", "U", "Y"]
MEM_NUM = 500
BANK_NUM = 100
BANK_INDEXES_NUM = len(BANK_INDEXES)

ICX90_NAME_LENGTH = 6
ICX90_DUPLEXES = ["", "-", "+", ""]
ICX90_DTCS_POLARITIES = ["NN", "NR", "RN", "RR"]
ICX90_TONE_MODES = ["", "Tone", "TSQL", "DTCS"]
ICX90_TUNE_STEPS = [5.0, 6.25, 8.33, 9.0, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0, 200.0]
ICX90_MODES = ["FM", "WFM", "AM"]

class ICx90BankModel(icf.IcomIndexedBankModel):
    bank_indexes = BANK_INDEXES

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
    _bank_index_bounds = (0, BANK_NUM - 1)
    _can_hispeed = False
    _check_clone_status = False

    def __init__(self, pipe):
        icf.IcomCloneModeRadio.__init__(self, pipe)
        self.init_special()

    def special_add(self, key, item_type, num, unique_idx):
          item = {}
          item["item_type"] = item_type
          item["num"] = num
          item["uidx"] = unique_idx
          self.special[key] = item

    def init_special(self):
      self.special = {}
      i = 0
      # program scan edges
      for x in range(25):
          self.special_add("Scan edge: %02dA" % x, "scan_edge", x * 2, i)
          self.special_add("Scan edge: %02dB" % x, "scan_edge", x * 2 + 1, i + 1)
          i += 2
      # call channels
      for x in range(5):
          self.special_add("Call ch: %d" % x, "call_chan", x, i)
          i += 1
      # VFO A
      for x in range(10):
          self.special_add("VFO A: %d" % x, "vfo_a", x, i)
          i += 1
      # VFO B
      for x in range(10):
          self.special_add("VFO B: %d" % x, "vfo_b", x, i)
          i += 1

    # it seems the bank driver has different terminology about bank number and index
    # so in fact _get_bank and _set_bank are about indexes (i.e index in the array
    # of bank names - A .. Y
    # and _get_bank_index and _set_bank_index are about positions in the bank (0..99)
    def _get_bank(self, loc):
        i = self.memobj.banks[loc].bank_index
        return i if i < BANK_INDEXES_NUM else None

    def _set_bank(self, loc, bank):
        self.memobj.banks[loc].bank_index = bank

    def _get_bank_index(self, loc):
        i = self.memobj.banks[loc].bank_channel
        return i if i < BANK_NUM else None

    def _set_bank_index(self, loc, index):
        self.memobj.banks[loc].bank_channel = index

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_settings = True
        rf.has_name = True
        rf.has_bank = False
        rf.has_bank_index = True
        rf.has_bank_names = False
        rf.can_delete = True
        rf.has_dtcs = True
        rf.has_dtcs_polarity = True
        rf.has_tuning_step = True
        rf.has_comment = False
        rf.memory_bounds = (0, MEM_NUM - 1)
#        rf.valid_power_levels = [chirp_common.PowerLevel("High", watts = 5.0),
#                                 chirp_common.PowerLevel("Low", watts = 0.5)]
        rf.valid_characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()*+-,/|= "
        rf.valid_modes = list(ICX90_MODES)
        rf.valid_tmodes = list(ICX90_TONE_MODES)
        rf.valid_duplexes = list(ICX90_DUPLEXES)[:-1]
        rf.valid_tuning_steps = list(ICX90_TUNE_STEPS)
        rf.valid_bands = [(495000, 999990000)]
        rf.valid_skips = ["", "S", "P"]
        rf.valid_name_length = ICX90_NAME_LENGTH
        rf.valid_special_chans = sorted(self.special.keys())

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

    def process_mmap(self):
        self.memobj = bitwise.parse(ICX90_MEM_FORMAT, self.mmap)

    def get_raw_memory(self, number):
        return repr(self.memobj.memory[number])

    def sync_in(self):
#        self._get_type()
#        icf.IcomCloneModeRadio.sync_in(self)
#        self.mmap[0x1930] = self._isuhf and 1 or 0
        self.mmap = icf.read_file("/var/tmp/ice90u.icf")[1]
        self.process_mmap()

    def sync_out(self):
        self._get_type()
        icf.IcomCloneModeRadio.sync_out(self)
        return

    def freq_chirp2icom(self, freq):
        if chirp_common.is_fractional_step(freq):
            mult = 6250
        else:
            mult = 5000

        return (freq / mult, mult)

    def freq_icom2chirp(self, freq, mult):
        return freq * (6250 if mult else 5000)

    def get_skip(self, number):
        bank_item = self.memobj.banks[number]
        if bank_item.prog_skip:
            return "P"
        elif bank_item.mem_skip:
            return "S"
        return ""

    def set_skip(self, number, skip):
        bank_item = self.memobj.banks[number]
        if skip == "P":
            bank_item.prog_skip = 1
            bank_item.mem_skip = 1
        elif skip == "S":
            bank_item.prog_skip = 0
            bank_item.mem_skip = 1
        elif skip == "":
            bank_item.prog_skip = 0
            bank_item.mem_skip = 0
        else:
            raise errors.InvalidDataError("skip '%s' not supported" % skip)

    # returns (memobj.mem_item, is_special_channel, unique_idx)
    def get_mem_item(self, number):
        try:
            item_type = self.special[number]["item_type"]
            num = self.special[number]["num"]
            unique_idx = self.special[number]["uidx"]
            if item_type == "scan_edge":
                return (self.memobj.scan_edges[num], True, unique_idx)
            elif item_type == "call_chan":
                return (self.memobj.call_channels[num], True, unique_idx)
            elif item_type == "vfo_a":
                return (self.memobj.vfo_a_band[num], True, unique_idx)
            elif item_type == "vfo_b":
                return (self.memobj.vfo_b_band[num], True, unique_idx)
            else:
                raise errors.InvalidDataError("unknown special channel type '%s'" % item_type)
        except KeyError:
            return (self.memobj.memory[number], False, number)

    def get_memory(self, number):
        mem = chirp_common.Memory()

        (mem_item, special, unique_idx) = self.get_mem_item(number)

        mem.freq = self.freq_icom2chirp(mem_item.freq, mem_item.freq_mult)
        if mem.freq == 0:
            mem.empty = True
        else:
            mem.empty = False
            if special:
                mem.name = " " * ICX90_NAME_LENGTH
            else:
                mem.name = mem_item.name
            mem.rtone = chirp_common.TONES[(mem_item.tx_tone_hi << 4) + mem_item.tx_tone_lo]
            mem.ctone = chirp_common.TONES[mem_item.rx_tone]
            mem.dtcs = chirp_common.DTCS_CODES[mem_item.dtcs]
            mem.dtcs_polarity = ICX90_DTCS_POLARITIES[mem_item.dtcs_polarity]
            mem.offset = self.freq_icom2chirp(mem_item.offset_freq, mem_item.offset_freq_mult)
            mem.duplex = ICX90_DUPLEXES[mem_item.duplex]
            mem.tmode = ICX90_TONE_MODES[mem_item.tone_mode]
            mem_tuning_step = ICX90_TUNE_STEPS[mem_item.tune_step]
            mem.mode = ICX90_MODES[mem_item.mode]
            if not special:
                mem.skip = self.get_skip(number)
        if special:
           mem.extd_number = number
           mem.number = -len(self.special) + unique_idx
        else:
           mem.number = number

        return mem

    def set_memory(self, memory):
        (mem_item, special, unique_idx) = self.get_mem_item(number)
        if memory.empty:
            mem_item.set_raw("\x00" * MEM_ITEM_SIZE)
        else:
            (mem_item.freq, mem_item.freq_mult) = self.freq_chirp2icom(memory.freq)
            if special:
                mem_item.name = " " * ICX90_NAME_LENGTH
            else:
                mem_item.name = memory.name
            mem_item.tx_tone_hi = chirp_common.TONES.index(memory.rtone) >> 4
            mem_item.tx_tone_lo = chirp_common.TONES.index(memory.rtone) & 0x0f
            mem_item.rx_tone = chirp_common.TONES.index(memory.ctone)
            mem_item.dtcs = chirp_common.DTCS_CODES.index(memory.dtcs)
            mem_item.dtcs_polarity = ICX90_DTCS_POLARITIES.index(memory.dtcs_polarity)
            (mem_item.offset_freq, mem_item.offset_freq_mult) = self.freq_chirp2icom(memory.offset)
            mem_item.duplex = ICX90_DUPLEXES.index(memory.duplex)
            mem_item.tone_mode = ICX90_TONE_MODES.index(memory.tmode)
            mem_item.tune_step = ICX90_TUNE_STEPS.index(memory.tuning_step)
            mem_item.mode = ICX90_MODES.index(memory.mode)
            if not special:
                self.set_skip(number, memory.skip)

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