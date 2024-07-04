import functools

class Screen:
	def __init__(self, sim, scr):
		self.sim = sim
		self.scr = scr

		self.hwid = self.sim.sim.c_config.hwid
		self.real_hw = self.sim.sim.c_config.real_hw
		self.is_5800p = self.hwid == 2 and self.sim.sim.c_config.is_5800p
		self.screen = [[0]*self.scr[4] for i in range(self.scr[2])]

		self.draw_hi_scr = False

		if self.hwid == 5 and self.real_hw: self.sim.sim.register_sfr(0x37, 1, self.scrselect)
		if self.hwid != 6:
			for i in range(self.scr[2]): self.sim.sim.register_sfr(0x800 + i*self.scr[0], self.scr[1], self.write_screen)
			self.sim.sim.register_sfr(0x30, 1, lambda addr, val: val & 7)
			self.sim.sim.register_sfr(0x31, 1, lambda addr, val: val & 7)
			self.sim.sim.register_sfr(0x32, 1, lambda addr, val: val & 0x1f)
			self.sim.sim.register_sfr(0x33, 1, lambda addr, val: val & 7)

	def scrselect(self, addr, val):
		self.draw_hi_scr = bool(val & 4)
		return val

	def write_screen(self, addr, val):
		y = (addr - 0x800) // self.scr[0]
		x = ((addr - 0x800) % self.scr[0]) * 8

		pix = (2 if self.draw_hi_scr else 1) if self.hwid == 5 else 3

		for i in range(8):
			if (val & (1 << (~i & 7))): self.screen[y][x+i] |= pix
			else: self.screen[y][x+i] &= ~pix

		return val

	def update_emu_hi_scr(self):
		if self.hwid == 5 and not self.real_hw:
			for i in range(self.scr[2]):
				data = self.sim.read_dmem_bytes(0x9000 + i*self.scr[0], self.scr[1], 8)
				for j in range(self.scr[1]):
					for k in range(8):
						if data[j] & (1 << (~k & 7)): self.screen[i][j*8+k] |= 2
						else: self.screen[i][j*8+k] &= ~2

	def get_scr_data(self): return self._get_scr_data(tuple(tuple(_) for _ in self.screen))

	@functools.lru_cache
	def _get_scr_data(self, screen):
		if self.hwid == 0: screen_data_status_bar = [
			self.get_screen_bit(0x11, 6),  # SHIFT
			self.get_screen_bit(0x11, 2),  # MODE
			self.get_screen_bit(0x12, 6),  # STO
			self.get_screen_bit(0x12, 2),  # RCL
			self.get_screen_bit(0x13, 6),  # hyp
			self.get_screen_bit(0x13, 2),  # M
			self.get_screen_bit(0x14, 6),  # K
			self.get_screen_bit(0x14, 2),  # DEG
			self.get_screen_bit(0x15, 6),  # RAD
			self.get_screen_bit(0x15, 2),  # GRA
			self.get_screen_bit(0x16, 4),  # FIX
			self.get_screen_bit(0x16, 2),  # SCI
			self.get_screen_bit(0x16, 0),  # SD
			]
		elif self.is_5800p: screen_data_status_bar = [
			self.get_screen_bit(0,   4),  # [S]
			self.get_screen_bit(0,   2),  # [A]
			self.get_screen_bit(1,   4),  # M
			self.get_screen_bit(1,   1),  # STO
			self.get_screen_bit(2,   6),  # RCL
			self.get_screen_bit(3,   6),  # SD
			self.get_screen_bit(4,   7),  # REG
			self.get_screen_bit(5,   6),  # FMLA
			self.get_screen_bit(5,   4),  # PRGM
			self.get_screen_bit(5,   1),  # END
			self.get_screen_bit(7,   5),  # [D]
			self.get_screen_bit(7,   1),  # [R]
			self.get_screen_bit(8,   4),  # [G]
			self.get_screen_bit(8,   0),  # FIX
			self.get_screen_bit(9,   5),  # SCI
			self.get_screen_bit(0xa, 6),  # Math
			self.get_screen_bit(0xa, 3),  # ▼
			self.get_screen_bit(0xb, 7),  # ▲
			self.get_screen_bit(0xb, 4),  # [Disp]
			]
		elif self.hwid in (2, 3): screen_data_status_bar = [
			self.get_screen_bit(0,   4),  # [S]
			self.get_screen_bit(0,   2),  # [A]
			self.get_screen_bit(1,   4),  # M
			self.get_screen_bit(1,   1),  # STO
			self.get_screen_bit(2,   6),  # RCL
			self.get_screen_bit(3,   6),  # STAT
			self.get_screen_bit(4,   7),  # CMPLX
			self.get_screen_bit(5,   6),  # MAT
			self.get_screen_bit(5,   1),  # VCT
			self.get_screen_bit(7,   5),  # [D]
			self.get_screen_bit(7,   1),  # [R]
			self.get_screen_bit(8,   4),  # [G]
			self.get_screen_bit(8,   0),  # FIX
			self.get_screen_bit(9,   5),  # SCI
			self.get_screen_bit(0xa, 6),  # Math
			self.get_screen_bit(0xa, 3),  # ▼
			self.get_screen_bit(0xb, 7),  # ▲
			self.get_screen_bit(0xb, 4),  # Disp
			]
		elif self.hwid == 4: screen_data_status_bar = [
			self.get_screen_bit(0),      # [S]
			self.get_screen_bit(1),      # [A]
			self.get_screen_bit(2),      # M
			self.get_screen_bit(3),      # ->[x]
			self.get_screen_bit(5),      # √[]/
			self.get_screen_bit(6),      # [D]
			self.get_screen_bit(7),      # [R]
			self.get_screen_bit(8),      # [G]
			self.get_screen_bit(9),      # FIX
			self.get_screen_bit(0xa),    # SCI
			self.get_screen_bit(0xb),    # 𝐄
			self.get_screen_bit(0xc),    # 𝒊
			self.get_screen_bit(0xd),    # ∠
			self.get_screen_bit(0xe),    # ⇩
			self.get_screen_bit(0xf),    # ◀
			self.get_screen_bit(0x11),   # ▼
			self.get_screen_bit(0x12),   # ▲
			self.get_screen_bit(0x13),   # ▶
			self.get_screen_bit(0x15),   # ⏸
			self.get_screen_bit(0x16),   # ☼
			]
		elif self.hwid == 5: screen_data_status_bar = [
			self.get_screen_bit(1),      # [S]
			self.get_screen_bit(3),      # √[]/
			self.get_screen_bit(4),      # [D] [Deg]
			self.get_screen_bit(5),      # [R] [Rad]
			self.get_screen_bit(6),      # [G] [Gra]
			self.get_screen_bit(7),      # FIX
			self.get_screen_bit(8),      # SCI
			self.get_screen_bit(0xa),    # 𝐄
			self.get_screen_bit(0xb),    # 𝒊
			self.get_screen_bit(0xc),    # ∠
			self.get_screen_bit(0xd),    # ⇩
			self.get_screen_bit(0xe),    # (✓)
			self.get_screen_bit(0x10),   # ◀
			self.get_screen_bit(0x11),   # ▼
			self.get_screen_bit(0x12),   # ▲
			self.get_screen_bit(0x13),   # ▶
			self.get_screen_bit(0x15),   # ⏸
			self.get_screen_bit(0x16),   # ☼
			self.get_screen_bit(9),      # f(𝑥)
			self.get_screen_bit(0xf),    # g(𝑥)
			]
		else: screen_data_status_bar = None
		
		if self.hwid == 0:
			screen_data = []
			for j in range(12):
				inner = []
				for i in range(2):
					n = 9+j*4
					inner.extend([self.screen[i][n+1], self.screen[i][n], self.screen[i][n+2]])
				inner.extend([self.screen[2][n+1], self.screen[2][n+2]])
				screen_data.append(inner)
			screen_data.append(self.screen[1][6])
			screen_data.append(self.screen[2][49])
		else: screen_data = self.screen[1:]

		return screen_data_status_bar, screen_data

	def get_screen_bit(self, addr, bit = 0):
		y = addr // self.scr[0]
		x = (addr % self.scr[0]) * 8 + (~bit & 7)
		return self.screen[y][x]
