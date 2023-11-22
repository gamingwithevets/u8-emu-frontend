import io
import os
import PIL.Image
import sys
import math
import time
import ctypes
import pygame
import logging
import functools
import threading
import traceback
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font
import tkinter.messagebox
from enum import IntEnum

from pyu8disas import main as disas_main
from tool8 import tool8
import platform

if sys.version_info < (3, 6, 0, 'alpha', 4):
	print(f'This program requires at least Python 3.6.0a4. (You are running Python {platform.python_version()})')
	sys.exit()

if pygame.version.vernum < (2, 2, 0):
	print(f'This program requires at least Pygame 2.2.0. (You are running Pygame {pygame.version.ver})')
	sys.exit()

level = logging.INFO

try:
	exec(f'import {sys.argv[1]+" as " if len(sys.argv) > 1 else ""}config')
	if hasattr(config, 'dt_format'): logging.basicConfig(datefmt = config.dt_format, format = '[%(asctime)s] %(levelname)s: %(message)s', level = level)
	else: logging.basicConfig(format = '%(levelname)s: %(message)s', level = level)
except ImportError as e:
	logging.basicConfig(format = '%(levelname)s: %(message)s', level = level)
	logging.error(str(e))
	sys.exit()

# For ROM8 reading
class DisplayBounds(ctypes.Structure):
	_fields_ = [
		('x',      ctypes.c_uint16),
		('y',      ctypes.c_uint16),
		('width',  ctypes.c_uint16),
		('height', ctypes.c_uint16),
		('scale',  ctypes.c_uint16),
	]

class GUIKey(ctypes.Structure):
	_fields_ = [
		('x',      ctypes.c_uint16),
		('y',      ctypes.c_uint16),
		('width',  ctypes.c_uint16),
		('height', ctypes.c_uint16),
		('keysym', ctypes.c_uint16),
	]

class Keybind(ctypes.Structure):
	_fields_ = [
		('key', ctypes.c_char),
		('keysym', ctypes.c_uint8),
	]

# Thanks Delta / @frsr on Discord!
class u8_core_t(ctypes.Structure):	# Forward definition so pointers can be used
	pass

class u8_regs_t(ctypes.Structure):
	_fields_ = [
		("gp",		ctypes.c_uint8 * 16),
		("pc",		ctypes.c_uint16),
		("csr",		ctypes.c_uint8),
		("lcsr",	ctypes.c_uint8),
		("ecsr",	ctypes.c_uint8 * 3),
		("lr",		ctypes.c_uint16),
		("elr",		ctypes.c_uint16 * 3),
		("psw",		ctypes.c_uint8),
		("epsw",	ctypes.c_uint8 * 3),
		("sp",		ctypes.c_uint16),
		("ea",		ctypes.c_uint16),
		("dsr",		ctypes.c_uint8)
	]

class _acc_func(ctypes.Structure):
	_fields_ = [
		("read",	ctypes.CFUNCTYPE(ctypes.c_uint8, ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16)),
		("write",	ctypes.CFUNCTYPE(None, ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8))
	]

class _acc_union(ctypes.Union):
	_anonymous_ = ["_acc_func"]
	_fields_ = [
		("array",		ctypes.POINTER(ctypes.c_uint8)),
		("_acc_func",	_acc_func)
	]

class u8_mem_reg_t(ctypes.Structure):
	_anonymous_ = ["_acc_union"]
	_fields_ = [
		("type",		ctypes.c_uint),
		("rw",			ctypes.c_bool),
		("addr_l",		ctypes.c_uint32),
		("addr_h",		ctypes.c_uint32),

		("acc",			ctypes.c_uint),
		("_acc_union",	_acc_union)
	]

class u8_mem_t(ctypes.Structure):
	_fields_ = [
		("num_regions",	ctypes.c_int),
		("regions",		ctypes.POINTER(u8_mem_reg_t))
	]

u8_core_t._fields_ = [
		("regs",	u8_regs_t),
		("cur_dsr",	ctypes.c_uint8),
		("mem",		u8_mem_t)
	]

class u8_mem_type_e(IntEnum):	
	U8_REGION_BOTH = 0
	U8_REGION_DATA = 1
	U8_REGION_CODE = 2

class u8_mem_acc_e(IntEnum):
	U8_MACC_ARR  = 0
	U8_MACC_FUNC = 1

##
# Utility Functions
#

def uint8_ptr(array, offset):
	vp = ctypes.cast(ctypes.pointer(array), ctypes.c_void_p).value + offset
	return ctypes.cast(vp, ctypes.POINTER(ctypes.c_uint8))

# Load the sim library
sim_lib = ctypes.CDLL(os.path.abspath(config.shared_lib))

sim_lib.u8_step.argtypes = [ctypes.POINTER(u8_core_t)]

sim_lib.read_reg_r.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8]
sim_lib.read_reg_r.restype = ctypes.c_uint8
sim_lib.read_reg_er.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8]
sim_lib.read_reg_er.restype = ctypes.c_uint16
sim_lib.read_reg_xr.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8]
sim_lib.read_reg_xr.restype = ctypes.c_uint32
sim_lib.read_reg_qr.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8]
sim_lib.read_reg_qr.restype = ctypes.c_uint64

sim_lib.write_reg_r.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint64]
sim_lib.write_reg_r.restype = None
sim_lib.write_reg_er.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint64]
sim_lib.write_reg_er.restype = None
sim_lib.write_reg_xr.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint64]
sim_lib.write_reg_xr.restype = None
sim_lib.write_reg_qr.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint64]
sim_lib.write_reg_qr.restype = None

sim_lib.read_mem_data.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8]
sim_lib.read_mem_data.restype = ctypes.c_uint64
sim_lib.read_mem_code.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8]
sim_lib.read_mem_code.restype = ctypes.c_uint64

sim_lib.write_mem_data.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_uint64]
sim_lib.write_mem_data.restype = None
sim_lib.write_mem_code.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_uint64]
sim_lib.write_mem_code.restype = None

##
# Core
##

class Core:
	def __init__(self, rom, ko_mode):
		self.core = u8_core_t()

		# Initialise memory
		self.code_mem = (ctypes.c_uint8 * len(rom))(*rom)

		rwin_sizes = {
		0: 0xdfff,
		2: 0x7fff,
		3: 0x7fff,
		4: 0xcfff,
		5: 0x8fff,
		}

		data_size = {
		0: (0xe000, 0x1000),
		3: (0x8000, 0xe00 if config.real_hardware else 0x7000),
		4: (0xd000, 0x2000),
		5: (0x9000, 0x6000),
		}

		self.known_sfrs = [0, 8, 9, 0xa, 0x10, 0x11, 0x14, 0x15, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x30, 0x31, 0x32, 0x33, 0x40, 0x42, 0x44 if ko_mode else 0x46, 0x50, 0x310]
		if config.hardware_id == 0: self.known_sfrs.extend(list(range(0x800, 0x820)))
		elif config.hardware_id in (4, 5): self.known_sfrs.extend(list(range(0x800, 0x1000)))
		else: self.known_sfrs.extend(list(range(0x800, 0xa00)))

		self.sdata = data_size[config.hardware_id if config.hardware_id in data_size else 3]

		self.data_mem = (ctypes.c_uint8 * self.sdata[1])()
		self.sfr = (ctypes.c_uint8 * 0x1000)()
		if not config.real_hardware and hasattr(config, 'pd_value'): self.sfr[0x50] = config.pd_value

		if config.hardware_id in (4, 5): self.rw_seg = (ctypes.c_uint8 * 0x10000)()

		read_functype = ctypes.CFUNCTYPE(ctypes.c_uint8, ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16)
		write_functype = ctypes.CFUNCTYPE(None, ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8)

		blank_code_mem_f = read_functype(self.blank_code_mem)
		read_sfr_f = read_functype(self.read_sfr)
		write_sfr_f = write_functype(self.write_sfr)
		read_dsr_f = read_functype(self.read_dsr)
		write_dsr_f = write_functype(self.write_dsr)

		regions = [
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_CODE, False, 0x00000,       len(rom) - 1,                    u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x00000,       rwin_sizes[config.hardware_id],  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  self.sdata[0], sum(self.sdata),                 u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.data_mem, 0x00000))),
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x0F000, 0x0F000,  u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(read_dsr_f, write_dsr_f))),
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x0F001, 0x0FFFF,  u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(read_sfr_f, write_sfr_f))),
		]

		if config.real_hardware: regions.append(u8_mem_reg_t(u8_mem_type_e.U8_REGION_CODE, False, len(rom), 0xFFFFF, u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(blank_code_mem_f))))

		if config.hardware_id == 4: regions.extend((
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x10000, 0x3FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x10000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x40000, 0x4FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.rw_seg,   0x00000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x50000, 0x5FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
			))
		elif config.hardware_id == 5: regions.extend((
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x10000, 0x7FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x10000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x80000, 0x8FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.rw_seg,   0x00000))),
			))
		else: regions.extend((
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x10000, 0x1FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x10000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x80000, 0x8FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
			))

		self.core.mem.num_regions = len(regions)
		self.core.mem.regions = ctypes.cast((u8_mem_reg_t * len(regions))(*regions), ctypes.POINTER(u8_mem_reg_t))

		# Initialise SP and PC
		self.core.regs.sp = rom[0] | rom[1] << 8
		self.core.regs.pc = rom[2] | rom[3] << 8
	

	def u8_step(self):
		self.sfr[0] = self.core.regs.dsr
		sim_lib.u8_step(ctypes.pointer(self.core))
	
	# Register Access
	def read_reg_r(self, reg):
		return sim_lib.read_reg_r(ctypes.pointer(self.core), reg)

	def read_reg_er(self, reg):
		return sim_lib.read_reg_er(ctypes.pointer(self.core), reg)

	def read_reg_xr(self, reg):
		return sim_lib.read_reg_xr(ctypes.pointer(self.core), reg)

	def read_reg_qr(self, reg):
		return sim_lib.read_reg_qr(ctypes.pointer(self.core), reg)
	
	def write_reg_r(self, reg, val):
		sim_lib.write_reg_r(ctypes.pointer(self.core), reg, val)
	
	def write_reg_er(self, reg, val):
		sim_lib.write_reg_er(ctypes.pointer(self.core), reg, val)

	def write_reg_xr(self, reg, val):
		sim_lib.write_reg_xr(ctypes.pointer(self.core), reg, val)

	def write_reg_qr(self, reg, val):
		sim_lib.write_reg_qr(ctypes.pointer(self.core), reg, val)
	
	# Memory Access
	def read_mem_data(self, dsr, offset, size):
		return sim_lib.read_mem_data(ctypes.pointer(self.core), dsr, offset, size)
	
	def read_mem_code(self, dsr, offset, size):
		return sim_lib.read_mem_code(ctypes.pointer(self.core), dsr, offset, size)
	
	def write_mem_data(self, dsr, offset, size, value):
		return sim_lib.write_mem_data(ctypes.pointer(self.core), dsr, offset, size, value)
	
	def write_mem_code(self, dsr, offset, size, value):
		return sim_lib.write_mem_code(ctypes.pointer(self.core), dsr, offset, size, value)

	def blank_code_mem(self, core, seg, addr): return 0xff

	def write_sfr(self, core, seg, addr, value):
		addr += 1

		if addr not in self.known_sfrs: logging.warning(f'Write to unknown SFR {0xf000 + addr:04X}H (value #{value:02X}H) @ {self.core.regs.csr:X}:{self.core.regs.pc:04X}H')
		self.sfr[addr] = value

	def read_sfr(self, core, seg, addr):
		addr += 1

		if addr not in self.known_sfrs: logging.warning(f'Read from unknown SFR {0xf000 + addr:04X}H @ {self.core.regs.csr:X}:{self.core.regs.pc:04X}H')
		return self.sfr[addr]

	def write_dsr(self, core, seg, addr, value):
		self.sfr[0] = value
		self.core.regs.dsr = value

	def read_dsr(self, core, seg, addr): return self.core.regs.dsr

# https://github.com/JamesGKent/python-tkwidgets/blob/master/Debounce.py
class Debounce():
	'''
	When holding a key down, multiple key press and key release events are fired in
	succession. Debouncing is implemented in order to squash these repeated events
	and know when the "real" KeyRelease and KeyPress events happen.
	Use by subclassing a tkinter widget along with this class:
		class DebounceTk(Debounce, tk.Tk):
			pass
	'''
	
	# use classname as key to store class bindings
	# as single dict for all instances
	_bind_class_dict = {}
	
	# 'all' bindings stored here
	# single dict for all instances
	_bind_all_dict = {}
	
	def bind(self, event, function, debounce=True):
		'''
		Override the bind method, acts as normal binding if not KeyPress or KeyRelease
		type events, optional debounce parameter can be set to false to force normal behavior
		'''
		self._debounce_init()
		self._debounce_bind(event, function, debounce,
			self._binding_dict, self._base.bind)
			
	def bind_all(self, event, function, debounce=True):
		'''
		Override the bind_all method, acts as normal binding if not KeyPress or KeyRelease
		type events, optional debounce parameter can be set to false to force normal behavior
		'''
		self._debounce_init()
		self._debounce_bind(event, function, debounce,
			self._bind_all_dict, self._base.bind_all)
		
	def bind_class(self, event, function, debounce=True):
		'''
		Override the bind_class method, acts as normal binding if not KeyPress or KeyRelease
		type events, optional debounce parameter can be set to false to force normal behavior
		unlike underlying tk bind_class this uses name of class on which its called
		instead of requireing clas name as a parameter
		'''
		self._debounce_init()
		self._debounce_bind(event, function, debounce,
			self._bind_class_dict[self.__class__.__name__],
			self._base.bind_class, self.__class__.__name__)
			
	def _debounce_bind(self, event, function, debounce, bind_dict, bind_method, *args):
		'''
		internal method to implement binding
		'''
		self._debounce_init()
		# remove special symbols and split at first hyphen if present
		ev = event.replace("<", "").replace(">", "").split('-', 1)
		# if debounce and a supported event
		if (('KeyPress' in ev) or ('KeyRelease' in ev)) and debounce:
			if len(ev) == 2: # not generic binding so use keynames as key
				evname = ev[1]
			else: # generic binding, use event type
				evname = ev[0]
			if evname in bind_dict: # if have prev binding use that dict
				d = bind_dict[evname]
			else: # no previous binding, create new default dict
				d = {'has_prev_key_release':None, 'has_prev_key_press':False}

			# add function to dict (as keypress or release depending on name)
			d[ev[0]] = function
			# save binding back into dict
			bind_dict[evname] = d
			# call base class binding
			if ev[0] == 'KeyPress':
				bind_method(self, *args, sequence=event, func=self._on_key_press_repeat)
			elif ev[0] == 'KeyRelease':
				bind_method(self, *args, sequence=event, func=self._on_key_release_repeat)
				
		else: # not supported or not debounce, bind as normal
			bind_method(self, *args, sequence=event, func=function)
			
	def _debounce_init(self):
		# get first base class that isn't Debounce and save ref
		# this will be used for underlying bind methods
		if not hasattr(self, '_base'):
			for base in self.__class__.__bases__:
				if base.__name__ != 'Debounce':
					self._base = base
					break
		# for instance bindings
		if not hasattr(self, '_binding_dict'):
			self._binding_dict = {}
			
		# for class bindings
		try: # check if this class has alread had class bindings
			cd = self._bind_class_dict[self.__class__.__name__]
		except KeyError: # create dict to store if not
			self._bind_class_dict[self.__class__.__name__] = {}
			
		# get the current bind tags
		bindtags = list(self.bindtags())
		# add our custom bind tag before the origional bind tag
		index = bindtags.index(self._base.__name__)
		bindtags.insert(index, self.__class__.__name__)
		# save the bind tags back to the widget
		self.bindtags(tuple(bindtags))
			
	def _get_evdict(self, event):
		'''
		internal method used to get the dictionaries that store the special binding info
		'''
		dicts = []
		names = {'2':'KeyPress', '3':'KeyRelease'}
		# loop through all applicable bindings
		for d in [self._binding_dict, # instance binding
			self._bind_class_dict[self.__class__.__name__], # class
			self._bind_all_dict]: # all
			evdict = None
			generic = False
			if event.type in names: # if supported event
				evname = event.keysym
				if evname not in d: # if no specific binding
					generic = True
					evname = names[event.type]
				try:
					evdict = d[evname]
				except KeyError:
					pass
			if evdict: # found a binding
				dicts.append((d, evdict, generic))
		return dicts
		
	def _on_key_release(self, event):
		'''
		internal method, called by _on_key_release_repeat only when key is actually released
		this then calls the method that was passed in to the bind method
		'''
		# get all binding details
		for d, evdict, generic in self._get_evdict(event):
			# call callback
			res = evdict['KeyRelease'](event)
			evdict['has_prev_key_release'] = None
			
			# record that key was released
			if generic:
				d['KeyPress'][event.keysym] = False
			else:
				evdict['has_prev_key_press'] = False
			# if supposed to break propagate this up
			if res == 'break':
				return 'break'
		
	def _on_key_release_repeat(self, event):
		'''
		internal method, called by the 'KeyRelease' event, used to filter false events
		'''
		# get all binding details
		for d, evdict, generic in self._get_evdict(event):
			if evdict["has_prev_key_release"]:
				# got a previous release so cancel it
				self.after_cancel(evdict["has_prev_key_release"])
				evdict["has_prev_key_release"] = None
			# queue new event for key release
			evdict["has_prev_key_release"] = self.after_idle(self._on_key_release, event)
		
	def _on_key_press(self, event):
		'''
		internal method, called by _on_key_press_repeat only when key is actually pressed
		this then calls the method that was passed in to the bind method
		'''
		# get all binding details
		for d, evdict, generic in self._get_evdict(event):
			# call callback
			res = evdict['KeyPress'](event)
			# record that key was pressed
			if generic:
				evdict[event.keysym] = True
			else:
				evdict['has_prev_key_press'] = True
			# if supposed to break propagate this up
			if res == 'break':
				return 'break'
		
	def _on_key_press_repeat(self, event):
		'''
		internal method, called by the 'KeyPress' event, used to filter false events
		'''
		# get binding details
		for d, evdict, generic in self._get_evdict(event):
			if not generic:
				if evdict["has_prev_key_release"]:
					# got a previous release so cancel it
					self.after_cancel(evdict["has_prev_key_release"])
					evdict["has_prev_key_release"] = None
				else:
					# if not pressed before (real event)
					if evdict['has_prev_key_press'] == False:
						self._on_key_press(event)
			else:
				# if not pressed before (real event)
				if (event.keysym not in evdict) or (evdict[event.keysym] == False):
					self._on_key_press(event)

class DebounceTk(Debounce, tk.Tk): pass

class Jump(tk.Toplevel):
	def __init__(self, sim):
		super(Jump, self).__init__()
		self.sim = sim

		self.withdraw()
		self.geometry('250x100')
		self.resizable(False, False)
		self.title('Jump to address')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self.vh_reg = self.register(self.sim.validate_hex)
		ttk.Label(self, text = 'Input new values for CSR and PC.\n(please input hex bytes)', justify = 'center').pack()
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
		self.sim.reg_display.print_regs()
		self.withdraw()

		self.csr_entry.delete(0, 'end'); self.csr_entry.insert(0, '0')
		self.pc_entry.delete(0, 'end')

class Brkpoint(tk.Toplevel):
	def __init__(self, sim):
		super(Brkpoint, self).__init__()
		self.sim = sim

		self.withdraw()
		self.geometry('300x125')
		self.resizable(False, False)
		self.title('Set breakpoint')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self.vh_reg = self.register(self.sim.validate_hex)
		ttk.Label(self, text = 'Single-step mode will be activated if CSR:PC matches\nthe below. Note that only 1 breakpoint can be set.\n(please input hex bytes)', justify = 'center').pack()
		self.csr = tk.Frame(self); self.csr.pack(fill = 'x')
		ttk.Label(self.csr, text = 'CSR').pack(side = 'left')
		self.csr_entry = ttk.Entry(self.csr, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0x10))); self.csr_entry.pack(side = 'right')
		self.csr_entry.insert(0, '0')
		self.pc = tk.Frame(self); self.pc.pack(fill = 'x')
		ttk.Label(self.pc, text = 'PC').pack(side = 'left')
		self.pc_entry = ttk.Entry(self.pc, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0, 0xfffe, 2))); self.pc_entry.pack(side = 'right')
		ttk.Button(self, text = 'OK', command = self.set_brkpoint).pack(side = 'bottom')
		self.bind('<Return>', lambda x: self.set_brkpoint())
		self.bind('<Escape>', lambda x: self.withdraw())

	def set_brkpoint(self):
		csr_entry = self.csr_entry.get()
		pc_entry = self.pc_entry.get()
		if csr_entry == '' or pc_entry == '': return
		self.sim.breakpoint = ((int(csr_entry, 16) if csr_entry else 0) << 16) + (int(pc_entry, 16) if pc_entry else 0)
		self.sim.reg_display.print_regs()
		self.withdraw()

		self.csr_entry.delete(0, 'end'); self.csr_entry.insert(0, '0')
		self.pc_entry.delete(0, 'end')

	def clear_brkpoint(self):
		self.sim.breakpoint = None
		self.sim.reg_display.print_regs()

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

		self.sim.reg_display.print_regs()
		self.sim.data_mem.get_mem()
		self.withdraw()

		self.csr_entry.delete(0, 'end'); self.csr_entry.insert(0, '0')
		self.pc_entry.delete(0, 'end')
		self.byte_entry.delete(0, 'end'); self.byte_entry.insert(0, '0')

class DataMem(tk.Toplevel):
	def __init__(self, sim):
		super(DataMem, self).__init__()
		self.sim = sim

		self.withdraw()
		self.geometry(f'{config.data_mem_width}x{config.data_mem_height}')
		self.resizable(False, False)
		self.title('Show data memory')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)

		segments = [
		f'RAM (00:{self.sim.sim.sdata[0]:04X}H - 00:{sum(self.sim.sim.sdata) - 1:04X}H)',
		'SFRs (00:F000H - 00:FFFFH)',
		]
		if config.hardware_id == 4: segments.append('Segment 4 (04:0000H - 04:FFFFH)')
		elif config.hardware_id == 5: segments.append('Segment 8 (08:0000H - 08:FFFFH)')
		elif config.hardware_id in (2, 3): segments[0] = f'RAM (00:8000H - 00:{"8DFF" if config.real_hardware else "EFFF"}H)'

		self.segment_var = tk.StringVar(value = segments[0])
		self.segment_cb = ttk.Combobox(self, width = 35, textvariable = self.segment_var, values = segments)
		self.segment_cb.bind('<<ComboboxSelected>>', lambda x: self.get_mem(False))
		self.segment_cb.pack()

		self.code_frame = ttk.Frame(self)
		self.code_text_sb = ttk.Scrollbar(self.code_frame)
		self.code_text_sb.pack(side = 'right', fill = 'y')
		self.code_text = tk.Text(self.code_frame, font = config.data_mem_font, yscrollcommand = self.code_text_sb.set, wrap = 'none', state = 'disabled')
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
			if seg.startswith('RAM'): data = self.format_mem(bytes(self.sim.sim.data_mem)[:0xe00 if config.real_hardware and config.hardware_id in (2, 3) else len(self.sim.sim.data_mem)], self.sim.sim.sdata[0])
			elif seg.startswith('SFRs'): data = self.format_mem(bytes(self.sim.sim.sfr), 0xf000)
			elif seg.startswith(f'Segment {4 if config.hardware_id == 4 else 8}'): data = self.format_mem(bytes(self.sim.sim.rw_seg), 0, 4 if config.hardware_id == 4 else 8)

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
			lines[j] = f'{seg:02}:{i % 0x10000:04X}H  {line}  {line_ascii}'
			j += 1
		return '\n'.join(lines.values())

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
		self.sim.reg_display.print_regs()

		self.reg_var.set('0')

class RegDisplay(tk.Toplevel):
	def __init__(self, sim):
		super(RegDisplay, self).__init__()
		self.sim = sim
		
		self.withdraw()
		self.geometry('400x800')
		self.title('Register display')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self['bg'] = config.console_bg

		self.info_label = tk.Label(self, font = config.console_font, fg = config.console_fg, bg = config.console_bg, justify = 'left', anchor = 'nw')
		self.info_label.pack(side = 'left', fill = 'both')

	def open(self):
		self.deiconify()
		self.print_regs()

	def print_regs(self):
		regs = self.sim.sim.core.regs

		csr = regs.csr
		pc = regs.pc
		sp = regs.sp
		psw = regs.psw
		psw_f = format(psw, '08b')

		if self.wm_state() == 'normal': self.info_label['text'] = f'''\
=== REGISTERS ===

General registers:
R0   R1   R2   R3   R4   R5   R6   R7
''' + '   '.join(f'{regs.gp[i]:02X}' for i in range(8)) + f'''
 
R8   R9   R10  R11  R12  R13  R14  R15
''' + '   '.join(f'{regs.gp[8+i]:02X}' for i in range(8)) + f'''

Control registers:
CSR:PC          {csr:X}:{pc:04X}H (prev. value: {self.sim.prev_csr_pc})
Words @ CSR:PC  ''' + ' '.join(format(self.sim.read_cmem((pc + i*2) & 0xfffe, csr), '04X') for i in range(3)) + f'''
Instruction     {self.sim.decode_instruction()}
SP              {sp:04X}H
Words @ SP      ''' + ' '.join(format(self.sim.read_dmem(sp + i, 2), '04X') for i in range(0, 8, 2)) + f'''
                ''' + ' '.join(format(self.sim.read_dmem(sp + i, 2), '04X') for i in range(8, 16, 2)) + f'''
DSR:EA          {regs.dsr:02X}:{regs.ea:04X}H

                   C Z S OV MIE HC ELEVEL
PSW             {psw:02X} {self.fmt_x(psw_f[0])} {self.fmt_x(psw_f[1])} {self.fmt_x(psw_f[2])}  {self.fmt_x(psw_f[3])}  {self.fmt_x(psw_f[4])}   {self.fmt_x(psw_f[5])} {psw_f[6:]} ({int(psw_f[6:], 2)})

LCSR:LR         {regs.lcsr:X}:{regs.lr:04X}H
ECSR1:ELR1      {regs.ecsr[0]:X}:{regs.elr[0]:04X}H
ECSR2:ELR2      {regs.ecsr[1]:X}:{regs.elr[1]:04X}H
ECSR3:ELR3      {regs.ecsr[2]:X}:{regs.elr[2]:04X}H

EPSW1           {regs.epsw[0]:02X}
EPSW2           {regs.epsw[1]:02X}
EPSW3           {regs.epsw[2]:02X}

Other information:
Breakpoint               {format(self.sim.breakpoint >> 16, 'X') + ':' + format(self.sim.breakpoint % 0x10000, '04X') + 'H' if self.sim.breakpoint is not None else 'None'}
STOP acceptor            1 [{'x' if self.sim.stop_accept[0] else ' '}]  2 [{'x' if  self.sim.stop_accept[1] else ' '}]
STOP mode                [{'x' if self.sim.stop_mode else ' '}]
Instructions per second  {format(self.sim.ips, '.1f') if self.sim.ips is not None and not self.sim.single_step else 'None'}\
'''

	@staticmethod
	@functools.lru_cache
	def fmt_x(val): return 'x' if int(val) else ' '

class Sim:
	def __init__(self):
		im = PIL.Image.open(config.status_bar_path)
		size = im.size
		if not hasattr(config, 's_width'):  config.s_width  = size[0]
		if not hasattr(config, 's_height'): config.s_height = size[1]

		self.rom8 = config.rom8 if hasattr(config, 'rom8') else False
		self.use_char = config.use_char if hasattr(config, 'use_char') else False
		self.ko_mode = config.ko_mode if hasattr(config, 'ko_mode') and config.ko_mode == 1 else 0
		self.text_y = config.text_y if hasattr(config, 'text_y') else 22
		self.pix_color = config.pix_color if hasattr(config, 'pix_color') else (0, 0, 0)

		if self.rom8:
			tags = list(tool8.read8(config.rom_file))
			props = {}
			keymap = {}
			found_tags = set()
			
			for tag, data in tags:
				if tag in found_tags and tag != 2:
					logging.error(f'Duplicate tag (type {int(tag)}) found')
					sys.exit()
				else: found_tags.add(tag)

				# end
				if tag == 0: break
				# prop
				elif tag == 2:
					ds = data.decode().split('=', 1)
					props[ds[0]] = ds[1]
				# rom
				elif tag == 3: rom = data
				# faceSVG / facePNG
				elif tag in (4, 5):
					if tag == 4 and 5 in found_tags:
						logging.error('facePNG tag already used')
						sys.exit()
					elif tag == 5 and 4 in found_tags:
						logging.error('faceSVG tag already used')
						sys.exit()

					if tag == 4:
						try: import cairosvg
						except Exception:
							logging.error(f'CairoSVG threw an error during import.\n{traceback.format_exc()}')
							sys.exit()

						data = cairosvg.svg2png(bytestring = data)
					
					name = f'temp{time.time_ns()}.png'
					with open(name, 'wb') as f: f.write(data)
					config.interface_path = name

				# faceDisplayBounds
				elif tag == 6:
					facedisp = DisplayBounds.from_buffer_copy(data)
					config.screen_tl_w = facedisp.x
					config.screen_tl_h = facedisp.y - config.s_height + 1
					config.pix         = facedisp.scale
				
				# faceGUIKeys
				elif tag == 7:
					for i in range(0, len(data), 10):
						key = GUIKey.from_buffer_copy(data[i:i+10])
						if key.keysym == 0x80: kio = None
						else: kio = (key.keysym >> 4 & 0xf, key.keysym & 0xf)
						if kio in keymap: keymap[kio][0] = (key.x, key.y, key.width, key.height)
						else: keymap[kio] = [(key.x, key.y, key.width, key.height)]
				
				# calcType
				elif tag == 9:
					calctype = data[0]
					if calctype & 3 == 1: config.hardware_id = 3
					elif calctype & 3 == 2: config.hardware_id = 4
					elif calctype & 3 == 3: config.hardware_id = 5
					config.real_hardware = calctype & 0xfc != 4
				
				# faceKeybinds
				elif tag == 10:
					self.use_char = True
					for i in range(0, len(data), 2):
						key = Keybind.from_buffer_copy(data[i:i+2])
						if key.keysym == 0x80: kio = None
						kio = (key.keysym >> 4 & 0xf, key.keysym & 0xf)
						if kio not in keymap: keymap[kio] = [(0, 0, 0, 0)]
						keymap[kio].append(key.key.decode())

			if keymap != {}: config.keymap = keymap
			if 'model' in props: config.root_w_name = props['model']
			logging.info('ROM8 properties:\n' + '\n'.join([f'{k}: {v}' for k, v in props.items()]))
		else:
			rom = open(config.rom_file, 'rb').read()
			if len(rom) % 2 != 0:
				logging.error('ROM size cannot be odd')
				sys.exit()

		im = PIL.Image.open(config.interface_path)
		size = im.size
		if not hasattr(config, 'width'):  config.width  = size[0]
		if not hasattr(config, 'height'): config.height = size[1]

		self.sim = Core(rom, self.ko_mode)

		self.root = DebounceTk()
		self.root.geometry(f'{config.width}x{config.height}')
		self.root.resizable(False, False)
		self.root.title(config.root_w_name)
		self.root.protocol('WM_DELETE_WINDOW', self.exit_sim)
		self.root.focus_set()

		self.init_sp = rom[0] | rom[1] << 8
		self.init_pc = rom[2] | rom[3] << 8

		self.keys_pressed = set()
		self.keys = []
		for key in [i[1:] for i in config.keymap.values()]: self.keys.extend(key)

		self.jump = Jump(self)
		self.brkpoint = Brkpoint(self)
		self.write = Write(self)
		self.data_mem = DataMem(self)
		self.gp_modify = GPModify(self)
		self.reg_display = RegDisplay(self)
		self.disas = disas_main.Disasm()

		embed_pygame = tk.Frame(self.root, width = config.width, height = config.height)
		embed_pygame.pack(side = 'left')
		embed_pygame.focus_set()

		def press_cb(event):
			for k, v in config.keymap.items():
				p = v[0]
				if (event.type == tk.EventType.ButtonPress and event.x in range(p[0], p[0]+p[2]) and event.y in range(p[1], p[1]+p[3])) \
				or (event.type == tk.EventType.KeyPress and (event.char if self.use_char else event.keysym.lower()) in v[1:]):
					self.keys_pressed.add(k)
					if k is None: self.reset_core()
					else:
						if not config.real_hardware:
							self.stop_mode = False
							self.write_emu_kb(1, 1 << k[0])
							self.write_emu_kb(2, 1 << k[1])

		def release_cb(event):
			if event.type == tk.EventType.KeyRelease and event.keysym.startswith('Shift'): 
				self.keys_pressed.clear()
				return

			for k, v in config.keymap.items():
				p = v[0]
				if (event.type == tk.EventType.ButtonRelease and event.x in range(p[0], p[0]+p[2]) and event.y in range(p[1], p[1]+p[3])) \
					or (event.type == tk.EventType.KeyRelease and (event.char if self.use_char else event.keysym.lower()) in v[1:]):
						try:
							self.keys_pressed.remove(k)
							return
						except KeyError: break

			self.keys_pressed.clear()
			return

		embed_pygame.bind('<KeyPress>', press_cb)
		embed_pygame.bind('<KeyRelease>', release_cb)
		embed_pygame.bind('<ButtonPress-1>', press_cb)
		embed_pygame.bind('<ButtonRelease-1>', release_cb)

		if os.name != 'nt': self.root.update()

		os.environ['SDL_WINDOWID'] = str(embed_pygame.winfo_id())
		os.environ['SDL_VIDEODRIVER'] = 'windib' if os.name == 'nt' else 'x11'
		pygame.init()
		self.screen = pygame.display.set_mode()

		self.interface = pygame.transform.scale(pygame.image.load(config.interface_path), (config.width, config.height))
		self.interface_rect = self.interface.get_rect()

		self.status_bar = pygame.transform.scale(pygame.image.load(config.status_bar_path), (config.s_width, config.s_height))
		self.status_bar_rect = self.status_bar.get_rect()

		self.sbar_hi = config.s_height

		self.disp_lcd = tk.IntVar(value = 0)

		self.rc_menu = tk.Menu(self.root, tearoff = 0)
		self.rc_menu.add_command(label = 'Step', accelerator = '\\', command = self.set_step)
		self.rc_menu.add_command(label = 'Enable single-step mode', accelerator = 'S', command = lambda: self.set_single_step(True))
		self.rc_menu.add_command(label = 'Resume execution (unpause)', accelerator = 'P', command = lambda: self.set_single_step(False))
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Jump to...', accelerator = 'J', command = self.jump.deiconify)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Set breakpoint to...', accelerator = 'B', command = self.brkpoint.deiconify)
		self.rc_menu.add_command(label = 'Clear breakpoint', accelerator = 'N', command = self.brkpoint.clear_brkpoint)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Show data memory', accelerator = 'M', command = self.data_mem.open)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Register display', accelerator = 'R', command = self.reg_display.open)
		self.rc_menu.add_separator()

		self.screen_stuff = {
	   # hwid: (alloc, used, rows, buffers,          columns)
			0: (0x8,   0x8,  4,    [],               0x40),
			2: (0x10,  0xc,  0x20, [0x8600],         96),
			3: (0x10,  0xc,  0x20, [0x87d0],         96),
			4: (0x20,  0x18, 0x40, [0xddd4, 0xe3d4], 192),
			5: (0x20,  0x18, 0x40, [0xca54, 0xd654], 192),
		}

		# first item can be anything
		self.cwii_screen_colors = (None, (170, 170, 170), (85, 85, 85), (0, 0, 0))

		self.num_buffers = len(self.screen_stuff[config.hardware_id][3])

		if self.num_buffers > 0:
			display_mode = tk.Menu(self.rc_menu, tearoff = 0)
			display_mode.add_command(label = 'Press D to switch between display modes', state = 'disabled')
			display_mode.add_separator()
			display_mode.add_radiobutton(label = 'LCD', variable = self.disp_lcd, value = 0)
			for i in range(self.num_buffers): display_mode.add_radiobutton(label = f'Buffer {i+1 if self.num_buffers > 1 else ""} @ 00:{self.screen_stuff[config.hardware_id][3][i]:04X}H', variable = self.disp_lcd, value = i+1)
			self.rc_menu.add_cascade(label = 'Display mode', menu = display_mode)
		
		self.rc_menu.add_separator()

		extra_funcs = tk.Menu(self.rc_menu, tearoff = 0)
		extra_funcs.add_command(label = 'ROM info', command = self.calc_checksum)
		extra_funcs.add_command(label = 'Write to data memory', command = self.write.deiconify)
		extra_funcs.add_command(label = 'Modify general registers', command = self.gp_modify.open)
		self.rc_menu.add_cascade(label = 'Extra functions', menu = extra_funcs)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Quit', command = self.exit_sim)

		self.root.bind('<Button-3>', self.open_popup)
		self.root.bind('\\', lambda x: self.set_step())
		self.bind_('s', lambda x: self.set_single_step(True))
		self.bind_('p', lambda x: self.set_single_step(False))
		self.bind_('j', lambda x: self.jump.deiconify())
		self.bind_('b', lambda x: self.brkpoint.deiconify())
		self.bind_('n', lambda x: self.brkpoint.clear_brkpoint())
		self.bind_('m', lambda x: self.data_mem.open())
		self.bind_('r', lambda x: self.reg_display.open())
		self.bind_('d', lambda x: self.disp_lcd.set((self.disp_lcd.get() + 1) % (self.num_buffers + 1)))

		self.single_step = True
		self.ok = True
		self.step = False
		self.breakpoint = None
		self.clock = pygame.time.Clock()

		self.prev_csr_pc = None
		self.stop_accept = [False, False]
		self.stop_mode = False

		self.ips = 0
		self.ips_start = time.time()
		self.ips_ctr = 0

		self.nsps = 1e9
		self.max_ns_per_update = 1e9
		self.max_ticks_per_update = 100
		self.tps = 10000
		self.last_time = 0
		self.passed_time = 0

		self.scr_ranges = (31, 15, 19, 23, 27, 27, 9, 9)

	def read_emu_kb(self, idx):
		if config.hardware_id == 0: return self.sim.data_mem[0x800 + idx]
		elif config.hardware_id in (4, 5): return self.sim.rw_seg[0x8e00 + idx]
		else: return self.sim.data_mem[0xe00 + idx]

	def write_emu_kb(self, idx, val):
		if config.hardware_id == 0: self.sim.data_mem[0x800 + idx] = val & 0xff
		elif config.hardware_id in (4, 5): self.sim.rw_seg[0x8e00 + idx] = val & 0xff
		else: self.sim.data_mem[0xe00 + idx] = val & 0xff

	def run(self):
		self.reset_core()
		self.set_single_step(False)
		self.pygame_loop()

		if os.name != 'nt': os.system('xset r off')
		self.root.mainloop()

	def bind_(self, char, func):
		self.root.bind(char.lower(), func)
		self.root.bind(char.upper(), func)

	@staticmethod
	def validate_hex(new_char, new_str, act_code, rang = None, spaces = False):
		act_code = int(act_code)
		if rang: rang = eval(rang)
		
		if act_code == 1:
			try: new_value_int = int(new_char, 16)
			except ValueError:
				if len(new_char) == 1:
					if new_char != ' ': return False
					elif not spaces: return False
				else:
					try: new_value_int = int(new_char.replace(' ', ''), 16)
					except ValueError: return False
			if rang and len(new_char) == 1 and len(new_str) >= len(hex(rang[-1])[2:]) and int(new_str, 16) not in rang: return False

		return True

	def read_dmem(self, addr, num_bytes, segment = 0): return self.sim.read_mem_data(segment, addr, num_bytes)

	def write_dmem(self, addr, num_bytes, data, segment = 0): self.sim.write_mem_data(segment, addr, num_bytes, data)

	def read_dmem_bytes(self, addr, num_bytes, segment = 0):
		data = b''
		bytes_grabbed = 0

		if num_bytes > 8:
			while bytes_grabbed < num_bytes:
				remaining = num_bytes - bytes_grabbed
				if remaining >= 8: grab = 8
				else: grab = remaining

				dt = self.read_dmem(addr + bytes_grabbed, grab, segment)
				data += dt.to_bytes(grab, 'little')
				bytes_grabbed += grab
			
			return data
		else: return self.read_dmem(addr, num_bytes, segment).to_bytes(num_bytes, 'little')


	def read_cmem(self, addr, segment = 0): return self.sim.read_mem_code(segment, addr, 2)

	def calc_checksum(self):
		csum = 0
		if config.hardware_id in (2, 3):
			version = self.read_dmem_bytes(0xfff4, 6, 1).decode()
			rev = self.read_dmem_bytes(0xfffa, 2, 1).decode()
			csum1 = self.read_dmem(0xfffc, 2, 1)
			for i in range(0x10000): csum -= self.read_dmem(i, 1, 8)
			for i in range(0xfffc): csum -= self.read_dmem(i, 1, 1)
			
			csum %= 0x10000
			text = f'{version} Ver{rev}\nSUM {csum:04X} {"OK" if csum == csum1 else "NG"}'
		elif config.hardware_id == 4:
			version = self.read_dmem_bytes(0xffee, 6, 3).decode()
			rev = self.read_dmem_bytes(0xfff4, 2, 3).decode()
			csum1 = self.read_dmem(0xfff6, 2, 3)
			for i in range(0, 0xfc00, 2): csum -= self.read_dmem(i, 2, 5)
			for i in range(0, 0x10000, 2): csum -= self.read_dmem(i, 2, 1)
			for i in range(0, 0x10000, 2): csum -= self.read_dmem(i, 2, 2)
			for i in range(0, 0xfff6, 2): csum -= self.read_dmem(i, 2, 3)
			
			csum %= 0x10000
			text = f'{version} Ver{rev}\nSUM {csum:04X} {"OK" if csum == csum1 else "NG"}'
		else:
			tk.messagebox.showinfo('ROM info only supports ES PLUS and CWI.')
			return
		
		tk.messagebox.showinfo('ROM info', text)

	def set_step(self): self.step = True

	def set_single_step(self, val):
		if self.single_step == val: return

		self.single_step = val
		if val:
			self.reg_display.print_regs()
			self.data_mem.get_mem()
		else: threading.Thread(target = self.core_step_loop, daemon = True).start()

	def open_popup(self, x):
		try: self.rc_menu.tk_popup(x.x_root, x.y_root)
		finally: self.rc_menu.grab_release()

	def keyboard(self):
		ki = 0xff
		if len(self.keys_pressed) > 0:
			self.sim.sfr[0x14] = 2
			
			ki_filter = self.sim.sfr[0x42]
			ko = self.sim.sfr[0x44] ^ 0xff if self.ko_mode else self.sim.sfr[0x46]

			try:
				for val in self.keys_pressed:
					if val == None: continue
					if ki_filter & (1 << val[0]): self.stop_mode = False
					if ko & (1 << val[1]): ki &= ~(1 << val[0])
			except RuntimeError: pass

		self.sim.sfr[0x40] = ki

		if not config.real_hardware:
			if self.read_emu_kb(0) in (2, 8) and [self.read_emu_kb(i) for i in (1, 2)] != [1<<2, 1<<4]: self.write_emu_kb(0, 0)

	def sbycon(self):
		sbycon = self.sim.sfr[9]

		if sbycon & (1 << 1) and all(self.stop_accept):
			self.stop_mode = True
			self.stop_accept = [False, False]
			self.sim.sfr[8] = 0
			self.sim.sfr[0x22] = 0
			self.sim.sfr[0x23] = 0

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
		if self.sim.sfr[0x25] & 1:
			counter = (self.sim.sfr[0x23] << 8) + self.sim.sfr[0x22]
			target = (self.sim.sfr[0x21] << 8) + self.sim.sfr[0x20]

			counter = (counter + tick) & 0xffff

			self.sim.sfr[0x22] = counter & 0xff
			self.sim.sfr[0x23] = counter >> 8

			if counter >= target and self.stop_mode:
				self.stop_mode = False
				self.sim.sfr[9] &= ~(1 << 1)
				self.sim.sfr[0x14] = 0x20
				if not config.real_hardware:
					self.write_emu_kb(1, 0)
					self.write_emu_kb(2, 0)

	def core_step(self):
		prev_csr_pc = f'{self.sim.core.regs.csr:X}:{self.sim.core.regs.pc:04X}H'
		prev_sbycon = self.sim.sfr[9]

		if not self.stop_mode:
			self.ok = False
			try: self.sim.u8_step()
			except Exception as e: pass
			self.sim.core.regs.csr %= 2 if config.real_hardware and config.hardware_id in (2, 3) else 0x10
			self.sim.core.regs.pc &= 0xfffe

			if prev_csr_pc != self.prev_csr_pc: self.prev_csr_pc = prev_csr_pc

			stpacp = self.sim.sfr[8]
			if self.stop_accept[0]:
				if not self.stop_accept[1]:
					if stpacp & 0xa0 == 0xa0: self.stop_accept[1] = True
					elif stpacp & 0x50 != 0x50: self.stop_accept[0] = False
			elif stpacp & 0x50 == 0x50: self.stop_accept[0] = True

			self.ok = True

			if self.ips_ctr % 1000 == 0:
				cur = time.time()
				try: self.ips = 1000 / (cur - self.ips_start)
				except ZeroDivisionError: self.ips = None
				self.ips_start = cur

			self.ips_ctr += 1

			if (self.sim.core.regs.csr << 16) + self.sim.core.regs.pc == self.breakpoint and not self.single_step:
				self.set_single_step(True)
				self.reg_display.open()
				self.keys_pressed.clear()

		self.keyboard()
		if self.stop_mode: self.timer()
		else: self.sbycon()

	def core_step_loop(self):
		while not self.single_step: self.core_step()

	def decode_instruction(self):
		self.disas.input_file = b''
		for i in range(3): self.disas.input_file += self.read_cmem((self.sim.core.regs.pc + i*2) & 0xfffe, self.sim.core.regs.csr).to_bytes(2, 'little')
		self.disas.addr = 0
		ins_str, _, dsr_prefix, _ = self.disas.decode_ins()
		if dsr_prefix:
			self.disas.last_dsr_prefix = ins_str
			last_dsr_prefix_str = f'DW {int.from_bytes(self.disas.input_file[:2], "little"):04X}'
			self.disas.addr += 2
			ins_str, _, _, used_dsr_prefix = self.disas.decode_ins()
			if used_dsr_prefix: return ins_str
			else: return last_dsr_prefix_str
		return ins_str

	def draw_text(self, text, size, x, y, color = (255, 255, 255), font_name = None, anchor = 'center'):
		font = pygame.font.SysFont(font_name, int(size))
		text_surface = font.render(str(text), True, color)
		text_rect = text_surface.get_rect()
		exec('text_rect.' + anchor + ' = (x,y)')
		self.screen.blit(text_surface, text_rect)

	@staticmethod
	@functools.lru_cache
	def get_scr_data(*scr_bytes):
		sbar = scr_bytes[0]
		screen_data_status_bar = screen_data = []

		if config.hardware_id == 0:
			screen_data_status_bar = [
			scr_bytes[0x11] & (1 << 6),  # SHIFT
			scr_bytes[0x11] & (1 << 2),  # MODE
			scr_bytes[0x12] & (1 << 6),  # STO
			scr_bytes[0x12] & (1 << 2),  # RCL
			scr_bytes[0x13] & (1 << 6),  # hyp
			scr_bytes[0x13] & (1 << 2),  # M
			scr_bytes[0x14] & (1 << 6),  # K
			scr_bytes[0x14] & (1 << 2),  # DEG
			scr_bytes[0x15] & (1 << 6),  # RAD
			scr_bytes[0x15] & (1 << 2),  # GRA
			scr_bytes[0x16] & (1 << 4),  # FIX
			scr_bytes[0x16] & (1 << 2),  # SCI
			scr_bytes[0x16] & (1 << 0),  # SD
			]

			screen_data_raw = [[scr_bytes[i*8+j] & (1 << k) for j in range(8) for k in range(7, -1, -1)] for i in range(3)]

			screen_data = []
			for j in range(12):
				inner = []
				for i in range(2):
					n = 9+j*4
					inner.extend([screen_data_raw[i][n+1], screen_data_raw[i][n], screen_data_raw[i][n+2]])
				inner.extend([screen_data_raw[2][n+1], screen_data_raw[2][n+2]])
				screen_data.append(inner)
			screen_data.append(screen_data_raw[1][6])
			screen_data.append(screen_data_raw[2][49])

		elif config.hardware_id == 4:
			screen_data_status_bar = [
			sbar[0]    & 1,  # [S]
			sbar[1]    & 1,  # [A]
			sbar[2]    & 1,  # M
			sbar[3]    & 1,  # ->[x]
			sbar[5]    & 1,  # √[]/
			sbar[6]    & 1,  # [D]
			sbar[7]    & 1,  # [R]
			sbar[8]    & 1,  # [G]
			sbar[9]    & 1,  # FIX
			sbar[0xa]  & 1,  # SCI
			sbar[0xb]  & 1,  # 𝐄
			sbar[0xc]  & 1,  # 𝒊
			sbar[0xd]  & 1,  # ∠
			sbar[0xe]  & 1,  # ⇩
			sbar[0xf]  & 1,  # ◀
			sbar[0x11] & 1,  # ▼
			sbar[0x12] & 1,  # ▲
			sbar[0x13] & 1,  # ▶
			sbar[0x15] & 1,  # ⏸
			sbar[0x16] & 1,  # ☼
			]

			screen_data = [[scr_bytes[1+i][j] & (1 << k) for j in range(0x18) for k in range(7, -1, -1)] for i in range(63)]

		else:
			screen_data_status_bar = [
			sbar[0]   & (1 << 4),  # [S]
			sbar[0]   & (1 << 2),  # [A]
			sbar[1]   & (1 << 4),  # M
			sbar[1]   & (1 << 1),  # STO
			sbar[2]   & (1 << 6),  # RCL
			sbar[3]   & (1 << 6),  # STAT
			sbar[4]   & (1 << 7),  # CMPLX
			sbar[5]   & (1 << 6),  # MAT
			sbar[5]   & (1 << 1),  # VCT
			sbar[7]   & (1 << 5),  # [D]
			sbar[7]   & (1 << 1),  # [R]
			sbar[8]   & (1 << 4),  # [G]
			sbar[8]   & (1 << 0),  # FIX
			sbar[9]   & (1 << 5),  # SCI
			sbar[0xa] & (1 << 6),  # Math
			sbar[0xa] & (1 << 3),  # ▼
			sbar[0xb] & (1 << 7),  # ▲
			sbar[0xb] & (1 << 4),  # Disp
			]
			
			screen_data = [[scr_bytes[1+i][j] & (1 << k) for j in range(0xc) for k in range(7, -1, -1)] for i in range(31)]

		return screen_data_status_bar, screen_data
	@staticmethod
	@functools.lru_cache
	def get_scr_data_cwii(addr, scr_bytes_lo, scr_bytes_hi):
		sbar = scr_bytes_lo[0]

		screen_data_status_bar = [
		sbar[1]    & 1,  # [S]
		sbar[3]    & 1,  # √[]/
		sbar[4]    & 1,  # [D]
		sbar[5]    & 1,  # [R]
		sbar[6]    & 1,  # [G]
		sbar[7]    & 1,  # FIX
		sbar[8]    & 1,  # SCI
		sbar[0xa]  & 1,  # 𝐄
		sbar[0xb]  & 1,  # 𝒊
		sbar[0xc]  & 1,  # ∠
		sbar[0xd]  & 1,  # ⇩
		sbar[0xe]  & 1,  # (✓)
		sbar[0x10]  & 1,  # ◀
		sbar[0x11] & 1,  # ▼
		sbar[0x12] & 1,  # ▲
		sbar[0x13] & 1,  # ▶
		sbar[0x15] & 1,  # ⏸
		sbar[0x16] & 1,  # ☼
		]

		screen_data = [[(2 if scr_bytes_hi[1+i][j] & (1 << k) > 0 else 0) + (1 if scr_bytes_lo[1+i][j] & (1 << k) else 0) for j in range(0x18) for k in range(7, -1, -1)] for i in range(63)]

		return screen_data_status_bar, screen_data

	def reset_core(self):
		self.core_reset()
		self.prev_csr_pc = None
		self.reg_display.print_regs()
		self.data_mem.get_mem()

	def core_reset(self):
		self.sim.write_reg_qr(0, 0)
		self.sim.write_reg_qr(8, 0)
		self.sim.core.regs.pc = self.init_pc
		self.sim.core.regs.csr = 0
		self.sim.core.regs.lcsr = 0
		self.sim.core.regs.lr = 0
		self.sim.core.regs.psw = 0

		for i in range(3):
			self.sim.core.regs.ecsr[i] = 0
			self.sim.core.regs.elr[i] = 0
			self.sim.core.regs.epsw[i] = 0

		self.sim.core.regs.sp = self.init_sp
		self.sim.core.regs.ea = 0
		self.sim.core.regs.dsr = 0

	def exit_sim(self):
		if self.rom8: os.remove(config.interface_path)

		pygame.quit()
		self.root.quit()
		if os.name != 'nt': os.system('xset r on')
		sys.exit()

	def pygame_loop(self):
		if self.single_step and self.step: self.core_step()
		if (self.single_step and self.step) or not self.single_step:
			self.reg_display.print_regs()
			if self.data_mem.winfo_viewable(): self.data_mem.get_mem()

		self.clock.tick()

		self.screen.fill((214, 227, 214))
		self.screen.blit(self.interface, self.interface_rect)
		try:
			for key in self.keys_pressed: self.screen.blit(self.interface, config.keymap[key][0][:2], config.keymap[key][0], pygame.BLEND_RGBA_ADD)
		except RuntimeError: pass

		if config.hardware_id in self.screen_stuff: scr = self.screen_stuff[config.hardware_id]
		else: scr = self.screen_stuff[3]

		disp_lcd = self.disp_lcd.get()
		if self.num_buffers > 0: self.draw_text(f'Displaying {"buffer "+str(disp_lcd if self.num_buffers > 1 else "")+" @ 00:"+format(scr[3][disp_lcd-1], "04X")+"H" if disp_lcd else "LCD"}', 22, config.width // 2, self.text_y, config.pygame_color, anchor = 'midtop')

		if config.hardware_id == 0: scr_bytes = self.read_dmem_bytes(0xf800, 0x20)
		else: scr_bytes = [self.read_dmem_bytes(scr[3][disp_lcd-1] + i*scr[1] if disp_lcd else 0xf800 + i*scr[0], scr[1]) for i in range(scr[2])]
		if config.hardware_id == 5:
			if disp_lcd: scr_bytes_hi = tuple(self.read_dmem_bytes(scr[3][disp_lcd-1] + scr[1]*scr[2] + i*scr[1], scr[1]) for i in range(scr[2]))
			else: scr_bytes_hi = tuple(self.read_dmem_bytes(0x9000 + i*scr[0], scr[1], 8) for i in range(scr[2]))
			screen_data_status_bar, screen_data = self.get_scr_data_cwii(scr[3][disp_lcd-1] if disp_lcd else 0xf800, tuple(scr_bytes), scr_bytes_hi)
		else: screen_data_status_bar, screen_data = self.get_scr_data(*scr_bytes)
		
		scr_range = self.read_dmem(0xf030, 1) & 7
		scr_mode = self.read_dmem(0xf031, 1) & 7

		if (not disp_lcd and scr_mode in (5, 6)) or disp_lcd:
			for i in range(len(screen_data_status_bar)):
				crop = config.status_bar_crops[i]
				if screen_data_status_bar[i]: self.screen.blit(self.status_bar, (config.screen_tl_w + crop[0], config.screen_tl_h), crop)
	
		if config.hardware_id == 0:
			offset = 0
			offset_h = 5
			small_offset = 0
			for i in range(14):
				n = lambda j: config.pix*(5*i+offset+j) if i < 11 else config.pix*(11*5+offset) + config.pix_s*(small_offset+5*(i-11)+j)
				pix = config.pix if i < 11 else config.pix_s
				if i == 0:
					if screen_data[-2]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(1), config.screen_tl_h + offset_h + self.sbar_hi + pix*5,  pix*2, pix))
				elif i == 11:
					if screen_data[-1]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(1), config.screen_tl_h + offset_h + self.sbar_hi + pix*5,  pix*2, pix))
				else:
					data = screen_data[i-(1 if i < 12 else 2)]
					if data[0]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(1), config.screen_tl_h + offset_h + self.sbar_hi,                 pix*2, pix))
					if data[1]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(0), config.screen_tl_h + offset_h + self.sbar_hi + pix,    pix,   pix*4))
					if data[2]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(3), config.screen_tl_h + offset_h + self.sbar_hi + pix,    pix,   pix*4))
					if data[3]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(1), config.screen_tl_h + offset_h + self.sbar_hi + pix*5,  pix*2, pix))
					if data[4]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(0), config.screen_tl_h + offset_h + self.sbar_hi + pix*6,  pix,   pix*4))
					if data[5]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(3), config.screen_tl_h + offset_h + self.sbar_hi + pix*6,  pix,   pix*4))
					if data[6]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + n(1), config.screen_tl_h + offset_h + self.sbar_hi + pix*10, pix*2, pix))
					if data[7] and i < 11: pygame.draw.circle(self.screen, self.pix_color, (config.screen_tl_w + n(4.5), config.screen_tl_h + offset_h + self.sbar_hi + config.pix*11), config.pix * (3/4))
		elif config.hardware_id == 5:
			for y in range(scr[2] - 1):
				for x in range(scr[4]):
					if screen_data[y][x]: pygame.draw.rect(self.screen, self.cwii_screen_colors[screen_data[y][x]], (config.screen_tl_w + x*config.pix, config.screen_tl_h + self.sbar_hi + y*config.pix, config.pix, config.pix))
		else:
			if (not disp_lcd and scr_mode == 5) or disp_lcd:
				for y in range(self.scr_ranges[scr_range] if not disp_lcd and config.hardware_id in (2, 3) else scr[2] - 1):
					for x in range(scr[4]):
						if screen_data[y][x]: pygame.draw.rect(self.screen, self.pix_color, (config.screen_tl_w + x*config.pix, config.screen_tl_h + self.sbar_hi + y*config.pix, config.pix, config.pix))

		if self.single_step: self.step = False
		else: self.draw_text(f'{self.clock.get_fps():.1f} FPS', 22, config.width // 2, self.text_y + 22 if self.num_buffers > 0 else self.text_y, config.pygame_color, anchor = 'midtop')

		pygame.display.update()
		self.root.update()
		self.root.after(0, self.pygame_loop)

if __name__ == '__main__':
	sim = Sim()
	sim.run()
