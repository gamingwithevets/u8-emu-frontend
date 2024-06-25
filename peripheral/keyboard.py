class Keyboard:
	def __init__(self, sim):
		self.sim = sim

		# placeholder
		self.sim.sim.register_sfr(0x41, 0xf)
