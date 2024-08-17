class WDT:
	def __init__(self, sim):
		self.sim = sim
		self.mode = None
		self.ms = (4096, 16384, 65536, 262144)
		self.counter = 0
		self.sim.sim.register_sfr(0xe, 1, self.wdtcon)
		self.sim.sim.register_sfr(0xf, 1)

	def start_wdt(self, mode = 2):
		self.mode = mode
		self.counter = self.ms[self.mode]

	def dec_wdt(self):
		self.counter -= 1
		if self.counter == 0: self.wdt_loop()

	def wdt_loop(self):
		self.sim.sim.c_config.sfr[0x18] |= 1
		self.mode = self.sim.sim.c_config.sfr[0xf] & 3
		self.counter = self.ms[self.mode]

	def wdtcon(self, addr, value): return value == 0x5a
