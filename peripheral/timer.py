import time

class Timer:
	def __init__(self, sim):
		self.sim = sim

		self.nsps = 1e9
		self.max_ns_per_update = 1e9
		self.max_ticks_per_update = 100
		self.tps = 10000
		self.last_time = 0
		self.passed_time = 0

		self.sim.sim.register_sfr(0x20, 6)

	def timer(self):
		now = time.time_ns()
		passed_ns = now - self.last_time
		self.last_time = now
		if passed_ns < 0: passed_ns = 0
		elif passed_ns > self.max_ns_per_update: passed_ns = 0

		self.passed_time += passed_ns * self.tps / self.nsps
		ticks = int(self.passed_time) if self.passed_time < 100 else 100
		self.passed_time -= ticks

		self.timer_tick(ticks)

	def timer_tick(self, tick):
		if self.sim.sim.c_config.sfr[0x25] & 1:
			counter = (self.sim.sim.c_config.sfr[0x23] << 8) + self.sim.sim.c_config.sfr[0x22]
			target = (self.sim.sim.c_config.sfr[0x21] << 8) + self.sim.sim.c_config.sfr[0x20]

			counter = (counter + tick) & 0xffff

			self.sim.sim.c_config.sfr[0x22] = counter & 0xff
			self.sim.sim.c_config.sfr[0x23] = counter >> 8

			if counter >= target and self.sim.standby.stop_mode:
				self.sim.standby.stop_mode = False
				self.sim.sim.c_config.sfr[0x14] = 0x20
				if not self.sim.sim.c_config.real_hw:
					self.sim.write_emu_kb(1, 0)
					self.sim.write_emu_kb(2, 0)
