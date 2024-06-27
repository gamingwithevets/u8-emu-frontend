class Keyboard:
	def __init__(self, sim):
		self.sim = sim

		# placeholder
		self.sim.sim.register_sfr(0x41, 0xe)
		self.sim.sim.c_config.sfr[0x50] = self.sim.sim.c_config.pd_value
