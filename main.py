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
import importlib
import importlib.util
import threading
import traceback
try:
	import klembord
	no_klembord = False
except ImportError: no_klembord = True
if os.name == 'nt': import win32clipboard
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font
import tkinter.messagebox
import tkinter.filedialog
from enum import IntEnum

sys.path.append('pyu8disas')
from pyu8disas import main as disas_main
from pyu8disas.labeltool import labeltool
from tool8 import tool8
import platform

try:
	from bcd import BCD
	bcd = True
except ImportError: bcd = False

if sys.version_info < (3, 6, 0, 'alpha', 4):
	print(f'This program requires at least Python 3.6.0a4. (You are running Python {platform.python_version()})')
	sys.exit()

if pygame.version.vernum < (2, 2, 0):
	print(f'This program requires at least Pygame 2.2.0. (You are running Pygame {pygame.version.ver})')
	sys.exit()

level = logging.INFO
logging.basicConfig(format = '%(levelname)s: %(message)s', level = level)

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
		("regs",			u8_regs_t),
		("cur_dsr",			ctypes.c_uint8),
		("mem",				u8_mem_t),
		('last_swi',		ctypes.c_uint8),
		('last_write',		ctypes.c_uint32),
		('last_write_size', ctypes.c_uint8),
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

##
# Core
##

class Core:
	def __init__(self, sim, rom, flash):
		self.sim = sim
		ko_mode = self.sim.ko_mode

		self.core = u8_core_t()

		# Initialise memory
		self.code_mem = (ctypes.c_uint8 * len(rom))(*rom)
		if config.hardware_id == 2 and self.sim.is_5800p: self.flash_mem = (ctypes.c_uint8 * len(flash))(*flash)

		rwin_sizes = {
		0: 0xdfff,
		2: 0x7fff,
		3: 0x7fff,
		4: 0xcfff,
		5: 0x8fff,
		6: 0xafff,
		}

		data_size = {
		0: (0xe000, 0x1000),
		3: (0x8000, 0xe00 if config.real_hardware else 0x7000),
		4: (0xd000, 0x2000),
		5: (0x9000, 0x6000),
		6: (0xb000, 0x4000),
		}

		self.sdata = data_size[config.hardware_id if config.hardware_id in data_size else 3]

		self.data_mem = (ctypes.c_uint8 * self.sdata[1])()
		self.sfr = (ctypes.c_uint8 * 0x1000)()
		if hasattr(config, 'pd_value'): self.sfr[0x50] = config.pd_value

		if config.hardware_id in (4, 5): self.rw_seg = (ctypes.c_uint8 * 0x10000)()

		read_functype = ctypes.CFUNCTYPE(ctypes.c_uint8, ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16)
		write_functype = ctypes.CFUNCTYPE(None, ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8)

		blank_code_mem_f = read_functype(self.blank_code_mem)
		battery_f = read_functype(self.battery)
		read_sfr_f = read_functype(self.read_sfr)
		write_sfr_f = write_functype(self.write_sfr)
		read_dsr_f = read_functype(self.read_dsr)
		write_dsr_f = write_functype(self.write_dsr)

		regions = [
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_CODE, False, 0x00000,       len(rom) - 1,                    u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x00000,       rwin_sizes[config.hardware_id],  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  self.sdata[0], sum(self.sdata) - 1,             u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.data_mem, 0x00000))),
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x0F000, 0x0F000,  u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(read_dsr_f, write_dsr_f))),
			u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x0F001, 0x0FFFF,  u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(read_sfr_f, write_sfr_f))),
		]

		if config.real_hardware and config.hardware_id != 2: regions.append(u8_mem_reg_t(u8_mem_type_e.U8_REGION_CODE, False, len(rom), 0xFFFFF, u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(blank_code_mem_f))))

		if config.hardware_id == 4: regions.extend((
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x10000, 0x3FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x10000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x40000, 0x4FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.rw_seg,   0x00000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x50000, 0x5FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
			))
		elif config.hardware_id == 5:
			regions.extend((
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x10000, 0x7FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x10000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x50000, 0x5FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x80000, 0x8FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.rw_seg,   0x00000))),
			))

		elif config.hardware_id == 6:
			regions.extend((
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x10000, 0x3FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x10000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x80000, 0xAFFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))),
				u8_mem_reg_t(u8_mem_type_e.U8_REGION_CODE, False, len(rom), 0xFFFFF, u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(blank_code_mem_f))),
			))

		else:
			regions.append(u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x10000, 0x1FFFF,  u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x10000))))
			if ko_mode == 0: regions.append(u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x80000, 0x8FFFF, u8_mem_acc_e.U8_MACC_ARR, _acc_union(uint8_ptr(self.code_mem, 0x00000))))
			if config.hardware_id == 2 and self.sim.is_5800p:
				regions.extend((
					u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, False, 0x100000, 0x100000,u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(blank_code_mem_f))),
					u8_mem_reg_t(u8_mem_type_e.U8_REGION_DATA, True,  0x40000,  0x47FFF, u8_mem_acc_e.U8_MACC_ARR,  _acc_union(uint8_ptr(self.flash_mem, 0x20000))),
					u8_mem_reg_t(u8_mem_type_e.U8_REGION_BOTH, False, 0x80000,  0xFFFFF, u8_mem_acc_e.U8_MACC_ARR,  _acc_union(uint8_ptr(self.flash_mem, 0x00000))),
					u8_mem_reg_t(u8_mem_type_e.U8_REGION_CODE, False, len(rom), 0x7FFFF, u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(blank_code_mem_f))),
				))
			elif config.real_hardware: regions.append(u8_mem_reg_t(u8_mem_type_e.U8_REGION_CODE, False, len(rom), 0xFFFFF, u8_mem_acc_e.U8_MACC_FUNC, _acc_union(None, _acc_func(blank_code_mem_f))))

		self.core.mem.num_regions = len(regions)
		self.core.mem.regions = ctypes.cast((u8_mem_reg_t * len(regions))(*regions), ctypes.POINTER(u8_mem_reg_t))

		# Initialise SP and PC
		self.core.regs.sp = rom[0] | rom[1] << 8
		self.core.regs.pc = rom[2] | rom[3] << 8
	
	def core_step(self): sim_lib.core_step(ctypes.pointer(self.core), config.real_hardware, config.hardware_id, self.sim.is_5800p)

	def u8_reset(self): sim_lib.u8_reset(ctypes.pointer(self.core))
	
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
		try:
			if config.hardware_id == 6:
				if addr == 0xe: self.sfr[addr] = value == 0x5a
				elif addr == 0x900: self.sfr[addr] = 0x34
				elif addr == 0x901: self.sfr[addr] = value == 0
				else: self.sfr[addr] = value
			elif addr == 0x46 and config.hardware_id == 2 and self.sim.is_5800p: pass
			else: self.sfr[addr] = value
			if bcd: self.sim.bcd.bcd_peripheral(addr)
		except IndexError:
			label = self.sim.get_instruction_label((self.core.regs.csr << 16) + self.core.regs.pc)
			logging.warning(f'Overflown write to {(0xf000 + addr) & 0xffff:04X}H @ {self.sim.get_addr_label(self.core.regs.csr, self.core.regs.pc-2)}')
			self.write_mem_data(seg, (0xf000 + addr) & 0xffff, 1)

	def read_sfr(self, core, seg, addr):
		addr += 1
		try:
			if addr == 0x46 and config.hardware_id == 2 and self.sim.is_5800p: return 4
			return self.sfr[addr]
		except IndexError:
			label = self.sim.get_instruction_label((self.core.regs.csr << 16) + self.core.regs.pc)
			logging.warning(f'Overflown read from {(0xf000 + addr) & 0xffff:04X}H @ {self.sim.get_addr_label(self.core.regs.csr, self.core.regs.pc-2)}')
			return self.read_mem_data(seg, (0xf000 + addr) & 0xffff, 1)

	def read_dsr(self, core, seg, addr): return self.core.regs.dsr
	def write_dsr(self, core, seg, addr, value):
		self.sfr[0] = value
		self.core.regs.dsr = value

	def battery(self, core, seg, addr): return 0xff

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
		self.sim.write_brkpoint = None
		self.sim.reg_display.print_regs()

class WriteBrkpoint(tk.Toplevel):
	def __init__(self, sim):
		super(WriteBrkpoint, self).__init__()
		self.sim = sim

		self.withdraw()
		self.geometry('300x125')
		self.resizable(False, False)
		self.title('Set breakpoint')
		self.protocol('WM_DELETE_WINDOW', self.withdraw)
		self.vh_reg = self.register(self.sim.validate_hex)
		ttk.Label(self, text = 'Single-step mode will be activated there is a write\nto the specified address. 1 write breakpoint at a time.\n(please input hex bytes)', justify = 'center').pack()
		self.csr = tk.Frame(self); self.csr.pack(fill = 'x')
		ttk.Label(self.csr, text = 'Segment').pack(side = 'left')
		self.csr_entry = ttk.Entry(self.csr, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0x100))); self.csr_entry.pack(side = 'right')
		self.csr_entry.insert(0, '0')
		self.pc = tk.Frame(self); self.pc.pack(fill = 'x')
		ttk.Label(self.pc, text = 'Address').pack(side = 'left')
		self.pc_entry = ttk.Entry(self.pc, validate = 'key', validatecommand = (self.vh_reg, '%S', '%P', '%d', range(0x10000))); self.pc_entry.pack(side = 'right')
		ttk.Button(self, text = 'OK', command = self.set_brkpoint).pack(side = 'bottom')
		self.bind('<Return>', lambda x: self.set_brkpoint())
		self.bind('<Escape>', lambda x: self.withdraw())

	def set_brkpoint(self):
		csr_entry = self.csr_entry.get()
		pc_entry = self.pc_entry.get()
		if csr_entry == '' or pc_entry == '': return
		self.sim.write_brkpoint = ((int(csr_entry, 16) if csr_entry else 0) << 16) + (int(pc_entry, 16) if pc_entry else 0)
		self.sim.reg_display.print_regs()
		self.withdraw()

		self.csr_entry.delete(0, 'end'); self.csr_entry.insert(0, '0')
		self.pc_entry.delete(0, 'end')

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
		if config.hardware_id == 2 and self.sim.is_5800p: segments.append('Flash RAM (04:0000H - 04:7FFFH)')

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
			elif seg.startswith('Flash RAM'): data = self.format_mem(bytes(self.sim.sim.flash_mem[0x20000:0x28000]), 0, 4)
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
		self.bind('\\', lambda x: self.sim.set_step())
		self['bg'] = config.console_bg

		self.info_label = tk.Label(self, font = config.console_font, fg = config.console_fg, bg = config.console_bg, justify = 'left', anchor = 'nw')
		self.info_label.pack(side = 'left', fill = 'both')

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
Opcode          ''' + ' '.join(format(self.sim.read_cmem((pc + i*2) & 0xfffe, csr), '04X') for i in range(ins_len // 2)) + f'''
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
Breakpoint               {format(self.sim.breakpoint >> 16, 'X') + ':' + format(self.sim.breakpoint % 0x10000, '04X') + 'H' if self.sim.breakpoint is not None else 'None'}
Write breakpoint         {format(self.sim.write_brkpoint >> 16, 'X') + ':' + format(self.sim.write_brkpoint % 0x10000, '04X') + 'H' if self.sim.write_brkpoint is not None else 'None'}
STOP acceptor            1 [{'x' if self.sim.stop_accept[:][0] else ' '}]  2 [{'x' if self.sim.stop_accept[:][1] else ' '}]
STOP mode                [{'x' if self.sim.stop_mode else ' '}]
Last SWI value           {last_swi if last_swi < 0x40 else 'None'}\
{nl+'Counts until next WDTINT ' + self.sim.wdt.counter if config.hardware_id == 6 else ''}\
{(nl+'Instructions per second  ' + (format(self.sim.ips, '.1f') if self.sim.ips is not None and not self.sim.single_step else 'None') if self.sim.enable_ips else '')}\
'''

	@staticmethod
	@functools.lru_cache
	def fmt_x(val): return 'x' if int(val) else ' '

class WDT:
	def __init__(self, sim):
		self.sim = sim
		self.mode = None
		self.ms = (4096, 16384, 65536, 262144)
		self.counter = 0

	def start_wdt(self, mode = 2):
		self.mode = mode
		self.counter = self.ms[self.mode]

	def dec_wdt(self):
		self.counter -= 1
		if self.counter == 0: self.wdt_loop()

	def wdt_loop(self):
		self.sim.sim.sfr[0x18] |= 1
		self.mode = self.sim.sim.sfr[0xf] & 3
		self.counter = self.ms[self.mode]

class Sim:
	def __init__(self, no_klembord, bcd):
		self.copyclip = not no_klembord or (no_klembord and os.name == 'nt')

		try:
			im = PIL.Image.open(config.status_bar_path)
			size = im.size
			if not hasattr(config, 's_width'):  config.s_width  = size[0]
			if not hasattr(config, 's_height'): config.s_height = size[1]
		except (AttributeError, IOError): pass

		self.rom8 = config.rom8 if hasattr(config, 'rom8') else False
		self.use_char = config.use_char if hasattr(config, 'use_char') else False
		self.ko_mode = config.ko_mode if hasattr(config, 'ko_mode') and config.ko_mode == 1 else 0
		self.text_y = config.text_y if hasattr(config, 'text_y') else 22
		self.pix_color = config.pix_color if hasattr(config, 'pix_color') else (0, 0, 0)
		self.pix_hi = config.pix_hi if hasattr(config, 'pix_hi') else config.pix
		self.is_5800p = config.is_5800p if hasattr(config, 'is_5800p') else False

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

		if config.hardware_id == 2 and self.is_5800p:
			flash = open(config.flash_rom_file, 'rb').read()
			if len(flash) % 2 != 0:
				logging.error('Flash ROM size cannot be odd')
				sys.exit()
		else: flash = None

		if any((not hasattr(config, 'width'), not hasattr(config, 'height'))):
			try:
				im = PIL.Image.open(config.interface_path)
				size = im.size
				if not hasattr(config, 'width'):  config.width  = size[0]
				if not hasattr(config, 'height'): config.height = size[1]
			except (AttributeError, IOError) as e:
				logging.error(e)
				sys.exit()

		if config.hardware_id == 2: self.ko_mode = 1 
		elif config.hardware_id != 3: self.ko_mode = 0

		self.sim = Core(self, rom, flash)

		self.root = DebounceTk()
		self.root.geometry(f'{config.width}x{config.height}')
		self.root.resizable(False, False)
		try: self.root.title(config.root_w_name)
		except AttributeError: self.root.title('u8-emu-frontend')
		self.root.protocol('WM_DELETE_WINDOW', self.exit_sim)
		self.root.focus_set()

		self.init_sp = rom[0] | rom[1] << 8
		self.init_pc = rom[2] | rom[3] << 8

		self.keys_pressed = set()
		self.keys = []
		if hasattr(config, 'keymap'):
			for key in [i[1:] for i in config.keymap.values()]: self.keys.extend(key)

		self.jump = Jump(self)
		self.brkpoint = Brkpoint(self)
		self.write_brkpoint = WriteBrkpoint(self)
		self.write = Write(self)
		self.data_mem = DataMem(self)
		self.gp_modify = GPModify(self)
		self.reg_display = RegDisplay(self)
		self.wdt = WDT(self)
		if bcd: self.bcd = BCD(self)
		self.disas = disas_main.Disasm()

		if hasattr(config, 'labels'):
			self.labels = {self.init_pc: ['start', True]}
			if rom[4] | rom[5] << 8 != self.init_pc: self.labels[rom[4] | rom[5] << 8] = ['brk', True]
			for file in config.labels:
				labels, data_labels, data_bit_labels = labeltool.load_labels(open(file), 0)
				for key in labels: self.labels[key] = labels[key]
				for key in data_labels: self.disas.data_labels[key] = data_labels[key]
				for key in data_bit_labels: self.disas.data_bit_labels[key] = data_bit_labels[key]
			self.labels = {i: self.labels[i] for i in sorted(self.labels.keys())}
			self.disas.labels = self.labels.copy()
		else: self.labels = {}

		embed_pygame = tk.Frame(self.root, width = config.width, height = config.height)
		embed_pygame.pack(side = 'left')
		embed_pygame.focus_set()

		def press_cb(event):
			for k, v in config.keymap.items():
				p = v[0]
				if (event.type == tk.EventType.ButtonPress and event.x in range(p[0], p[0]+p[2]) and event.y in range(p[1], p[1]+p[3])) \
				or (event.type == tk.EventType.KeyPress and (event.char if self.use_char else event.keysym.lower()) in v[1:]):
					if config.hardware_id != 6:
						self.keys_pressed.add(k)
						if k is None: self.reset_core()
						else:
							if not config.real_hardware:
								self.stop_mode = False
								self.write_emu_kb(1, 1 << k[0])
								self.write_emu_kb(2, 1 << k[1])
							else:
								self.sim.sfr[0x14] = 2
								if self.sim.sfr[0x42] & (1 << k[0]): self.stop_mode = False
					elif len(self.keys_pressed) == 0: self.curr_key = k

		def release_cb(event):
			if config.hardware_id != 6:
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
			else: self.curr_key = 0

		if hasattr(config, 'keymap'):
			embed_pygame.bind('<KeyPress>', press_cb)
			embed_pygame.bind('<KeyRelease>', release_cb)
			embed_pygame.bind('<ButtonPress-1>', press_cb)
			embed_pygame.bind('<ButtonRelease-1>', release_cb)

		if os.name != 'nt': self.root.update()

		os.environ['SDL_WINDOWID'] = str(embed_pygame.winfo_id())
		os.environ['SDL_VIDEODRIVER'] = 'windib' if os.name == 'nt' else 'x11'
		pygame.init()
		self.screen = pygame.display.set_mode()

		try:
			self.interface = pygame.transform.smoothscale(pygame.image.load(config.interface_path), (config.width, config.height))
			self.interface_rect = self.interface.get_rect()
		except IOError as e:
			logging.warning(e)
			self.interface = None
		except AttributeError: self.interface = None

		try:
			self.status_bar = pygame.transform.scale(pygame.image.load(config.status_bar_path), (config.s_width, config.s_height))
			self.status_bar_rect = self.status_bar.get_rect()
		except IOError as e:
			logging.warning(e)
			self.status_bar = None
		except AttributeError: self.status_bar = None
		
		if hasattr(config, 's_height'): self.sbar_hi = config.s_height
		else: self.sbar_hi = 0

		self.disp_lcd = tk.IntVar(value = 0)
		self.enable_ips = False
		self.enable_ips_tk = tk.BooleanVar(value = self.enable_ips)
		self.enable_fps = True
		self.enable_fps_tk = tk.BooleanVar(value = self.enable_fps)
		self.always_update = False
		self.always_update_tk = tk.BooleanVar(value = self.always_update)

		self.rc_menu = tk.Menu(self.root, tearoff = 0)
		self.rc_menu.add_command(label = 'Step', accelerator = '\\', command = self.set_step)
		self.rc_menu.add_command(label = 'Enable single-step mode', accelerator = 'S', command = lambda: self.set_single_step(True))
		self.rc_menu.add_command(label = 'Resume execution (unpause)', accelerator = 'P', command = lambda: self.set_single_step(False))
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Jump to...', accelerator = 'J', command = self.jump.deiconify)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Set breakpoint to...', accelerator = 'B', command = self.brkpoint.deiconify)
		self.rc_menu.add_command(label = 'Set write breakpoint to...', command = self.write_brkpoint.deiconify)
		self.rc_menu.add_command(label = 'Clear breakpoints', accelerator = 'N', command = self.brkpoint.clear_brkpoint)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Show data memory', accelerator = 'M', command = self.data_mem.open)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Register display', accelerator = 'R', command = self.reg_display.open)
		self.rc_menu.add_separator()

		self.screen_stuff = {
	   # hwid: (alloc, used, rows,buffers,          columns)
			0: (0x8,   0x8,  4,   [],               64),
			2: (0x10,  0xc,  32,  [0x80e0 if self.is_5800p else 0x8600], 96),
			3: (0x10,  0xc,  32,  [0x87d0],         96),
			4: (0x20,  0x18, 64,  [0xddd4, 0xe3d4], 192),
			5: (0x20,  0x18, 64,  [0xca54, 0xd654], 192),
			6: (0x8,   0x8,  192, [None, None],     64),
		}

		if config.hardware_id in self.screen_stuff: self.scr = self.screen_stuff[config.hardware_id]
		else: self.scr = self.screen_stuff[3]
		
		if config.hardware_id == 6: self.display = pygame.Surface((self.scr[2]*config.pix, (self.scr[4])*self.pix_hi + self.sbar_hi))
		else: self.display = pygame.Surface((self.scr[4]*config.pix, (self.scr[2] - 1)*self.pix_hi + self.sbar_hi))
		self.display.fill((255, 255, 255))

		if config.hardware_id != 6: self.int_table = {
			# (irqsfr,bit):(vtadr,ie_sfr,bit, name)
				(0x14, 0): (0x08, None, None, 'WDTINT'),     # Watchdog timer interrupt
				(0x14, 1): (0x0a, 0x10, 1,    'XI0INT'),     # External interrupt 0
			 	(0x14, 2): (0x0c, 0x10, 2,    'XI1INT'),     # External interrupt 1
				(0x14, 3): (0x0e, 0x10, 3,    'XI2INT'),     # External interrupt 2
				(0x14, 4): (0x10, 0x10, 4,    'XI3INT'),     # External interrupt 3
				(0x14, 5): (0x12, 0x10, 5,    'TM0INT'),     # Timer 0 interrupt
				(0x14, 6): (0x14, 0x10, 6,    'L256SINT'),
				(0x14, 7): (0x16, 0x10, 7,    'L1024SINT'),
				(0x15, 0): (0x18, 0x11, 0,    'L4096SINT'),
				(0x15, 1): (0x1a, 0x11, 1,    'L16384SINT'),
				(0x15, 2): (0x1c, 0x11, 2,    'SIO0INT'),    # Synchronous serial port 0 interrupt
				(0x15, 3): (0x1e, 0x11, 3,    'I2C0INT'),    # I²C bus 0 interrupt
				(0x15, 4): (0x20, 0x11, 4,    'I2C1INT'),    # I²C bus 1 interrupt
				(0x15, 5): (0x22, 0x11, 5,    'BENDINT'),
				(0x15, 6): (0x24, 0x11, 6,    'BLOWINT'),
				(0x15, 7): (0x26, 0x11, 7,    'RTCINT'),     # Real-time clock interrupt
				(0x16, 0): (0x28, 0x12, 0,    'AL0INT'),     # RTC alarm 0 interrupt
				(0x16, 1): (0x2a, 0x12, 1,    'AL1INT'),     # RTC alarm 1 interrupt
			}
		else: self.int_table = {
			# (irqsfr,bit):(vtadr,ie_sfr,bit, name)
				(0x18, 0): (0x08, None, None, 'WDTINT'),     # Watchdog timer interrupt
			}

		# first item can be anything
		self.cwii_screen_colors = (None, (170, 170, 170), (85, 85, 85), (0, 0, 0))

		self.num_buffers = len(self.screen_stuff[config.hardware_id][3]) if config.hardware_id in self.screen_stuff else 0

		if self.num_buffers > 0 and config.hardware_id != 6:
			display_mode = tk.Menu(self.rc_menu, tearoff = 0)
			display_mode.add_command(label = 'Press D to switch between display modes', state = 'disabled')
			display_mode.add_separator()
			display_mode.add_radiobutton(label = 'LCD', variable = self.disp_lcd, value = 0)
			for i in range(self.num_buffers): display_mode.add_radiobutton(label = f'Buffer {i+1 if self.num_buffers > 1 else ""} @ {self.screen_stuff[config.hardware_id][3][i]:04X}H', variable = self.disp_lcd, value = i+1)
			self.rc_menu.add_cascade(label = 'Display mode', menu = display_mode)
			self.rc_menu.add_separator()
		elif config.hardware_id == 6: self.disp_lcd.set(1)

		extra_funcs = tk.Menu(self.rc_menu, tearoff = 0)
		extra_funcs.add_command(label = 'ROM info', command = self.calc_checksum)
		extra_funcs.add_command(label = 'Write to data memory', command = self.write.deiconify)
		extra_funcs.add_command(label = 'Modify general registers', command = self.gp_modify.open)
		if config.hardware_id == 2 and self.is_5800p: extra_funcs.add_command(label = 'Save flash ROM', command = self.save_flash)

		save_display = tk.Menu(extra_funcs, tearoff = 0)
		save_display.add_command(label = f'Copy to clipboard{" (klembord package required)" if not self.copyclip else ""}', state = 'normal' if self.copyclip else 'disabled', command = self.save_display)
		save_display.add_command(label = 'Save as...', command = lambda: self.save_display(False))
		extra_funcs.add_cascade(label = 'Save display', menu = save_display)

		self.rc_menu.add_cascade(label = 'Extra functions', menu = extra_funcs)
		
		options = tk.Menu(self.rc_menu, tearoff = 0)
		options.add_checkbutton(label = 'IPS display (in register display)', variable = self.enable_ips_tk, command = self.set_enable_ips)
		options.add_checkbutton(label = 'FPS display', variable = self.enable_fps_tk, command = self.set_enable_fps)
		if config.hardware_id == 6: options.add_checkbutton(label = 'Always update display', variable = self.always_update_tk, command = self.set_always_update)
		self.rc_menu.add_cascade(label = 'Options', menu = options)

		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Reset core', command = self.reset_core)
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
		if config.hardware_id != 6: self.bind_('d', lambda x: self.disp_lcd.set((self.disp_lcd.get() + 1) % (self.num_buffers + 1)))

		self.single_step = True
		self.ok = True
		self.step = False
		self.breakpoint = None
		self.write_brkpoint = None
		self.clock = pygame.time.Clock()

		self.prev_csr_pc = None
		self.prev_prev_csr_pc = None
		self.stop_accept = self.get_var('stop_accept', ctypes.c_bool * 2)
		self.stop_mode = False

		self.nsps = 1e9
		self.max_ns_per_update = 1e9
		self.max_ticks_per_update = 100
		self.tps = 10000
		self.last_time = 0
		self.passed_time = 0

		self.int_timer = 0

		self.scr_ranges = (31, 15, 19, 23, 27, 27, 9, 9)

		# TI MathPrint only
		self.screen_changed = False
		self.curr_key = 0

	def get_var(self, var, typ): return typ.in_dll(sim_lib, var)

	def set_enable_ips(self):
		self.enable_ips = self.enable_ips_tk.get()
		if self.enable_ips:
			self.ips = 0
			self.ips_start = time.time()
			self.ips_ctr = 0

	def set_enable_fps(self): self.enable_fps = self.enable_fps_tk.get()
	def set_always_update(self): self.always_update = self.always_update_tk.get()

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
		if config.hardware_id == 6: self.wdt.start_wdt()
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
		if config.hardware_id == 3:
			version = self.read_dmem_bytes(0xfff4, 6, 1).decode()
			rev = self.read_dmem_bytes(0xfffa, 2, 1).decode()
			csum1 = self.read_dmem(0xfffc, 2, 1)
			for i in range(0x8000 if self.ko_mode else 0x10000): csum -= self.read_dmem(i, 1, 0 if self.ko_mode else 8)
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
		elif config.hardware_id == 5:
			version = self.read_dmem_bytes(0x1fee, 6, 7).decode()
			rev = self.read_dmem_bytes(0x1ff4, 2, 7).decode()
			csum1 = self.read_dmem(0x1ff6, 2, 7)
			for i in range(0, 0xfc00, 2): csum -= self.read_dmem(i, 2, 8)
			for i in range(0, 0x10000, 2): csum -= self.read_dmem(i, 2, 1)
			for i in range(0, 0x10000, 2): csum -= self.read_dmem(i, 2, 2)
			for i in range(0, 0x10000, 2): csum -= self.read_dmem(i, 2, 3)
			for i in range(0, 0x10000, 2): csum -= self.read_dmem(i, 2, 4)
			for i in range(0, 0xe000, 2): csum -= self.read_dmem(i, 2, 5)
			for i in range(0, 0x1ff6, 2): csum -= self.read_dmem(i, 2, 7)
			
			csum %= 0x10000
			text = f'{version}\nV.{rev} Bt OK\nSUM{csum:04X} {"OK" if csum == csum1 else "NG"}'
		else:
			tk.messagebox.showinfo('ROM info only supports ES PLUS, CWI and CWII.')
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
		try:
			sstep_bak = self.single_step
			self.set_single_step(True)
			self.rc_menu.tk_popup(x.x_root, x.y_root)
		finally:
			self.rc_menu.grab_release()
			self.set_single_step(sstep_bak)

	def keyboard(self):
		ki = 0xff
		if len(self.keys_pressed) > 0:
			ko = self.sim.sfr[0x44] ^ 0xff if self.ko_mode else self.sim.sfr[0x46]

			try:
				for val in self.keys_pressed:
					if val == None: continue
					if ko & (1 << val[1]): ki &= ~(1 << val[0])
			except RuntimeError: pass

		self.sim.sfr[0x40] = ki

		if not config.real_hardware:
			if self.read_emu_kb(0) in (2, 8) and [self.read_emu_kb(i) for i in (1, 2)] != [1<<2, 1<<4]: self.write_emu_kb(0, 0)

	def sbycon(self):
		if self.sim.sfr[9] & (1 << 1):
			if all(self.stop_accept[:]):
				self.stop_mode = True
				self.stop_accept[:] = (ctypes.c_bool * 2)()[:]
				self.sim.sfr[8] = 0
				self.sim.sfr[0x22] = 0
				self.sim.sfr[0x23] = 0
			else: self.sim.sfr[9] &= ~(1 << 1)

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

	@staticmethod
	def find_bit(num): return (num & -num).bit_length() - 1

	def check_ints(self):
		for i in range(0x14, 0x16) if config.hardware_id != 6 else range(0x18, 0x20):
			if self.sim.sfr[i] == 0: continue
			self.raise_int(i, self.find_bit(self.sim.sfr[i]))

	def raise_int(self, irq, bit):
		intdata = self.int_table[(irq, bit)]
		if intdata[1] is not None and intdata[2] is not None: cond = self.sim.sfr[intdata[1]] & (1 << intdata[2])
		else: cond = True

		elevel = 2 if intdata[3] == 'WDTINT' else 1
		mie = elevel & (1 << 3) if elevel == 1 else 1
		if cond and (self.sim.core.regs.psw & 3 >= elevel or elevel == 2) and mie:
			#logging.info(f'{intdata[3]} interrupt raised {"@ "+self.get_addr_label(self.sim.core.regs.csr, self.sim.core.regs.pc) if intdata[3] != "WDTINT" else ""}')
			self.stop_mode = False
			self.sim.sfr[irq] &= ~(1 << bit)
			self.sim.core.regs.elr[elevel-1] = self.sim.core.regs.pc
			self.sim.core.regs.ecsr[elevel-1] = self.sim.core.regs.csr
			self.sim.core.regs.epsw[elevel-1] = self.sim.core.regs.psw
			self.sim.core.regs.psw &= 0b11111100 if elevel == 2 else 0b11110100
			self.sim.core.regs.psw |= elevel
			self.sim.core.regs.csr = 0
			self.sim.core.regs.pc = (self.sim.code_mem[intdata[0]+1] << 8) + self.sim.code_mem[intdata[0]]

			self.int_timer = 2

	@staticmethod
	def read_word(arr, index): return arr[index + 1] << 8 | arr[index]

	@staticmethod
	def write_word(arr, index, val): arr[index + 1] = val >> 8; arr[index] = val & 0xff

	def core_step(self):
		prev_csr_pc = f'{self.sim.core.regs.csr:X}:{self.sim.core.regs.pc:04X}H'
		if not self.stop_mode:
			wdp = self.sim.sfr[0xe] & 1

			try: self.sim.core_step()
			except Exception as e: logging.error(e)

			if self.prev_csr_pc is not None: self.prev_prev_csr_pc = self.prev_csr_pc
			if prev_csr_pc != self.prev_csr_pc: self.prev_csr_pc = prev_csr_pc

			if config.hardware_id == 6:
				last_swi = self.sim.core.last_swi
				if last_swi < 0x40:
					if last_swi == 1:
						self.scr[3][0] = (self.sim.core.regs.gp[1] << 8) + self.sim.core.regs.gp[0]
						self.sim.core.regs.gp[0] = self.sim.core.regs.gp[1] = 0
						self.screen_changed = True
					elif last_swi == 2:
						self.sim.core.regs.gp[1] = 0
						self.sim.core.regs.gp[0] = self.curr_key
						#if self.curr_key != 0: self.hit_brkpoint()
					elif last_swi == 4:
						self.scr[3][1] = (self.sim.core.regs.gp[1] << 8) + self.sim.core.regs.gp[0]
						self.sim.core.regs.gp[0] = self.sim.core.regs.gp[1] = 0
						self.screen_changed = True

			if self.enable_ips:
				if self.ips_ctr % 1000 == 0:
					cur = time.time()
					try: self.ips = 1000 / (cur - self.ips_start)
					except ZeroDivisionError: self.ips = None
					self.ips_start = cur
				self.ips_ctr += 1

			if (self.sim.core.regs.csr << 16) + self.sim.core.regs.pc == self.breakpoint and not self.single_step: self.hit_brkpoint()
			if self.write_brkpoint in range(self.sim.core.last_write, self.sim.core.last_write + self.sim.core.last_write_size): self.hit_brkpoint()
			
		if config.hardware_id != 6:
			self.keyboard()
			if self.stop_mode: self.timer()
			else: self.sbycon()
		if (config.hardware_id != 2 or (config.hardware_id == 2 and self.is_5800p)) and self.int_timer == 0: self.check_ints()
		if self.int_timer != 0: self.int_timer -= 1

		if config.hardware_id == 6: self.wdt.dec_wdt()

	def hit_brkpoint(self):
		self.set_single_step(True)
		self.reg_display.open()
		self.keys_pressed.clear()

	def save_flash(self):
		f = tk.filedialog.asksaveasfile(mode = 'wb', initialfile = 'flash.bin', defaultextension = '.bin', filetypes = [('All Files', '*.*'), ('Binary Files', '*.bin')])
		if f is not None: f.write(bytes(self.sim.flash_mem))

	def save_display(self, clipboard = True):
		if clipboard:
			temp = io.BytesIO()
			if os.name == 'nt':
				pygame.image.save(self.display, temp, 'BMP')
				win32clipboard.OpenClipboard()
				win32clipboard.EmptyClipboard()
				win32clipboard.SetClipboardData(win32clipboard.CF_DIB, temp.getvalue()[14:])
				win32clipboard.CloseClipboard()
			else:
				pygame.image.save(self.display, temp, 'PNG')
				klembord.init()
				klembord.set({'image/png': temp.getvalue()})
			temp.close()
		else:
			f = tk.filedialog.asksaveasfilename(initialfile = 'image.png', defaultextension = '.png', filetypes = [('All Files', '*.*'), ('Supported Image Files', '*.bmp *.tga *.png *.jpg *.jpeg')])
			if f is not None: pygame.image.save(self.display, f)

	def core_step_loop(self):
		while not self.single_step: self.core_step()

	def decode_instruction(self):
		self.disas.input_file = b''
		for i in range(3): self.disas.input_file += self.read_cmem((self.sim.core.regs.pc + i*2) & 0xfffe, self.sim.core.regs.csr).to_bytes(2, 'little')
		self.disas.addr = 0
		ins_str, ins_len, dsr_prefix, _ = self.disas.decode_ins(True)
		if dsr_prefix:
			self.disas.last_dsr_prefix = ins_str
			last_dsr_prefix_str = f'DW {int.from_bytes(self.disas.input_file[:2], "little"):04X}'
			self.disas.addr += 2
			ins_str, inslen, _, used_dsr_prefix = self.disas.decode_ins(True)
			ins_len + inslen
			if used_dsr_prefix: return ins_str, ins_len
			else: return last_dsr_prefix_str, 2
		return ins_str, ins_len

	@staticmethod
	def nearest_num(l, n): return max([i for i in l if i <= n], default = None)

	def get_instruction_label(self, addr):
		near = self.nearest_num(self.labels.keys(), addr)
		if near is None: return
		label = self.labels[near]
		offset = addr - near
		offset_str = hex(offset) if offset > 9 else str(offset)
		return f'{label[0] if label[1] else self.labels[label[2]][0]+label[0]}{"+"+offset_str if offset != 0 else ""}'

	def get_addr_label(self, csr, pc):
		label = self.get_instruction_label((csr << 16) + pc)
		return f'{csr:X}:{pc:04X}H{" ("+label+")" if label is not None else ""}'

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

			screen_data_raw = [[3 if scr_bytes[i*8+j] & (1 << k) else 0 for j in range(8) for k in range(7, -1, -1)] for i in range(3)]

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

			screen_data = [[3 if scr_bytes[1+i][j] & (1 << k) else 0 for j in range(0x18) for k in range(7, -1, -1)] for i in range(63)]

		elif config.hardware_id == 6:
			screen_data_status_bar = [sbar & (1 << i) for i in range(19)]
			screen_data = [[3 if scr_bytes[1+i][j] & (1 << k) else 0 for j in range(7, -1, -1) for k in range(7, -1, -1)] for i in range(192)]

		else:
			is_5800p = config.is_5800p if hasattr(config, 'is_5800p') else False
			if config.hardware_id == 2 and is_5800p:
				screen_data_status_bar = [
				sbar[0]   & (1 << 4),  # [S]
				sbar[0]   & (1 << 2),  # [A]
				sbar[1]   & (1 << 4),  # M
				sbar[1]   & (1 << 1),  # STO
				sbar[2]   & (1 << 6),  # RCL
				sbar[3]   & (1 << 6),  # SD
				sbar[4]   & (1 << 7),  # REG
				sbar[5]   & (1 << 6),  # FMLA
				sbar[5]   & (1 << 4),  # PRGM
				sbar[5]   & (1 << 1),  # END
				sbar[7]   & (1 << 5),  # [D]
				sbar[7]   & (1 << 1),  # [R]
				sbar[8]   & (1 << 4),  # [G]
				sbar[8]   & (1 << 0),  # FIX
				sbar[9]   & (1 << 5),  # SCI
				sbar[0xa] & (1 << 6),  # Math
				sbar[0xa] & (1 << 3),  # ▼
				sbar[0xb] & (1 << 7),  # ▲
				sbar[0xb] & (1 << 4),  # [Disp]
				]
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
			
			screen_data = [[3 if scr_bytes[1+i][j] & (1 << k) else 0 for j in range(0xc) for k in range(7, -1, -1)] for i in range(31)]

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
		self.sim.u8_reset()
		if config.hardware_id == 6:
			self.scr[3][0] = self.scr[3][1] = None
			for i in range(0x1000): self.sim.sfr[i] = 0xff
			self.sim.sfr[2] = 0x13
			self.sim.sfr[3] = 3
			self.sim.sfr[4] = 2
			self.sim.sfr[5] = 0x40
			self.sim.sfr[0xa] = 3
			self.sim.sfr[0xe] = 0
			self.sim.sfr[0xf] = 0x82
			self.sim.sfr[0x900] = 6
			self.sim.sfr[1] = 0x30
			for i in range(0x10, 0x4f): self.sim.sfr[i] = 0

		self.stop_mode = False
		self.prev_csr_pc = None
		self.reg_display.print_regs()
		self.data_mem.get_mem()

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

		self.screen.fill((214, 227, 214) if config.hardware_id != 6 else (255, 255, 255))
		if self.interface is not None: self.screen.blit(self.interface, self.interface_rect)
		if config.hardware_id == 6 and self.curr_key != 0:
			pygame.draw.rect(self.screen, (255, 255, 255), config.keymap[self.curr_key][0])
			self.screen.blit(self.interface, config.keymap[self.curr_key][0][:2], config.keymap[self.curr_key][0], pygame.BLEND_RGB_SUB)
		elif len(self.keys_pressed) > 0:
			for key in self.keys_pressed:
				pygame.draw.rect(self.screen, (255, 255, 255), config.keymap[key][0])
				self.screen.blit(self.interface, config.keymap[key][0][:2], config.keymap[key][0], pygame.BLEND_RGB_SUB)

		disp_lcd = self.disp_lcd.get()

		if (config.hardware_id == 6 and (self.screen_changed or self.always_update)) or config.hardware_id != 6:
			self.screen_changed = False
			self.display.fill((214, 227, 214) if config.hardware_id != 6 else (255, 255, 255))

			if config.hardware_id == 0: scr_bytes = self.read_dmem_bytes(0xf800, 0x20)
			elif (disp_lcd != 0 and self.scr[3][disp_lcd-1] is not None) or disp_lcd == 0: scr_bytes = [self.read_dmem_bytes(self.scr[3][disp_lcd-1] + i*self.scr[1] if disp_lcd else 0xf800 + i*self.scr[0], self.scr[1]) for i in range(self.scr[2])]
			if config.hardware_id == 6 and self.scr[3][0] is not None: scr_bytes = [0 if self.scr[3][1] is None else int.from_bytes(self.read_dmem_bytes(self.scr[3][1], 3), 'little')] + scr_bytes
			if config.hardware_id == 5:
				if disp_lcd: scr_bytes_hi = tuple(self.read_dmem_bytes(self.scr[3][disp_lcd-1] + self.scr[1]*self.scr[2] + i*self.scr[1], self.scr[1]) for i in range(self.scr[2]))
				else: scr_bytes_hi = tuple(self.read_dmem_bytes(0x9000 + i*self.scr[0], self.scr[1], 8) for i in range(self.scr[2]))
				screen_data_status_bar, screen_data = self.get_scr_data_cwii(self.scr[3][disp_lcd-1] if disp_lcd else 0xf800, tuple(scr_bytes), scr_bytes_hi)
			elif (disp_lcd != 0 and self.scr[3][disp_lcd-1] is not None) or disp_lcd == 0: screen_data_status_bar, screen_data = self.get_scr_data(*scr_bytes)
			
			scr_range = self.sim.sfr[0x30] & 7
			scr_mode = self.sim.sfr[0x31] & 7

			if (not disp_lcd and scr_mode in (5, 6)) or disp_lcd:
				if self.status_bar is not None and hasattr(config, 'status_bar_crops') and 'screen_data_status_bar' in locals():
					for i in range(len(screen_data_status_bar)):
						try: crop = config.status_bar_crops[i]
						except IndexError: continue
						if screen_data_status_bar[i]: self.display.blit(self.status_bar, crop[:2], crop)
				elif config.hardware_id != 6:
					sbar = [scr_bytes[0][j] & (1 << k) for j in range(self.scr[1]) for k in range(7, -1, -1)]
					for x in range(self.scr[4]):
						if sbar[x]: pygame.draw.rect(self.display, (0, 0, 0), (x*config.pix, self.sbar_hi - self.pix_hi, config.pix, self.pix_hi))
		
			if config.hardware_id == 0:
				offset = 0
				offset_h = 5
				small_offset = 0
				for i in range(14):
					n = lambda j: config.pix*(5*i+offset+j) if i < 11 else config.pix*(11*5+offset) + config.pix_s*(small_offset+5*(i-11)+j)
					pix = config.pix if i < 11 else config.pix_s
					if i == 0:
						if screen_data[-2]: pygame.draw.rect(self.display, self.pix_color, (n(1), offset_h + self.sbar_hi + pix*5,  pix*2, pix))
					elif i == 11:
						if screen_data[-1]: pygame.draw.rect(self.display, self.pix_color, (n(1), offset_h + self.sbar_hi + pix*5,  pix*2, pix))
					else:
						data = screen_data[i-(1 if i < 12 else 2)]
						if data[0]: pygame.draw.rect(self.display, self.pix_color, (n(1), offset_h + self.sbar_hi,                 pix*2, pix))
						if data[1]: pygame.draw.rect(self.display, self.pix_color, (n(0), offset_h + self.sbar_hi + pix,    pix,   pix*4))
						if data[2]: pygame.draw.rect(self.display, self.pix_color, (n(3), offset_h + self.sbar_hi + pix,    pix,   pix*4))
						if data[3]: pygame.draw.rect(self.display, self.pix_color, (n(1), offset_h + self.sbar_hi + pix*5,  pix*2, pix))
						if data[4]: pygame.draw.rect(self.display, self.pix_color, (n(0), offset_h + self.sbar_hi + pix*6,  pix,   pix*4))
						if data[5]: pygame.draw.rect(self.display, self.pix_color, (n(3), offset_h + self.sbar_hi + pix*6,  pix,   pix*4))
						if data[6]: pygame.draw.rect(self.display, self.pix_color, (n(1), offset_h + self.sbar_hi + pix*10, pix*2, pix))
						if data[7] and i < 11: pygame.draw.circle(self.screen, self.pix_color, (n(4.5), offset_h + self.sbar_hi + config.pix*11), config.pix * (3/4))
			elif config.hardware_id == 6:
				if self.scr[3][0] is not None:
					for y in range(self.scr[4]):
						for x in range(self.scr[2]):
							if screen_data[x][y]: pygame.draw.rect(self.display, (0, 0, 0), (x*config.pix, self.sbar_hi + (64-y)*config.pix, config.pix, config.pix))
			else:
				if (not disp_lcd and scr_mode == 5) or disp_lcd:
					for y in range(self.scr_ranges[scr_range] if not disp_lcd and config.hardware_id in (2, 3) else self.scr[2] - 1):
						for x in range(self.scr[4]):
							if screen_data[y][x]: pygame.draw.rect(self.display, self.cwii_screen_colors[screen_data[y][x]], (x*config.pix, self.sbar_hi + y*self.pix_hi, config.pix, self.pix_hi))

		if config.hardware_id == 6: self.draw_text(f'{"No screen data" if self.scr[3][0] is None else "Screen data @ "+format(self.scr[3][0], "04X")+"H"} - {"No status bar" if self.scr[3][1] is None else "Status bar @ "+format(self.scr[3][1], "04X")+"H"}', 22, config.width // 2, self.text_y, config.pygame_color, anchor = 'midtop')
		elif self.num_buffers > 0: self.draw_text(f'Displaying {"buffer "+str(disp_lcd if self.num_buffers > 1 else "")+" @ "+format(self.scr[3][disp_lcd-1], "04X")+"H" if disp_lcd else "LCD"}', 22, config.width // 2, self.text_y, config.pygame_color, anchor = 'midtop')
		if self.single_step: self.step = False
		elif self.enable_fps: self.draw_text(f'{self.clock.get_fps():.1f} FPS', 22, config.width // 2, self.text_y + 22 if self.num_buffers > 0 else self.text_y, config.pygame_color, anchor = 'midtop')

		self.screen.blit(self.display, (config.screen_tl_w, config.screen_tl_h))
		pygame.display.update()
		self.root.update()
		self.root.after(0, self.pygame_loop)

if __name__ == '__main__':
	spec = importlib.util.spec_from_file_location('config', sys.argv[1] if len(sys.argv) > 1 else 'config.py')
	if spec is None:
		try: config = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'config')
		except ImportError as e:
			logging.error(f'Cannot import config script as module: {str(e)}')
			sys.exit()
	else:
		config = importlib.util.module_from_spec(spec)
		sys.modules['config'] = config
		spec.loader.exec_module(config)

	if hasattr(config, 'dt_format'): logging.basicConfig(datefmt = config.dt_format, format = '[%(asctime)s] %(levelname)s: %(message)s', level = level, force = True)

	# Load the sim library
	sim_lib = ctypes.CDLL(os.path.abspath(config.shared_lib))

	sim_lib.u8_step.argtypes = [ctypes.POINTER(u8_core_t)]

	sim_lib.core_step.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_bool, ctypes.c_int, ctypes.c_bool]

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

	sim = Sim(no_klembord, bcd)
	sim.run()
