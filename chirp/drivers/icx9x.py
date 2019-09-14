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

import logging

import icf, icx9x_ll
#from chirp.drivers import icf, icx9x_ll
from chirp import chirp_common, errors, directory

LOG = logging.getLogger(__name__)

class ICx9xBankModel(icf.IcomIndexedBankModel):
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
class ICx9xRadio(icf.IcomCloneModeRadio):
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
        return icx9x_ll.get_bank(self._mmap, loc)

    def _set_bank(self, loc, bank):
        return icx9x_ll.set_bank(self._mmap, loc, bank)

    def _get_bank_index(self, loc):
        return icx9x_ll.get_bank_index(self._mmap, loc)

    def _set_bank_index(self, loc, index):
        return icx9x_ll.set_bank_index(self._mmap, loc, index)

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_settings = False
        rf.has_name = True
        rf.has_bank = False
        rf.has_bank_index = True
        rf.has_bank_names = False
        rf.memory_bounds = (0, 499)
#        rf.valid_power_levels = [chirp_common.PowerLevel("High", watts = 5.0),
#                                 chirp_common.PowerLevel("Low", watts = 0.5)]
        rf.valid_modes = list(icx9x_ll.ICX9X_MODES)
        rf.valid_tmodes = list(icx9x_ll.ICX9X_TONE_MODES)
        rf.valid_duplexes = list(icx9x_ll.ICX9X_DUPLEXES)[:-1]
        rf.valid_tuning_steps = list(icx9x_ll.ICX9X_TUNE_STEPS)
        rf.valid_bands = [(495000, 999990000)]
        rf.valid_skips = ["", "S"]
        rf.valid_name_length = 6
#        rf.valid_special_chans = sorted(icx9x_ll.ICx9x_SPECIAL.keys())

        return rf

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
        return icx9x_ll.get_memory(self._mmap, number)

    def set_memory(self, memory):
        if not self._mmap:
            self.sync_in()
        self._mmap = icx9x_ll.set_memory(self._mmap, memory)

    def get_raw_memory(self, number):
        return icx9x_ll.get_raw_memory(self._mmap, number)

    def get_bank_model(self):
        return ICx9xBankModel(self)

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
    ser = ICx9xRadio(serial.Serial(port=None,
                                   baudrate=9600, timeout=0.1))
    _read_icf(ser)
    print(ser.get_index_bounds())

if __name__ == "__main__":
    _test()
