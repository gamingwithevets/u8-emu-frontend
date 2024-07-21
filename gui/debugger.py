import tkinter as tk
import tkinter.ttk as ttk
import functools

class RegDisplay(tk.Toplevel):
	def __init__(self, sim, fg = None, bg = None, font = None):
		super(RegDisplay, self).__init__()
		self.sim = sim
		
		self.withdraw()
		self.geometry('400x800')
		self.title('Register display')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self.bind('\\', lambda x: self.sim.set_step())
		self.sim.bind_(self, 's', lambda x: self.sim.set_single_step(True))
		self.sim.bind_(self, 'p', lambda x: self.sim.set_single_step(False))
		self['bg'] = bg

		self.info_label = tk.Label(self, font = font, fg = fg, bg = bg, justify = 'left', anchor = 'nw')
		self.info_label.pack(side = 'left', fill = 'both')

	@staticmethod
	@functools.lru_cache
	def fmt_x(val): return 'x' if int(val) else ' '

	def open(self):
		self.deiconify()
		self.print_regs()

	def print_regs(self):
		try: wm_state = self.wm_state()
		except Exception: return

		regs = self.sim.sim.core.regs
		last_swi = self.sim.sim.core.last_swi
		ins, ins_len = self.sim.decode_instruction()

		csr = regs.csr
		pc = regs.pc
		sp = regs.sp
		psw = regs.psw
		psw_f = format(psw, '08b')
		label = self.sim.get_instruction_label((csr << 16) + pc)
		nl = '\n'

		if wm_state == 'normal': self.info_label['text'] = f'''\
=== REGISTERS ===

General registers:
R0   R1   R2   R3   R4   R5   R6   R7
''' + '   '.join(f'{regs.gp[i]:02X}' for i in range(8)) + f'''
 
R8   R9   R10  R11  R12  R13  R14  R15
''' + '   '.join(f'{regs.gp[8+i]:02X}' for i in range(8)) + f'''

Control registers:
CSR:PC          {self.sim.get_addr_label(csr, pc)}
Previous CSR:PC {self.sim.prev_csr_pc} -- Prev. Prev.: {self.sim.prev_prev_csr_pc}
Opcode          ''' + ''.join(format(self.sim.read_cmem((pc + i*2) & 0xfffe, csr), '04X') for i in range(ins_len // 2)) + f'''
Instruction     {ins}
SP              {sp:04X}H
Words @ SP      ''' + ' '.join(format(self.sim.read_dmem(sp + i, 2), '04X') for i in range(0, 8, 2)) + f'''
                ''' + ' '.join(format(self.sim.read_dmem(sp + i, 2), '04X') for i in range(8, 16, 2)) + f'''
DSR:EA          {regs.dsr:02X}:{regs.ea:04X}H

                   C Z S OV MIE HC ELEVEL
PSW             {psw:02X} {self.fmt_x(psw_f[0])} {self.fmt_x(psw_f[1])} {self.fmt_x(psw_f[2])}  {self.fmt_x(psw_f[3])}  {self.fmt_x(psw_f[4])}   {self.fmt_x(psw_f[5])} {psw_f[6:]} ({int(psw_f[6:], 2)})

LCSR:LR         {self.sim.get_addr_label(regs.lcsr, regs.lr)}
ECSR1:ELR1      {self.sim.get_addr_label(regs.ecsr[0], regs.elr[0])}
ECSR2:ELR2      {self.sim.get_addr_label(regs.ecsr[1], regs.elr[1])}
ECSR3:ELR3      {self.sim.get_addr_label(regs.ecsr[2], regs.elr[2])}

EPSW1           {regs.epsw[0]:02X}
EPSW2           {regs.epsw[1]:02X}
EPSW3           {regs.epsw[2]:02X}

Other information:
STOP acceptor            1 [{'x' if self.sim.standby.stop_accept[0] else ' '}]  2 [{'x' if self.sim.standby.stop_accept[1] else ' '}]
STOP mode                [{'x' if self.sim.standby.stop_mode else ' '}]
Shutdown acceptor        [{'x' if self.sim.shutdown_accept else ' '}]
Shutdown state           [{'x' if self.sim.shutdown else ' '}]
Last SWI value           {last_swi if last_swi < 0x40 else 'None'}\
{nl+'Flash mode               ' + str(self.sim.sim.c_config.flash_mode) if self.sim.sim.c_config.hwid == 2 and self.sim.is_5800p else ''}\
{nl+'Counts until next WDTINT ' + str(self.sim.wdt.counter) if self.sim.sim.c_config.hwid == 6 else ''}\
{(nl+'Instructions per second  ' + (format(self.sim.ips, '.1f') if self.sim.ips is not None and not self.sim.single_step else 'None') if self.sim.enable_ips else '')}\
'''

class CallStackDisplay(tk.Toplevel):
	def __init__(self, sim, fg = None, bg = None, font = None):
		super(CallStackDisplay, self).__init__()
		self.sim = sim
		
		self.withdraw()
		self.geometry('400x800')
		self.title('Call stack display')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self['bg'] = bg

		self.info_label = tk.Label(self, font = font, fg = fg, bg = bg, justify = 'left', anchor = 'nw')
		self.info_label.pack(side = 'left', fill = 'both')

	def open(self):
		self.deiconify()
		self.print_regs()

	def print_regs(self):
		try: wm_state = self.wm_state()
		except Exception: return

		regs = self.sim.sim.core.regs

		nl = '\n'


		if wm_state == 'normal':
			a = []
			for j in range(len(self.sim.call_trace)):
				i = self.sim.call_trace[j]
				a.append(f'#{j}{nl}Function address  {self.sim.get_addr_label(i[0] >> 16, i[0] & 0xfffe)}{nl}Return address    {self.sim.get_addr_label(i[1] >> 16, i[1] & 0xfffe)}{nl*2}')

			self.info_label['text'] = f'''\
=== CALL STACK === ({len(self.sim.call_trace)} calls)
{''.join(a)}
'''

class Debugger(tk.Toplevel):
	def __init__(self, sim):
		super(Debugger, self).__init__()
		self.sim = sim

		self.disas_hi = 17

		self.withdraw()
		self.geometry('1200x600')
		self.resizable(False, False)
		self.title('Debugger (beta)')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)

		self.bind('\\', lambda x: self.sim.set_step())
		self.sim.bind_(self, 's', lambda x: self.sim.set_single_step(True))
		self.sim.bind_(self, 'p', lambda x: self.sim.set_single_step(False))

		f_disas = tk.Frame(self, width = 800, height = 300)
		f_disas.grid(row = 0, column = 0, sticky = 'nw')
		f_disas.pack_propagate(False)
		ttk.Label(f_disas, text = 'Disassembly').pack()
		self.disas = tk.Text(f_disas, state = 'disabled', height = self.disas_hi)
		self.disas.pack(fill = 'x')

		f_regs = tk.Frame(self, width = 800, height = 300)
		f_regs.grid(row = 0, column = 0, sticky = 'sw')
		f_regs.pack_propagate(False)
		ttk.Label(f_regs, text = 'Register list').pack()
		r_frame_outer = tk.Frame(f_regs)
		r_frame = []; r_entry = []; self.r = []
		for i in range(16):
			r_frame.append(tk.Frame(r_frame_outer))
			self.r.append(tk.StringVar())
			r_entry.append(ttk.Entry(r_frame[i], width = 3, state = 'readonly', textvariable = self.r[i]))
			r_entry[i].pack()
			ttk.Label(r_frame[i], text = f'R{i}').pack(side = 'bottom')
			r_frame[i].pack(side = 'left', expand = True)
		r_frame_outer.pack(fill = 'x')

		f_call = tk.Frame(self, width = 400, height = 600)
		f_call.grid(row = 0, column = 1, sticky = 'se')
		f_call.pack_propagate(False)
		ttk.Label(f_call, text = 'Call stack\n(Note: actual stack data may be different)', justify = 'center').pack()
		self.call_stack = tk.Text(f_call, state = 'disabled')
		scroll = tk.Scrollbar(f_call, orient = 'vertical', command = self.call_stack.yview)
		self.call_stack.configure(yscrollcommand = scroll.set)
		scroll.pack(side = 'right', fill = 'y')
		self.call_stack.pack(side = 'left', fill = 'both', expand = True)
		
	def open(self):
		self.deiconify()
		self.update()

	def update(self):
		try: wm_state = self.wm_state()
		except Exception: return

		regs = self.sim.sim.core.regs

		nl = '\n'

		if wm_state == 'normal':
			instructions = ['']*self.disas_hi
			cur_csr = regs.csr
			cur_pc = regs.pc
			format_ins = lambda ins_len, inst: f'{">>>" if i == 0 else "   "} {cur_csr:X}:{cur_pc:04X}H    {"".join(format(self.sim.read_cmem((cur_pc + i*2) & 0xfffe, cur_csr), "04X") for i in range(ins_len // 2)):<13}    {inst}'
			for i in range(self.disas_hi):
				ins, ins_len = self.sim.decode_instruction(cur_csr, cur_pc)
				instructions[i] = format_ins(ins_len, ins)
				cur_pc = (cur_pc + ins_len) & 0xfffe

			self.disas['state'] = 'normal'
			self.disas.delete('1.0', 'end')
			self.disas.insert('1.0', nl.join(instructions))
			self.disas['state'] = 'disabled'

			for i in range(16):
				if self.r[i].get() != f'{self.sim.sim.core.regs.gp[i]:02X}': self.r[i].set(f'{self.sim.sim.core.regs.gp[i]:02X}')

			a = []
			for j in range(len(self.sim.call_trace)):
				i = self.sim.call_trace[j]
				a.append(f'#{j}{nl}⇨ {self.sim.get_addr_label(i[0] >> 16, i[0] & 0xfffe)}{nl}⇦ {self.sim.get_addr_label(i[1] >> 16, i[1] & 0xfffe)}{nl*2}')
			self.call_stack['state'] = 'normal'
			self.call_stack.delete('1.0', 'end')
			self.call_stack.insert('1.0', f'''\
{len(self.sim.call_trace)} calls

{''.join(a)}
''')
			self.call_stack['state'] = 'disabled'
