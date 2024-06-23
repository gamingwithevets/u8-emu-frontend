import tkinter as tk
import tkinter.ttk as ttk

# https://stackoverflow.com/a/16198198
class VerticalScrolledFrame(tk.Frame):
	def __init__(self, parent, *args, **kw):
		tk.Frame.__init__(self, parent, *args, **kw)

		vscrollbar = tk.Scrollbar(self, orient = 'vertical')
		vscrollbar.pack(fill = 'y', side = 'right')
		canvas = tk.Canvas(self, bd = 0, highlightthickness = 0, yscrollcommand = vscrollbar.set)
		canvas.pack(side = 'left', fill = 'both', expand = True)
		vscrollbar.config(command = canvas.yview)

		canvas.xview_moveto(0)
		canvas.yview_moveto(0)

		self.interior = interior = tk.Frame(canvas)
		interior_id = canvas.create_window(0, 0, window = interior, anchor = 'nw')

		def _configure_interior(event):
			size = (interior.winfo_reqwidth(), interior.winfo_reqheight())
			canvas.config(scrollregion = '0 0 %s %s' % size)
			if interior.winfo_reqwidth() != canvas.winfo_width():
				canvas.config(width=interior.winfo_reqwidth())
		interior.bind('<Configure>', _configure_interior)

		def _configure_canvas(event):
			if interior.winfo_reqwidth() != canvas.winfo_width():
				canvas.itemconfigure(interior_id, width=canvas.winfo_width())
		canvas.bind('<Configure>', _configure_canvas)

class BrkpointFrame(tk.Frame):
	sizenames = {2: "", 4: "D", 8: "Q"}

	def __init__(self, master, gui, index, **kw):
		tk.Frame.__init__(self, master, **kw)
		self.gui = gui
		self.index = index

		self.show_exec_labels = len(self.gui.sim.labels) != 0
		self.show_data_labels = len(self.gui.sim.disas.data_labels) != 0

		if self.show_exec_labels: self.labels = self.gui.sim.labels
		if self.show_data_labels: self.data_labels = self.gui.sim.disas.data_labels

		self.type = tk.IntVar()

		ttk.Button(self, text = 'X', width = 2, command = self.destroy).pack(side = 'right')
		ttk.Label(self, text = '   ').pack(side = 'right')
		ttk.Radiobutton(self, text = 'Execute', variable = self.type, value = 0, command = self.change_type).pack(side = 'right')
		ttk.Radiobutton(self, text = 'Write', variable = self.type, value = 2, command = self.change_type).pack(side = 'right')
		ttk.Radiobutton(self, text = 'Read', variable = self.type, value = 1, command = self.change_type).pack(side = 'right')

		self.enabled = tk.BooleanVar(value = True)
		ttk.Checkbutton(self, text = ' ', variable = self.enabled, command = self.set_enable).pack(side = 'left')

		self.vcmd = self.register(self.gui.sim.validate_hex)

		self.csr = ttk.Entry(self, width = 3, justify = 'left', validate = 'key', validatecommand = (self.vcmd, '%S', '%P', '%d', range(0x10)))
		self.csr.bind('<KeyPress>', self.cap_input)
		self.csr.pack(side = 'left')

		ttk.Label(self, text = ':').pack(side = 'left')

		self.pc = ttk.Entry(self, width = 6, justify = 'left', validate = 'key', validatecommand = (self.vcmd, '%S', '%P', '%d', range(0, 0x10000, 2)))
		self.pc.bind('<KeyPress>', self.cap_input)
		self.pc.pack(side = 'left')

		ttk.Label(self, text = 'H   ').pack(side = 'left')

		self.label = tk.StringVar()
		self.labelselect = ttk.Combobox(self, width = 27, textvariable = self.label)
		if self.show_exec_labels:
			self.labelselect['values'] = [f'{k >> 16:X}:{k & 0xfffe:04X}H - {("" if v[1] else self.labels[v[2]][0]) + v[0]}' for k, v in self.labels.items()]
			self.labelselect.pack(side = 'left')

		self.bind('<FocusOut>', self.focusout)

	def change_type(self):
		self.gui.sim.brkpoints[self.index]['type'] = self.type.get()
		self.labelselect.pack_forget()

		if self.type.get() == 0:
			value = int(self.pc.get(), 16) & 0xfffe
			self.pc.delete(0, 'end')
			self.pc.insert(0, f'{value:04X}')
			self.pc['validatecommand'] = (self.vcmd, '%S', '%P', '%d', range(0, 0x10000, 2))

			value = int(self.csr.get(), 16) & 0xf
			self.csr.delete(0, 'end')
			self.csr.insert(0, f'{value:X}')
			self.csr['validatecommand'] = (self.vcmd, '%S', '%P', '%d', range(0x10))

			if self.show_exec_labels:
				self.label = ''
				self.labelselect['values'] = [f'{k >> 16:X}:{k & 0xfffe:04X}H - {("" if v[1] else self.labels[v[2]][0]) + v[0]}' for k, v in self.labels.items()]
				self.labelselect.pack(side = 'left')
		else:
			self.csr['validatecommand'] = (self.vcmd, '%S', '%P', '%d', range(0x100))
			self.pc['validatecommand'] = (self.vcmd, '%S', '%P', '%d', range(0x10000))

			if self.show_data_labels:
				self.label = ''
				self.labelselect['values'] = [f'{k >> 16}:{k & 0xfffe}H - {v}' for k, v in self.data_labels.items()]
				self.labelselect.pack(side = 'left')

	def cap_input(self, event):
		if event.char.lower() in '0123456789abcdef':
			event.widget.insert('end', event.char.upper())
			return 'break'

	def focusout(self, event = None):
		self.pc.insert(0, '0'*(4-len(self.pc.get())))
		self.csr.insert(0, '0'*(1+(self.type.get() != 0)-len(self.csr.get())))

		self.change_type()

		self.gui.sim.brkpoints[self.index]['addr'] = (int(self.csr.get(), 16) << 16) + int(self.pc.get(), 16)

	def set_enable(self): self.gui.sim.brkpoints[self.index]['enabled'] = self.enabled.get()

	def destroy(self):
		del self.gui.sim.brkpoints[self.index]
		if len(self.gui.sim.brkpoints) == 0: self.gui.clearbutton['state'] = 'disabled'
		super().destroy()

class Brkpoint(tk.Toplevel):
	def __init__(self, sim):
		super(Brkpoint, self).__init__()
		self.sim = sim

		self.withdraw()
		self.geometry('800x600')
		self.resizable(False, False)
		self.title('Breakpoint manager')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self.vh_reg = self.register(self.sim.validate_hex)
		ttk.Label(self, text = 'Breakpoint list\n').pack()

		buttonframe = tk.Frame(self)
		addbtn = ttk.Button(buttonframe, text = 'Add breakpoint', command = self.add)
		addbtn.pack(side = 'left')

		self.clearbutton = ttk.Button(buttonframe, text = 'Delete all', command = self.clear_all, state = 'disabled'); self.clearbutton.pack(side = 'left')
		buttonframe.pack()

		self.brkpointframe = VerticalScrolledFrame(self)
		self.brkpointframe.pack(fill = 'both', expand = True)

	def add(self):
		idx = max(self.sim.brkpoints) + 1 if len(self.sim.brkpoints) > 0 else 0
		if len(self.sim.brkpoints) == 0: self.clearbutton['state'] = 'normal'

		widget = BrkpointFrame(self.brkpointframe.interior, self, idx)
		self.sim.brkpoints[idx] = {'enabled': True, 'type': 0, 'addr': None, 'widget': widget}
		widget.pack(fill = 'x')

	def clear_all(self, confirm = True):
		if confirm and not tk.messagebox.askyesno('Warning', 'Are you sure you want to delete all breakpoints?', icon = 'warning'): return
		for j in [i['widget'] for i in self.sim.brkpoints.values()]: j.destroy()
