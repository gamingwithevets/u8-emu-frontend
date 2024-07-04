'''
This code below comes from the simlib.wasm and SimU8engine.dll of Casio's emulators,
and the SimBCD.dll from the LAPIS LEXIDE-Ω SDK.
The code was converted from Ghidra's decompiled C code and ILSpy's decompiled C# code to Python.
'''

import logging
import inspect

class BCD:
	def __init__(self, sim, log = True):
		self.sim = sim
		self.enlog = log

		self.calc_mode = 0
		self.dst = 0
		self.src = 0
		self.calc_en = False
		self.calc_en_d = False
		self.calc_en_dd = False
		self.divsn_mode = False
		self.div_mode = False
		self.mul_mode = False
		self.sft_mode = False
		self.calc_len = 0
		self.calc_pos = 0
		self.BMC = 0
		self.macro_state = 0
		self.macro_cnt = 0
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
			if self.enlog: self.log(f'Write to BCDRAM: {index+0xf000:04X}H = 0x{val & 0xff:02x}')
			#info = self.get_caller_info()
			#self.log(f'write to BCDRAM from {info.function} @ L{info.lineno}: {0xf000+index:04x} = old 0x{old:02x}, new 0x{val:02x}{" -> 0x"+format(val&0xff,"02x") if val&0xff!=val else ""}')
		self.sim.sim.c_config.sfr[index] = val

	def get_nibble(self, index): return self.sim.sim.c_config.sfr[index] >> 4 | self.sim.sim.c_config.sfr[index + 1] << 4

	def tick(self, addr, val):
		self.macro_state = 0x3f
		self.calc_en = False
		self.calc_en_d = False
		self.calc_en_dd = False
		if addr == 0x402:  # BCDCON
			a = val & 0xf
			if a == 0: return 1
			elif a >= 7: return 6
			else: return a
		elif addr == 0x404:  # BCDMCN
			return val & 0x1f
		elif addr in (0x400, 0x405):  # BCDCMD - BCDMCR
			self.sim.sim.c_config.sfr[addr] = val
			self.log(f'{"BCDCMD" if addr == 0x400 else "BCDMCR"} = 0x{self.sim.sim.c_config.sfr[addr]:02x}, CSR:PC = {self.sim.sim.core.regs.csr:X}:{self.sim.sim.core.regs.pc:04X}H')
			self.check_BCD_Register()
			while True:
				self.log(f'calc_en = {self.calc_en}, macro_state = 0x{self.macro_state:x}')
				self.data_repeat_flag = self.calc_en or self.macro_state != 0x3f
				self.state_manage()
				self.exec_calc()
				if not self.data_repeat_flag: break
			self.log('=== exiting function ===')
			return self.sim.sim.c_config.sfr[addr]

	@staticmethod
	def RegAdr(reg_num, reg_pos): return 0x480 + reg_num * 0x20 + reg_pos

	@staticmethod
	def RegPrev(reg_num): return (reg_num - 1 + 4) % 4

	@staticmethod
	def RegNext(reg_num): return (reg_num + 1) % 4

	def abcd44(self, m, a, b, ci):
		self.log(f'm = {m}, a = {a}, b = {b}, ci = {ci}')

		ci = (ci ^ 1 if m else ci) & 1
		num = 0
		for i in range(4):
			num2 = (a >> i * 4) & 0xf
			num3 = (b >> i * 4) & 0xf
			if m: num3 = (9 - num3) & 0xf
			num4 = num2 + num3 + ci
			ci = 1 if num4 >= 0xa else 0
			num4 = (num4 - (0xa if ci != 0 else 0)) & 0xf
			num |= num4 << i * 4
		ci = ci ^ 1 if m else ci
		result = (ci << 0x10) + num

		self.log(f'result = {result}')
		return result

	def calc_sl(self, ex):
		self.log(f'ex = {ex}, dst = {self.dst}, src = {self.src}')
		v = self.src
		if v == 0:
			for i in range(11): self.write_sfr(self.RegAdr(self.dst, 11 - i), self.get_nibble(self.RegAdr(self.dst, 10 - i)))
			self.write_sfr(self.RegAdr(self.dst, 0), (self.sim.sim.c_config.sfr[self.RegAdr(self.dst, 0)]) << 4 | (self.sim.sim.c_config.sfr[self.RegAdr(self.RegPrev(self.dst), 11)] if ex else 0) >> 4)
		elif v == 1:
			for i in range(11): self.write_sfr(self.RegAdr(self.dst, 11 - i), self.sim.sim.c_config.sfr[self.RegAdr(self.dst, 10 - i)])
			self.write_sfr(self.RegAdr(self.dst, 0), self.sim.sim.c_config.sfr[self.RegAdr(self.RegPrev(self.dst), 11)] if ex else 0)
		elif v == 2:
			for i in range(10): self.write_sfr(self.RegAdr(self.dst, 11 - i), self.sim.sim.c_config.sfr[self.RegAdr(self.dst, 9 - i)])
			for i in range(2): self.write_sfr(self.RegAdr(self.dst, i), self.sim.sim.c_config.sfr[self.RegAdr(self.RegPrev(self.dst), i + 10)] if ex else 0)
		elif v == 3:
			for i in range(8): self.write_sfr(self.RegAdr(self.dst, 11 - i), self.sim.sim.c_config.sfr[self.RegAdr(self.dst, 7 - i)])
			for i in range(4): self.write_sfr(self.RegAdr(self.dst, i), self.sim.sim.c_config.sfr[self.RegAdr(self.RegPrev(self.dst), i + 8)] if ex else 0)

	def calc_sr(self, ex):
		v = self.src
		self.log(f'ex = {ex}, dst = {self.dst}, src = {self.src}')
		if v == 0:
			for i in range(11): self.write_sfr(self.RegAdr(self.dst, i+1), self.get_nibble(self.RegAdr(self.dst, i)))
			self.write_sfr(self.RegAdr(self.dst, 11), self.sim.sim.c_config.sfr[self.RegAdr(self.RegNext(self.dst), 0)] if ex else 0 << 4 | self.sim.sim.c_config.sfr[self.RegAdr(self.dst, 11)] >> 4)
		elif v == 1:
			for i in range(11): self.write_sfr(self.RegAdr(self.dst, i), self.sim.sim.c_config.sfr[self.RegAdr(self.dst, i+1)])
			self.write_sfr(self.RegAdr(self.dst, 11), self.sim.sim.c_config.sfr[self.RegAdr(self.RegNext(self.dst), 0)] if ex else 0)
		elif v == 2:
			for i in range(10): self.write_sfr(self.RegAdr(self.dst, i), self.sim.sim.c_config.sfr[self.RegAdr(self.dst, i+2)])
			for i in range(10, 12): self.write_sfr(self.RegAdr(self.dst, i), self.sim.sim.c_config.sfr[self.RegAdr(self.RegPrev(self.dst), i-10)] if ex else 0)
		elif v == 3:
			for i in range(8): self.write_sfr(self.RegAdr(self.dst, i), self.sim.sim.c_config.sfr[self.RegAdr(self.dst, i+4)])
			for i in range(8, 12): self.write_sfr(self.RegAdr(self.dst, i), self.sim.sim.c_config.sfr[self.RegAdr(self.RegPrev(self.dst), i-8)] if ex else 0)

	def check_BCD_Register(self):
		self.check_BCDCMD()
		self.calc_len = self.sim.sim.c_config.sfr[0x402]
		self.check_BCDMCR()

	def check_BCDCMD(self):
		out = self.sim.sim.c_config.sfr[0x400]
		if out != 0xff:
			self.state_set((out >> 4) & 0xf, out >> 2 & 3, out & 3, self.macro_state)
			self.calc_pos = 0
			if self.calc_mode == 0:
				self.calc_en = False
				self.calc_en_d = True
			else: self.calc_en = True
			self.write_sfr(0x400, 0xff)

	def check_BCDMCR(self):
		out = self.sim.sim.c_config.sfr[0x405]
		self.log(f'BCDMCR = {out}')
		if out & 0x7f:
			self.BMC = out
			self.macro_cnt = self.sim.sim.c_config.sfr[0x404]
			self.write_sfr(0x405, 0)
			self.macro_state = 0xff

	def state_set(self, calc_mode, src, dst, macro_state):
		self.log(f'calc_mode = {calc_mode}, src = {src}, dst = {dst}, macro_state = 0x{macro_state:x}')
		self.calc_mode = calc_mode
		self.src = src
		self.dst = dst
		self.macro_state = macro_state

	def state_manage(self):
		if self.macro_state == 0xff and not self.calc_en: self.state_manage_init()
		elif any((self.mul_mode, self.div_mode, self.divsn_mode, self.sft_mode)) and not self.calc_en:
			if self.mul_mode: self.state_manage_mul()
			elif self.div_mode or self.divsn_mode: self.state_manage_div_divsn()
			elif self.sft_mode: self.state_manage_sft()
			if any((self.mul_mode, self.div_mode, self.divsn_mode)): self.calc_en = (self.src | self.dst | self.calc_mode) != 0
			self.calc_pos = 0

		self.write_sfr(0x405, (self.sim.sim.c_config.sfr[0x405] & 0x7f) | (0x80 if any((self.mul_mode, self.div_mode, self.divsn_mode, self.sft_mode)) else 0))
		self.calc_en_dd = self.calc_en_d
		self.calc_en_d = self.calc_en

	def state_manage_init(self):
		if self.mul_mode: self.state_set(13, 0, 0, self.a())
		elif self.div_mode: self.state_set(8, 0, 1, 0x18)
		elif self.divsn_mode: self.state_set(12, 0, 1, 0x18)
		else:
			v = self.BMC >> 1 & 0xf
			if v == 1:
				if self.BMC & 1: self.state_set(13, 0, 0, self.a())
				else: self.state_set(11, 1, 3, 24)
				self.mul_mode = True
			elif v == 2:
				if self.BMC & 1: self.state_set(8, 0, 1, 24)
				else: self.state_set(11, 1, 3, 16)
				self.div_mode = True
			elif v == 3:
				if self.BMC & 1: self.state_set(12, 0, 1, 24)
				else: self.state_set(11, 1, 3, 32)
				self.div_mode = True
			elif v in (4, 5, 6, 7):
				self.macro_cnt += 1
				self.state_set(8 if self.BMC & 0xc == 8 else 9, 3 if self.macro_cnt >= 8 else (2 if macro_cnt >= 4 else (1 if macro_cnt >= 2 else 0)), self.BMC & 3, 0)
				self.macro_cnt -= 1 << self.src
				self.sft_mode = self.macro_cnt != 0
			else: self.state_set(0, 0, 0, self.macro_state)

		self.calc_pos = 0
		self.calc_en = True
		self.BMC = 0

	def state_manage_mul(self):
		v = self.macro_state
		if v == 0x18: self.state_set(11, 1, 2, 0x19)
		elif v == 0x19: self.state_set(1, 2, 2, 0x1a)
		elif v == 0x1a: self.state_set(1, 2, 2, 0x1b)
		elif v == 0x1b: self.state_set(10, 0, 1, 0x1c)
		elif v == 0x1c: self.state_set(13, 0, 0, self.a())
		elif v == 0x20: self.state_set(9, 0, 1, 0x3f)
		elif v in range(0x21, 0x2a): self.state_set(9, 0, 1, v + 0x10)
		elif v == 0x31: self.state_set(1, 3, 1, 0x3f)
		elif v == 0x32: self.state_set(1, 3, 1, 0x31)
		elif v == 0x33: self.state_set(2, 3, 1, 0x34)
		elif v == 0x34: self.state_set(1, 2, 1, 0x3f)
		elif v == 0x35: self.state_set(1, 2, 1, 0x31)
		elif v == 0x36: self.state_set(1, 2, 1, 0x32)
		elif v == 0x37: self.state_set(1, 2, 1, 0x33)
		elif v == 0x38: self.state_set(1, 2, 1, 0x34)
		elif v == 0x39: self.state_set(1, 2, 1, 0x35)
		else:
			self.state_set(0, 0, 0, 0x3f)
			self.mul_mode = self.macro_cnt != 0

		if self.macro_state == 0x3f and self.macro_cnt:
			self.macro_cnt -= 1
			self.macro_state = 0xff

	def state_manage_div_divsn(self):
		v = self.macro_state
		val = 1 if self.sim.sfr[0x410] & 0x80 != 0 else 0
		if v in (0, 3, 6): self.state_set(0, 0, 0, 0x3f)
		elif v == 1:
			if val == 0: self.state_set(0, 0, 0, 0x3f)
			else: self.state_set(1, 3, 1, 0)
		elif v == 2:
			if val == 0: self.state_set(0, 0, 0, 0x3f)
			else: self.state_set(1, 3, 1, 1)
		elif v == 4:
			if val == 0: self.state_set(0, 0, 0, 0x3f)
			else: self.state_set(1, 3, 1, 3)
		elif v == 5:
			if val == 0: self.state_set(0, 0, 0, 0x3f)
			else: self.state_set(1, 3, 1, 4)
		elif v == 7:
			if val == 0: self.state_set(0, 0, 0, 0x3f)
			else: self.state_set(1, 3, 1, 6)
		elif v == 8:
			if val == 0: self.state_set(0, 0, 0, 0x3f)
			else: self.state_set(1, 3, 1, 7)
		elif v == 9:
			if val == 0: self.state_set(1, 3, 1, 8)
			else: self.state_set(0, 0, 0, 0x3f)
		elif v == 0x10: self.state_set(11, 1, 2, 0x11)
		elif v == 0x11: self.state_set(1, 1, 2, 0x12)
		elif v == 0x12: self.state_set(1, 1, 2, 0x13)
		elif v == 0x13: self.state_set(11, 0, 1, 0x14)
		elif v == 0x14: self.state_set(10, 0, 0, 0x18)
		elif v == 0x18: self.state_set(8, 0, 0, 0x19)
		elif v == 0x19: self.state_set(2, 2, 1, 0x1a)
		elif v == 0x1a:
			if val == 0: self.state_set(1, 3, 1, 2)
			else: self.state_set(2, 2, 1, 0x1b)
		elif v == 0x1b:
			if val == 0: self.state_set(1, 3, 1, 5)
			else: self.state_set(2, 2, 1, 9)
		elif v == 0x20: self.state_set(11, 1, 2, 0x21)
		elif v == 0x21: self.state_set(1, 1, 2, 0x22)
		elif v == 0x22: self.state_set(1, 1, 2, 0x23)
		elif v == 0x23: self.state_set(12, 3, 1, 0x24)
		elif v == 0x24: self.state_set(8, 3, 0, 0x19)

		if v == 0x3f:
			addr = self.RegAdr(0, 0)
			self.write_sfr(addr, self.sim.sim.c_config.sfr[addr] & 0xf0 | v & 0xf)
			if self.macro_cnt == 0:
				self.divsn_mode = False
				self.div_mode = False
			else:
				self.macro_cnt -= 1
				if self.div_mode: self.state_set(8, 0, 1, 0x18)
				elif self.divsn_mode: self.state_set(12, 0, 1, 0x18)

	def state_manage_sft(self):
		self.src = 3 if self.macro_cnt >= 8 else (2 if macro_cnt >= 4 else (1 if macro_cnt >= 2 else 0))
		self.macro_cnt -= 1 << self.src
		if self.macro_cnt == 0: self.sft_mode = False
		self.calc_en = True
		self.macro_state = 0

	def a(self): return self.sim.sim.c_config.sfr[self.RegAdr(0, 0)] & 0xf | 0x20

	def exec_calc(self):
		self.exec_Add_Sub()
		self.exec_Sft_Con_Cp()
		self.update_LLZ_MLZ()
		self.check_calc_end()

	def exec_Add_Sub(self):
		num = 0
		if self.calc_en and not self.calc_pos:
			num2 = 1
			num3 = 0
			flag = self.calc_mode in (1, 2)
			for i in range(0, self.calc_len, 2):
				self.log(f'i = {i}, calc_len = {self.calc_len}, flag = {flag}, num = {num}, num2 = {num2}, num3 = {num3}')
				a = self.read_word(self.RegAdr(self.dst, i*2))
				b = self.read_word(self.RegAdr(self.src, i*2))
				num = self.abcd44(self.calc_mode == 2, a, b, num3)
				num3 = (num >> 16) & 1
				num2 = 1 if num & 0xffff == 0 and num2 != 0 else 0
				if flag: self.write_word(self.RegAdr(self.dst, i*2), num)
				a = self.read_word(self.RegAdr(self.dst, i*2))
				b = self.read_word(self.RegAdr(self.src, i*2))
				num = self.abcd44(self.calc_mode == 2, a, b, num3)
				if (i+1 != self.calc_len): 
					num3 = (num >> 16) & 1
					num2 = 1 if num & 0xffff == 0 and num2 != 0 else 0
				self.write_sfr(0x410, (num3 << 7) | (num2 << 6))
				if flag:
					if i+1 == self.calc_len: num = 0
					self.write_word(self.RegAdr(self.dst, i*2+2), num)

		if self.calc_mode in (1, 2) and (self.calc_en_dd or self.calc_en_d):
			self.log(f'calc_pos = {self.calc_pos} -> {self.calc_pos + 2}')
			self.calc_pos += 2
			if self.calc_pos >= self.calc_len: self.calc_en = False

	def exec_Sft_Con_Cp(self):
		v = self.calc_mode & (0xf if self.calc_en else 0)
		self.log(f'v = {v}')
		if v == 8: self.calc_sl(False)
		elif v == 9: self.calc_sr(False)
		elif v == 10:
			for i in range(1, 12): self.write_sfr(self.RegAdr(self.dst, i), 0)
			self.write_sfr(self.RegAdr(self.dst, 0), 5 if self.src == 3 else self.src)
		elif v == 11:
			for i in range(12): self.write_sfr(self.RegAdr(self.dst, i), self.sim.sim.c_config.sfr[self.RegAdr(self.src, i)])
		elif v == 12: self.calc_sl(True)
		elif v == 13: self.calc_sr(True)

	def update_LLZ_MLZ(self):
		if self.sim.sim.c_config.sfr[0x400] & 0xf0 == 0 and (self.calc_en_d or not self.calc_en_dd):
			end = 0
			for i in range(11, -1, -1):
				b = self.sim.sim.c_config.sfr[self.RegAdr(self.dst, i)]
				if i < self.calc_len * 2 and b & 0xf0 != 0: break
				end += 1
				if i < self.calc_len * 2 and b & 0xf != 0: break
				end += 1

			start = 0
			for i in range(12):
				b = self.sim.sim.c_config.sfr[self.RegAdr(self.dst, i)]
				if i < self.calc_len * 2 and b & 0xf != 0: break
				start += 1
				if i < self.calc_len * 2 and b & 0xf0 != 0: break
				start += 1

			self.log(f'BCDLLZ = {start}')
			self.log(f'BCDMLZ = {end}')

			self.write_sfr(0x414, start)
			self.write_sfr(0x415, end)

	def check_calc_end(self):
		self.log(f'calc_mode = {self.calc_mode}')
		if self.calc_mode & 8 != 0 or self.calc_mode == 0:
			self.calc_en = False
			self.calc_pos = 6
