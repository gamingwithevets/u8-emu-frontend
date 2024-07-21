import tkinter as tk
import tkinter.ttk as ttk
import functools

class Write(tk.Toplevel):
	def __init__(self, sim):
		super(Write, self).__init__()
		self.sim = sim
		
		tk_font = tk.font.nametofont('TkDefaultFont')
		bold_italic_font = tk_font.copy()
		bold_italic_font.config(weight = 'bold', slant = 'italic')

		self.withdraw()
		self.geometry('375x125')
		self.resizable(False, False)
		self.title('Write to data memory')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self.vh_reg = self.register(self.sim.validate_hex)
		ttk.Label(self, text = '(please input hex bytes)', justify = 'center').pack()
		self.csr = tk.Frame(self); self.csr.pack(fill = 'x')
		ttk.Label(self.csr, text = 'Segment').pack(side = 'left')
		self.csr_entry = ttk.Entry(self.csr, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0x100))); self.csr_entry.pack(side = 'right')
		self.csr_entry.insert(0, '0')
		self.pc = tk.Frame(self); self.pc.pack(fill = 'x')
		ttk.Label(self.pc, text = 'Address').pack(side = 'left')
		self.pc_entry = ttk.Entry(self.pc, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0x10000))); self.pc_entry.pack(side = 'right')
		self.byte = tk.Frame(self); self.byte.pack(fill = 'x')
		ttk.Label(self.byte, text = 'Hex data').pack(side = 'left')
		self.byte_entry = ttk.Entry(self.byte, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', None, 1)); self.byte_entry.pack(side = 'right')
		ttk.Button(self, text = 'OK', command = self.write).pack(side = 'bottom')
		self.bind('<Return>', lambda x: self.write())
		self.bind('<Escape>', lambda x: self.withdraw())

	def write(self):
		seg = self.csr_entry.get(); seg = int(seg, 16) if seg else 0
		adr = self.pc_entry.get(); adr = int(adr, 16) if adr else 0
		byte = self.byte_entry.get()
		if seg == '' or adr == '' or byte == '': return
		try: byte = bytes.fromhex(byte) if byte else '\x00'
		except Exception:
			try: byte = byte = bytes.fromhex('0' + byte) if byte else '\x00'
			except Exception:
				tk.messagebox.showerror('Error', 'Invalid hex string!')
				return
		
		index = 0
		while index < len(byte):
			remaining = len(byte) - index
			if remaining > 8: num = 8
			else: num = remaining
			self.sim.write_dmem(adr + index, num, int.from_bytes(byte[index:index+num], 'little'), seg)
			index += num

		self.sim.update_displays()
		self.sim.data_mem.get_mem()
		self.withdraw()

		self.csr_entry.delete(0, 'end'); self.csr_entry.insert(0, '0')
		self.pc_entry.delete(0, 'end')
		self.byte_entry.delete(0, 'end'); self.byte_entry.insert(0, '0')

class DataMem(tk.Toplevel):
	def __init__(self, sim, width = None, height = None, font = None):
		super(DataMem, self).__init__()
		self.sim = sim

		self.withdraw()
		self.geometry(f'{width}x{height}')
		self.resizable(False, False)
		self.title('Show data memory')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)

		self.cursor_position = 0
		self.first_nibble = None

		segments = [
		f'RAM (00:{self.sim.sim.ramstart:04X}H - 00:{self.sim.sim.ramstart + self.sim.sim.ramsize - 1:04X}H)',
		'SFRs (00:F000H - 00:FFFFH)',
		]
		if not self.sim.sim.c_config.real_hw:
			if self.sim.sim.c_config.hwid == 4: segments.append('Segment 4 (04:0000H - 04:FFFFH)')
			elif self.sim.sim.c_config.hwid == 5: segments.append('Segment 8 (08:0000H - 08:FFFFH)')
		if self.sim.sim.c_config.hwid in (2, 3): segments[0] = f'RAM (00:8000H - 00:{"8DFF" if self.sim.sim.c_config.real_hw else "EFFF"}H)'
		if self.sim.sim.c_config.hwid == 2 and self.sim.is_5800p: segments.append('PRAM (04:0000H - 04:7FFFH)')

		self.segment_var = tk.StringVar(value = segments[0])
		self.segment_cb = ttk.Combobox(self, width = 35, textvariable = self.segment_var, values = segments, state = 'readonly')
		self.segment_cb.bind('<<ComboboxSelected>>', lambda x: self.get_mem(False))
		self.segment_cb.pack()

		ttk.Label(self, text = 'Address  ' + ' '.join([f'{i:02X}' for i in range(16)]) + '   ASCII text', justify = 'left', font = font).pack(fill = 'x')
		self.code_frame = ttk.Frame(self)
		self.code_text_sb = ttk.Scrollbar(self.code_frame)
		self.code_text_sb.pack(side = 'right', fill = 'y')
		self.code_text = tk.Text(self.code_frame, font = font, yscrollcommand = self.code_text_sb.set, wrap = 'none', state = 'disabled')
		self.code_text_sb.config(command = self.sb_yview)
		self.code_text.pack(fill = 'both', expand = True)
		self.code_frame.pack(fill = 'both', expand = True)

	def sb_yview(self, *args):
		self.code_text.yview(*args)
		self.get_mem()

	def open(self):
		self.deiconify()
		self.get_mem()

	def get_mem(self, keep_yview = True):
		if self.wm_state() == 'normal':
			seg = self.segment_var.get()
			if seg.startswith('RAM'):
				size = 0xe00 if self.sim.sim.c_config.real_hw and self.sim.sim.c_config.hwid in (2, 3) else self.sim.sim.ramsize
				data = self.format_mem(bytes(self.sim.sim.c_config.ram[:size]), self.sim.sim.ramstart)
			elif seg.startswith('SFRs'): data = self.format_mem(bytes(self.sim.sim.c_config.sfr[:0x1000]), 0xf000)
			elif seg.startswith('Segment'): data = self.format_mem(bytes(self.sim.sim.c_config.emu_seg[:0x10000]), 0, 4 if self.sim.sim.c_config.hwid == 4 else 8)
			elif seg.startswith('PRAM'): data = self.format_mem(bytes(self.sim.sim.c_config.emu_seg[:0x8000]), 0, 4)
			else: data = '[No region selected yet.]'

			self.code_text['state'] = 'normal'
			yview_bak = self.code_text.yview()[0]
			self.code_text.delete('1.0', 'end')
			self.code_text.insert('end', data)
			if keep_yview: self.code_text.yview_moveto(str(yview_bak))
			self.code_text['state'] = 'disabled'

	@staticmethod
	@functools.lru_cache
	def format_mem(data, addr, seg = 0):
		lines = {}
		j = addr // 16
		for i in range(addr, addr + len(data), 16):
			line = ''
			line_ascii = ''
			for byte in data[i-addr:i-addr+16]: line += f'{byte:02X} '; line_ascii += chr(byte) if byte in range(0x20, 0x7f) else '.'
			lines[j] = f'{seg:02}:{i % 0x10000:04X}H {line}  {line_ascii}'
			j += 1
		return '\n'.join(lines.values())
