'''
This code below comes from the simlib.wasm and SimU8engine.dll of Casio's emulators.
The code was converted from Ghidra's decompiled C code to Python.

To use, place this script in the root of the u8-emu-frontend repo.
'''

import logging
import inspect

class BCD:
	def __init__(self, sim, log = True):
		self.sim = sim
		self.enlog = log

		self.data_operator = 0
		self.data_type_1 = 0
		self.data_type_2 = 0
		self.param1 = False
		self.param2 = False
		self.param3 = False
		self.data_a = False
		self.data_b = False
		self.data_c = False
		self.data_d = False
		self.f402_copy = 0
		self.param4 = 0
		self.f405_copy = 0
		self.data_mode = 0
		self.f404_copy = 0
		self.data_repeat_flag = False

	def get_caller_info(self): return inspect.stack()[2]

	def log(self, string):
		if self.enlog: logging.info(f'{inspect.currentframe().f_back.f_code.co_name}: {string}')

	def read_word(self, index): return self.sim.sim.c_config.sfr[index + 1] << 8 | self.sim.sim.c_config.sfr[index]

	def write_word(self, index, val):
		#old = self.sim.sim.c_config.sfr[index + 1] << 8 | self.sim.sim.c_config.sfr[index]
		#if index in range(0x480, 0x500) and old != val:
			#info = self.get_caller_info()
			#self.log(f'write to BCDRAM from {info.function} @ L{info.lineno}: {0xf000+index:04x} = old 0x{old:04x}, new 0x{val:04x}{" -> 0x"+format(val&0xffff,"04x") if val&0xffff!=val else ""}')
		#self.sim.sim.c_config.sfr[index + 1] = val >> 8; self.sim.sim.c_config.sfr[index] = val & 0xff
		self.write_sfr(index, val & 0xff)
		self.write_sfr(index + 1, val >> 8)

	def write_sfr(self, index, val):
		#old = self.sim.sim.c_config.sfr[index]
		if index in range(0x480, 0x500):# and old != val:
			if self.enlog: print(f'Write to BCDRAM: {index+0xf000:04X}H = 0x{val & 0xff:02x}')
			#info = self.get_caller_info()
			#self.log(f'write to BCDRAM from {info.function} @ L{info.lineno}: {0xf000+index:04x} = old 0x{old:02x}, new 0x{val:02x}{" -> 0x"+format(val&0xff,"02x") if val&0xff!=val else ""}')
		self.sim.sim.c_config.sfr[index] = val

	def get_nibble(self, index): return self.sim.sim.c_config.sfr[index] >> 4 | self.sim.sim.c_config.sfr[index + 1] << 4

	def tick(self, addr, val):
		self.data_mode = 0x3f
		self.param1 = False
		self.param2 = False
		self.param3 = False
		if addr == 0x402:
			out = val & 0xf
			vin = out
			if out == 0: vin = 1
			if out >= 7: vin = 6
			return vin
		elif addr == 0x404: return val & 0x1f
		elif addr in (0x400, 0x405):
			self.sim.sim.c_config.sfr[addr] = val
			self.log(f'f400 = 0x{self.sim.sim.c_config.sfr[0x400]:02x}, CSR:PC = {self.sim.sim.core.regs.csr:X}:{self.sim.sim.core.regs.pc:04X}H')
			self.unnamed_function_823()
			while True:
				self.log(f'param1 = {self.param1}, data_mode = 0x{self.data_mode:x}')
				self.data_repeat_flag = not (not self.param1 and self.data_mode == 0x3f)
				self.f405_control()
				self.param3 = self.param2
				self.param2 = self.param1
				self.data_operate()
				if not self.data_repeat_flag: break
			self.log('=== exiting function ===')
			return self.sim.sim.c_config.sfr[addr]

	@staticmethod
	def get_bcdram_addr(y, x): return y*0x20 + x + 0x480

	@staticmethod
	def unnamed_function_828(param2): return (param2 + 3) & 3

	@staticmethod
	def unnamed_function_827(param2): return (param2 + 1) & 3

	def calculate(self, tmp, val1, val2, flag):
		if flag: tmp ^= 1
		tmp &= 1

		val1_tmp = val1 & 0xf
		val2_tmp = val2 & 0xf

		if flag: val2_tmp = (0xfffffff9 - val2_tmp) & 0xf

		val2_tmp += val1_tmp
		val2_tmp += tmp

		f = 0
		if val2_tmp >= 0xa:
			val2_tmp -= 0xa
			f = 1

		val2_tmp &= 0xf
		tmp = val2_tmp
		val1_tmp = (val1 >> 4) & 0xf
		val2_tmp = (val2 >> 4) & 0xf

		if flag: val2_tmp = (0xfffffff9 - val2_tmp) & 0xf

		val1_tmp += val2_tmp
		val1_tmp += f
		f = 0

		if val1_tmp >= 0xa:
			val1_tmp -= 0xa
			f = 1

		val1_tmp = val1_tmp << 4
		tmp |= val1_tmp & 0xF0
		val1_tmp = (val1 >> 8) & 0xf
		val2_tmp = (val2 >> 8) & 0xf

		if flag: val2_tmp = (0xfffffff9 - val2_tmp) & 0xf

		val1_tmp += val2_tmp
		val1_tmp += f
		f = 0

		if val1_tmp >= 0xa:
			val1_tmp -= 0xa
			f = 1

		val1_tmp = (val1_tmp << 8) & 0xf00
		val1 = (val1 >> 12) & 0xf
		val2 = (val2 >> 12) & 0xf
		tmp |= val1_tmp
		if flag: val2 = (0xfffffff9 - val2) & 0xf

		val1 += val2
		val1 += f
		f = 0

		if val1 >= 0xa:
			val1 -= 0xa
			f = 1

		val1 = (val1 << 12) & 0xf000
		tmp |= val1
		if flag: f ^= 1

		f = f << 0x10
		f += tmp

		return f

	def shift_left(self, param2):
		v = self.data_type_2
		self.log(f'param2 = {param2}, data_type_1 = {self.data_type_1}, data_type_2 = {v}')
		if v == 0:
			for i in range(11): self.write_sfr(self.get_bcdram_addr(self.data_type_1, 11 - i), self.get_nibble(self.get_bcdram_addr(self.data_type_1, 10 - i)))
			self.write_sfr(self.get_bcdram_addr(self.data_type_1, 0), (self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, 0)]) << 4 | (self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.unnamed_function_828(self.data_type_1), 11)] if param2 else 0) >> 4)
		elif v == 1:
			for i in range(11): self.write_sfr(self.get_bcdram_addr(self.data_type_1, 11 - i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, 10 - i)])
			self.write_sfr(self.get_bcdram_addr(self.data_type_1, 0), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.unnamed_function_828(self.data_type_1), 11)] if param2 else 0)
		elif v == 2:
			for i in range(10): self.write_sfr(self.get_bcdram_addr(self.data_type_1, 11 - i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, 9 - i)])
			for i in range(2): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.unnamed_function_828(self.data_type_1), i + 10)] if param2 else 0)
		elif v == 3:
			for i in range(8): self.write_sfr(self.get_bcdram_addr(self.data_type_1, 11 - i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, 7 - i)])
			for i in range(4): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.unnamed_function_828(self.data_type_1), i + 8)] if param2 else 0)

	def shift_right(self, param2):
		v = self.data_type_2
		self.log(f'param2 = {param2}, data_type_1 = {self.data_type_1}, data_type_2 = {v}')
		if v == 0:
			for i in range(11): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i+1), self.get_nibble(self.get_bcdram_addr(self.data_type_1, i)))
			self.write_sfr(self.get_bcdram_addr(self.data_type_1, 11), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.unnamed_function_827(self.data_type_1), 0)] if param2 else 0 << 4 | self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, 11)] >> 4)
		elif v == 1:
			for i in range(11): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, i+1)])
			self.write_sfr(self.get_bcdram_addr(self.data_type_1, 11), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.unnamed_function_827(self.data_type_1), 0)] if param2 else 0)
		elif v == 2:
			for i in range(10): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, i+2)])
			for i in range(10, 12): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.unnamed_function_828(self.data_type_1), i-10)] if param2 else 0)
		elif v == 3:
			for i in range(8): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, i+4)])
			for i in range(8, 12): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.unnamed_function_828(self.data_type_1), i-8)] if param2 else 0)

	def unnamed_function_823(self):
		out = self.sim.sim.c_config.sfr[0x400]
		if out != 0xff:
			self.generate_params(out >> 4, out >> 2 & 3, out & 3, self.data_mode)
			self.param4 = 0
			if self.data_operator == 0:
				self.param1 = False
				self.param2 = True
			else: self.param1 = True
			self.write_sfr(0x400, 0xff)
		self.f402_copy = self.sim.sim.c_config.sfr[0x402]
		out = self.sim.sim.c_config.sfr[0x405]
		if out & 0x7f:
			self.f405_copy = out
			self.f404_copy = self.sim.sim.c_config.sfr[0x404]
			self.write_sfr(0x405, 0)
			self.data_mode = 0xff

	def generate_params(self, data_operator, data_type_2, data_type_1, data_mode):
		self.log(f'data_operator = {data_operator}, data_type_1 = {data_type_1}, data_type_2 = {data_type_2}, data_mode = {data_mode}')
		self.data_operator = data_operator
		self.data_type_2 = data_type_2
		self.data_type_1 = data_type_1
		self.data_mode = data_mode

	def f405_control(self):
		if self.data_mode == 0xff and not self.param1: self.unnamed_function_820()
		else:
			if any((self.data_c, self.data_b, self.data_a, self.data_d)) and not self.param1:
				if self.data_c: self.unnamed_function_819()
				elif not any(self.data_b, self.data_a): self.unnamed_function_816()
				else: self.unnamed_function_817()
			if any((self.data_c, self.data_b, self.data_a)): self.param1 = bool(self.data_type_2 | self.data_type_1 | self.data_operator)
			self.param4 = 0

		self.write_sfr(0x405, self.sim.sim.c_config.sfr[0x405] & 0x7f | (0x80 if any((self.data_c, self.data_b, self.data_a, self.data_d)) else 0))

	def unnamed_function_820(self):
		if self.data_c: self.generate_params(13, 0, 0, self.unnamed_function_815())
		elif self.data_b: self.generate_params(8, 0, 1, 0x18)
		elif self.data_a: self.generate_params(12, 0, 1, 0x18)
		else:
			v = self.f405_copy
			var = v >> 1 & 0xf
			if var == 1:
				if v & 1: self.generate_params(13, 0, 0, self.unnamed_function_815())
				else: self.generate_params(11, 1, 3, 0x18)
				self.data_c = True
			elif var == 2:
				if v & 1: self.generate_params(8, 0, 1, 0x18)
				else:self.generate_params(11, 1, 3, 0x10)
				self.data_b = True
			elif var == 3:
				if v & 1: self.generate_params(12, 0, 1, 0x18)
				else: self.generate_params(11, 1, 3, 0x20)
				self.data_a = True
			elif var in range(4, 8):
				vv = self.f404_copy + 1
				self.f404_copy = vv
				var_ = (int(1 < vv) if vv < 4 else 2) if vv < 8 else 3
				self.generate_params((v & 0xc != 8) + 8, var_, v & 3, 0)
				self.f404_copy += (0xff << (self.data_type_2 & 0x1f))
				if self.f404_copy: self.data_d = True
				else:
					self.data_d = False
					self.data_mode = 0x3f
			else: self.generate_params(0, 0, 0, self.data_mode)
		self.param1 = True
		self.param4 = 0
		self.f405_copy = 0

	def unnamed_function_819(self):
		v = self.data_mode
		if v == 0x18: self.generate_params(11, 1, 2, 0x19)
		elif v == 0x19: self.generate_params(1, 2, 2, 0x1a)
		elif v == 0x1a: self.generate_params(1, 2, 2, 0x1b)
		elif v == 0x1b: self.generate_params(10, 0, 1, 0x1c)
		elif v == 0x1c: self.generate_params(13, 0, 0, self.unnamed_function_815())
		elif v == 0x20: self.generate_params(9, 0, 1, 0x3f)
		elif v in range(0x21, 0x2a): self.generate_params(9, 0, 1, self.unnamed_function_814(v))
		elif v == 0x31: self.generate_params(1, 3, 1, 0x3f)
		elif v == 0x32: self.generate_params(1, 3, 1, 0x31)
		elif v == 0x33: self.generate_params(2, 3, 1, 0x34)
		elif v == 0x34: self.generate_params(1, 2, 1, 0x3f)
		elif v == 0x35: self.generate_params(1, 2, 1, 0x31)
		elif v == 0x36: self.generate_params(1, 2, 1, 0x32)
		elif v == 0x37: self.generate_params(1, 2, 1, 0x33)
		elif v == 0x38: self.generate_params(1, 2, 1, 0x34)
		elif v == 0x39: self.generate_params(1, 2, 1, 0x35)
		else:
			self.generate_params(0, 0, 0, 0x3f)
			self.data_c = self.f404_copy != 0

		if self.data_mode == 0x3f and self.f404_copy:
			self.f404_copy -= 1
			self.data_mode = 0xff

	def unnamed_function_817(self):
		v = self.data_mode
		val = self.sim.sfr[0x410] >> 7
		if v in (0, 3, 6): self.generate_params(0, 0, 0, 0x3f)
		elif v == 1:
			if val: self.generate_params(1, 3, 1, 0)
			else: self.generate_params(0, 0, 0, 0x3f)
		elif v == 2:
			if val: self.generate_params(1, 3, 1, 1)
			else: self.generate_params(0, 0, 0, 0x3f)
		elif v == 4:
			if val: self.generate_params(1, 3, 1, 3)
			else: self.generate_params(0, 0, 0, 0x3f)
		elif v == 5:
			if val: self.generate_params(1, 3, 1, 4)
			else: self.generate_params(0, 0, 0, 0x3f)
		elif v == 7:
			if val: self.generate_params(1, 3, 1, 6)
			else: self.generate_params(0, 0, 0, 0x3f)
		elif v == 8:
			if val: self.generate_params(1, 3, 1, 7)
			else: self.generate_params(0, 0, 0, 0x3f)
		elif v == 9:
			if val: self.generate_params(0, 0, 0, 0x3f)
			else: self.generate_params(1, 3, 1, 8)
		elif v == 0x10: self.generate_params(11, 1, 2, 0x11)
		elif v == 0x11: self.generate_params(1, 1, 2, 0x12)
		elif v == 0x12: self.generate_params(1, 1, 2, 0x13)
		elif v == 0x13: self.generate_params(11, 0, 1, 0x14)
		elif v == 0x14: self.generate_params(10, 0, 0, 0x18)
		elif v == 0x18: self.generate_params(8, 0, 0, 0x19)
		elif v == 0x19: self.generate_params(2, 2, 1, 0x1a)
		elif v == 0x1a:
			if val: self.generate_params(1, 3, 1, 2)
			else: self.generate_params(2, 2, 1, 0x1b)
		elif v == 0x1b:
			if val: self.generate_params(1, 3, 1, 5)
			else: self.generate_params(2, 2, 1, 9)
		elif v == 0x20: self.generate_params(11, 1, 2, 0x21)
		elif v == 0x21: self.generate_params(1, 1, 2, 0x22)
		elif v == 0x22: self.generate_params(1, 1, 2, 0x23)
		elif v == 0x23: self.generate_params(12, 3, 1, 0x24)
		elif v == 0x24: self.generate_params(8, 3, 0, 0x19)

		if v == 0x3f:
			addr = self.get_bcdram_addr(0, 0)
			self.write_sfr(addr, ((self.sim.sim.c_config.sfr[addr] ^ v) & 0xf) ^ self.sim.sim.c_config.sfr[addr]);
			if self.f404_copy:
				self.f404_copy -= 1
				if self.data_b: self.generate_params(8, 0, 1, 0x18)
				elif self.data_a: self.generate_params(12, 0, 1, 0x18)
			else:
				self.data_a = False
				self.data_b = False

	def unnamed_function_816(self):
		v = self.f404_copy
		va = (int(1 < v) if v < 4 else 2) if v < 8 else 3

		self.generate_params(self.data_operator, va, self.data_type_1, 0)
		self.param1 = True
		self.f404_copy += (0xff << (self.data_type_2 & 0x1f))
		if not self.f404_copy:
			self.data_mode = 0x3f
			self.data_d = False

	def unnamed_function_815(self): return self.sim.sim.c_config.sfr[self.get_bcdram_addr(0, 0)] & 0xf | 0x20

	def unnamed_function_814(self, param2): return param2 + 0x10

	def data_operate(self):
		if self.param1 and self.param4 == 0 and self.f402_copy != 0:
			tmp = 0
			store_results = self.data_operator in (1, 2)
			f410_tmp = 1
			self.log(f'f402_copy = {self.f402_copy}, data_operator = {self.data_operator}, data_type_1 = 0x{self.data_type_1:02x}, data_type_2 = 0x{self.data_type_2:02x}')
			for i in range(self.f402_copy // 2):
				offset = i*4
				addr = self.get_bcdram_addr(self.data_type_1, offset)
				self.log(f'offset = 0x{offset:02x}, addr1 = {0xf000+addr:04x}')
				res = self.calculate(tmp, self.read_word(addr), self.read_word(self.get_bcdram_addr(self.data_type_2, offset)), self.data_operator == 2)
				tmp = (res >> 16) & 1
				f410_tmp = int(res & 0xffff == 0 and f410_tmp != 0)
				if store_results: self.write_word(addr, res)
				offset += 2
				addr = self.get_bcdram_addr(self.data_type_1, offset)
				self.log(f'offset = 0x{offset:02x}, addr1 = {0xf000+addr:04x}')
				res = self.calculate(tmp, self.read_word(addr), self.read_word(self.get_bcdram_addr(self.data_type_2, offset)), self.data_operator == 2)
				if i * 2 + 1 != self.f402_copy:
					tmp = (res >> 16) & 1
					f410_tmp = int(not res & 0xffff and f410_tmp)
				self.write_sfr(0x410, ((tmp * 2) | f410_tmp) << 6)
				if store_results: self.write_word(addr, 0 if i*2+1 == self.f402_copy else res)

		if self.data_operator in (1, 2) and (self.param2 or self.param3):
			self.param4 += 2
			if self.f402_copy <= self.param4: self.param1 = False	

		sign = self.data_operator & 0xf if self.param1 else 0
		if sign == 8: self.shift_left(False)
		elif sign == 9: self.shift_right(False)
		elif sign == 10:
			for i in range(1, 12): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), 0)
			self.write_sfr(self.get_bcdram_addr(self.data_type_1, 0), 5 if self.data_type_2 == 3 else self.data_type_2)
		elif sign == 11:
			for i in range(12): self.write_sfr(self.get_bcdram_addr(self.data_type_1, i), self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_2, i)])
		elif sign == 12: self.shift_left(True)
		elif sign == 13: self.shift_right(True)

		if self.sim.sim.c_config.sfr[0x400] & 0xf0 == 0 or (self.param3 and not self.param2):
			end = 0
			brk = False
			for i in range(11, -1, -1):
				if brk: break
				out = self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, i)]
				if i < self.f402_copy * 2:
					if out & 0xf0: brk = True
					else:
						end += 1
						if out & 0xf: brk = True
						else: end += 1
				else: end += 2

			start = 0
			brk = False
			for i in range(12):
				if brk: break
				out = self.sim.sim.c_config.sfr[self.get_bcdram_addr(self.data_type_1, i)]
				if i < self.f402_copy * 2:
					if out & 0xf: brk = True
					else:
						start += 1
						if out & 0xf0: brk = True
						else: start += 1
				else: start += 2

			self.write_sfr(0x414, start)
			self.write_sfr(0x415, end)

		if self.sim.sim.c_config.sfr[0x400] & 8 or not self.sim.sim.c_config.sfr[0x400]:
			self.param1 = False
			self.param4 = 6
