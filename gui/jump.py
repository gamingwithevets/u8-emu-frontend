import tkinter as tk
import tkinter.ttk as ttk

class Jump(tk.Toplevel):
	def __init__(self, sim):
		super(Jump, self).__init__()
		self.sim = sim

		self.withdraw()
		self.geometry('250x120')
		self.resizable(False, False)
		self.title('Jump to address')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self.vh_reg = self.register(self.sim.validate_hex)
		ttk.Label(self, text = 'Input new values for CSR and PC.\nStop mode will be disabled after jumping.\n(please input hex bytes)', justify = 'center').pack()
		self.csr = tk.Frame(self); self.csr.pack(fill = 'x')
		ttk.Label(self.csr, text = 'CSR').pack(side = 'left')
		self.csr_entry = ttk.Entry(self.csr, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0x10))); self.csr_entry.pack(side = 'right')
		self.csr_entry.insert(0, '0')
		self.pc = tk.Frame(self); self.pc.pack(fill = 'x')
		ttk.Label(self.pc, text = 'PC').pack(side = 'left')
		self.pc_entry = ttk.Entry(self.pc, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0, 0xfffe, 2))); self.pc_entry.pack(side = 'right')
		ttk.Button(self, text = 'OK', command = self.set_csr_pc).pack(side = 'bottom')
		self.bind('<Return>', lambda x: self.set_csr_pc())
		self.bind('<Escape>', lambda x: self.withdraw())

	def set_csr_pc(self):
		csr_entry = self.csr_entry.get()
		pc_entry = self.pc_entry.get()
		if csr_entry == '' or pc_entry == '': return

		self.sim.sim.core.regs.csr = int(csr_entry, 16) if csr_entry else 0
		self.sim.sim.core.regs.pc = int(pc_entry, 16) if pc_entry else 0
		self.sim.stop_mode = False
		self.sim.update_displays()
		self.withdraw()

		self.csr_entry.delete(0, 'end'); self.csr_entry.insert(0, '0')
		self.pc_entry.delete(0, 'end')
