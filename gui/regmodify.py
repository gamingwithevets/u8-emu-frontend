import tkinter as tk
import tkinter.ttk as ttk

class GPModify(tk.Toplevel):
	def __init__(self, sim):
		super(GPModify, self).__init__()
		self.sim = sim
		
		self.withdraw()
		self.geometry('300x100')
		self.resizable(False, False)
		self.title('Modify general registers')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self.vh_reg = self.register(self.sim.validate_hex)

		regs = [str(i) for i in range(16)]

		ttk.Label(self, text = '(please input hex bytes)').pack()
		modify_frame = tk.Frame(self)
		ttk.Label(modify_frame, text = 'Change R').pack(side = 'left')
		ttk.Label(modify_frame, text = ' to:').pack(side = 'right')
		self.reg_var = tk.StringVar(value = '0')
		self.reg_var = ttk.Combobox(modify_frame, width = 2, textvariable = self.reg_var, values = regs)
		self.reg_var.bind('<<ComboboxSelected>>', lambda x: self.update_reg())
		self.reg_var.pack()
		modify_frame.pack()

		byte_frame = tk.Frame(self)
		ttk.Label(byte_frame, text = '#').pack(side = 'left')
		ttk.Label(byte_frame, text = 'H').pack(side = 'right')
		self.byte_entry = ttk.Entry(byte_frame, width = '3', justify = 'center', validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0x100))); self.byte_entry.pack()
		byte_frame.pack()

		ttk.Button(self, text = 'OK', command = self.modify).pack(side = 'bottom')

		self.bind('<Return>', lambda x: self.modify())
		self.bind('<Escape>', lambda x: self.withdraw())

	def open(self):
		if self.reg_var.get() == '': self.reg_var.set('0')
		self.update_reg()
		self.deiconify()

	def update_reg(self):
		self.byte_entry.delete(0, 'end')
		self.byte_entry.insert(0, f'{self.sim.sim.core.regs.gp[int(self.reg_var.get())]:02X}')

	def modify(self):
		self.withdraw()
		self.sim.sim.core.regs.gp[int(self.reg_var.get())] = int(self.byte_entry.get(), 16)
		self.sim.update_displays()

		self.reg_var.set('0')
