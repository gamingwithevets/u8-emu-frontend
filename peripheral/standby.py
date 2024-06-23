class Standby:
	def __init__(self, sim):
		self.sim = sim
		
		self.stop_accept = [False, False]
		self.stop_mode = False

		self.sim.sim.register_sfr(8, 1, self.stpacp)
		self.sim.sim.register_sfr(9, 1, self.sbycon)

	def stpacp(self, addr, val):
		if self.stop_accept[0]:
			if val & 0xa0 == 0xa0: self.stop_accept[1] = True
			else: self.stop_accept[0] = False
		elif val & 0x50 == 0x50: self.stop_accept[0] = True
		return 0

	def sbycon(self, addr, val):
		if val & (1 << 1):
			if all(self.stop_accept):
				self.stop_mode = True
				self.stop_accept = [False, False]
				self.sim.sim.c_config.sfr[0x22] = 0
				self.sim.sim.c_config.sfr[0x23] = 0

		return 0
