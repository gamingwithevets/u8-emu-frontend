import io
import os; os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = ''
try: import PIL.Image
except ImportError:
	print('Please install pillow!')
	sys.exit()
import sys
import math
import time
import ctypes
try: import pygame
except ImportError:
	print('Please install pygame!')
	sys.exit()
import logging
import cProfile
import functools
import importlib
import importlib.util
import threading
import traceback
import webbrowser
no_clipboard = False
try:
	if os.name == 'nt': import win32clipboard
	else: import klembord
	no_clipboard = True
except ImportError: no_clipboard = True
try: import tkinter as tk
except ImportError:
	print('Please install tkinter!')
	sys.exit()
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

import peripheral
import gui

profile_mode = False

if sys.version_info < (3, 8, 0):
	print(f'This program requires at least Python 3.8.0. (You are running Python {platform.python_version()})')
	sys.exit()

if pygame.version.vernum < (2, 2, 0):
	print(f'This program requires at least Pygame 2.2.0. (You are running Pygame {pygame.version.ver})')
	sys.exit()

level = logging.INFO
logging.basicConfig(datefmt = '%d/%m/%Y %H:%M:%S', format = '[%(asctime)s] %(levelname)s: %(message)s', level = level)

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

# from Delta / @frsr (edited to be compatible with pitust™ quality code)
class u8_core_t(ctypes.Structure):	# Forward definition so pointers can be used
	pass

class u8_regs_t(ctypes.Structure):
	_fields_ = [
		('gp',		ctypes.c_uint8 * 16),
		('pc',		ctypes.c_uint16),
		('csr',		ctypes.c_uint8),
		('lcsr',	ctypes.c_uint8),
		('ecsr',	ctypes.c_uint8 * 3),
		('lr',		ctypes.c_uint16),
		('elr',		ctypes.c_uint16 * 3),
		('psw',		ctypes.c_uint8),
		('epsw',	ctypes.c_uint8 * 3),
		('sp',		ctypes.c_uint16),
		('ea',		ctypes.c_uint16),
		('dsr',		ctypes.c_uint8)
	]

class _acc_arr(ctypes.Structure):
	_fields_ = [
		('array',	ctypes.POINTER(ctypes.c_uint8)),
		('dirty',	ctypes.c_uint64),
	]

class _acc_func(ctypes.Structure):
	_fields_ = [
		('read',	ctypes.CFUNCTYPE(ctypes.c_uint8, ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16)),
		('write',	ctypes.CFUNCTYPE(None, ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8))
	]

class _acc_union(ctypes.Union):
	_anonymous_ = ['_acc_arr', '_acc_func']
	_fields_ = [
		('_acc_arr',	_acc_arr),
		('_acc_func',	_acc_func)
	]

class u8_mem_reg_t(ctypes.Structure):
	_anonymous_ = ['_acc_union']
	_fields_ = [
		('type',		ctypes.c_uint),
		('rw',			ctypes.c_bool),
		('addr_l',		ctypes.c_uint32),
		('addr_h',		ctypes.c_uint32),

		('acc',			ctypes.c_uint),
		('_acc_union',	_acc_union)
	]

class u8_mem_t(ctypes.Structure):
	_fields_ = [
		('num_regions',	ctypes.c_int),
		('regions',		ctypes.POINTER(u8_mem_reg_t))
	]

u8_core_t._fields_ = [
		('regs',			u8_regs_t),
		('cur_dsr',			ctypes.c_uint8),
		('last_swi',		ctypes.c_uint8),
		('last_read',		ctypes.c_uint32),
		('last_read_size',	ctypes.c_uint8),
		('last_write',		ctypes.c_uint32),
		('last_write_size',	ctypes.c_uint8),
		('u16_mode',		ctypes.c_bool),
		('small_mm',		ctypes.c_bool),
		('mem',				u8_mem_t),
		('codemem',			u8_mem_t),
	]

class u8_mem_type_e(IntEnum):	
	U8_REGION_BOTH = 0
	U8_REGION_DATA = 1
	U8_REGION_CODE = 2

class u8_mem_acc_e(IntEnum):
	U8_MACC_ARR  = 0
	U8_MACC_FUNC = 1

class c_config(ctypes.Structure):
	_fields_ = [
		('hwid',		ctypes.c_int),
		('real_hw',		ctypes.c_bool),
		('ko_mode',		ctypes.c_bool),
		('sample',		ctypes.c_bool),
		('is_5800p',	ctypes.c_bool),
		('pd_value',	ctypes.c_uint8),
		('rom',			ctypes.POINTER(ctypes.c_uint8)),
		('flash',		ctypes.POINTER(ctypes.c_uint8)),
		('ram',			ctypes.POINTER(ctypes.c_uint8)),
		('sfr',			ctypes.POINTER(ctypes.c_uint8)),
		('emu_seg',		ctypes.POINTER(ctypes.c_uint8)),
		('sfr_write',	(ctypes.CFUNCTYPE(ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8)) * 0x1000),
		('flash_mode',	ctypes.c_int),
	]

class Core:
	def __init__(self, sim, rom, flash):
		self.sim = sim

		pd_value = config.pd_value if hasattr(config, 'pd_value') else 0
		self.c_config = c_config(config.hardware_id, config.real_hardware, self.sim.ko_mode, self.sim.sample, self.sim.is_5800p)
		self.c_config.pd_value = pd_value

		self.core = u8_core_t()

		# Initialise memory
		if config.hardware_id == 5 and config.real_hardware:
			self.rom_length = 0xfffff
			self.code_mem = (ctypes.c_uint8 * 0x100000)(*rom, *rom)
		else:
			self.rom_length = len(rom)
			self.code_mem = (ctypes.c_uint8 * (0x80000 if config.hardware_id == 2 and self.sim.is_5800p else 0x100000))(*rom)
			if config.hardware_id == 2 and self.sim.is_5800p:
				self.flash_length = len(flash)
				self.flash_mem = (ctypes.c_uint8 * 0x80000)(*flash)
			else: self.flash_length = 0

		data_size = {
		0: (0xe000, 0x1000),
		3: (0x8000, 0xe00 if config.real_hardware else 0x7000),
		4: (0xd000, 0x2000),
		5: (0x9000, 0x6000),
		6: (0xb000, 0x4000),
		}

		ramstart, ramsize = data_size[config.hardware_id if config.hardware_id in data_size else 3]
		self.ramstart = ramstart
		self.ramsize = ramsize

		self.sfr_write_ft = ctypes.CFUNCTYPE(ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8)
		self.sfr_default_write_f = self.sfr_write_ft(self.sfr_default_write)

		self.setup_mcu(ramstart, ramsize)

	def setup_mcu(self, ramstart, ramsize):
		sim_lib.setup_mcu(ctypes.pointer(self.c_config), ctypes.pointer(self.core), self.code_mem, self.flash_mem if config.hardware_id == 2 and self.sim.is_5800p else None, ramstart, ramsize)

		if config.hardware_id == 2 and self.sim.is_5800p: self.c_config.sfr[0x46] = 4
		self.register_sfr(0, 1, self.write_dsr)

		if config.hardware_id in (4, 5):
			self.register_sfr(0xd0, 1)
			self.register_sfr(0xd1, 1, lambda x, y: 6 if self.c_config.sfr[0xd0] == 3 and self.c_config.sfr[0xd2] == 0 and y == 5 else y)
			self.register_sfr(0xd2, 1)

		if config.hardware_id == 5:
			self.bcd = peripheral.BCD(self.sim)
			self.register_sfr(0x400, 1, self.bcd.tick)  # BCDCMD
			self.register_sfr(0x402, 1, self.bcd.tick)  # BCDCON
			self.c_config.sfr[0x402] = 6
			self.register_sfr(0x404, 1, self.bcd.tick)  # BCDMCN
			self.register_sfr(0x405, 1, self.bcd.tick)  # BCDMCR
			self.register_sfr(0x410, 1)                 # BCDFLG
			# F414H: BCDLLZ, F415H: BCDMLZ (both read-only)
			for i in range(4): self.register_sfr(0x480 + i*0x20, 12)  # BCDREG000 - BCDREG311
	
	def u8_reset(self): sim_lib.u8_reset(ctypes.pointer(self.core))

	def read_reg_er(self, n): return sim_lib.read_reg_er(ctypes.pointer(self.core), n)

	# Memory Access
	def read_mem_data(self, dsr, offset, size): return sim_lib.read_mem_data(ctypes.pointer(self.core), dsr, offset, size)
	
	def write_mem_data(self, dsr, offset, size, value): return sim_lib.write_mem_data(ctypes.pointer(self.core), dsr, offset, size, value)
	
	def register_sfr(self, addr, length, handler = None):
		for i in range(addr, addr+length): self.c_config.sfr_write[i] = self.sfr_default_write_f if handler is None else self.sfr_write_ft(handler)

	def sfr_default_write(self, addr, value): return value

	def write_dsr(self, addr, value):
		self.core.regs.dsr = value
		return value

	def write_sfr(self, addr, value):
		if addr >= 0x1000:
			label = self.sim.get_instruction_label((self.core.regs.csr << 16) + self.core.regs.pc)
			logging.warning(f'Overflown write to {(0xf000 + addr) & 0xffff:04X}H @ {self.sim.get_addr_label(self.core.regs.csr, self.core.regs.pc-2)}')
			return self.read_mem_data(seg, (0xf000 + addr) & 0xffff, 1)

		try:
			if config.hardware_id == 5:
				if config.real_hardware:
					if addr >= 0x800:
						y, x = self.get_idx(addr - 0x800)
						if self.c_config.sfr[0x37] & 4: self.sim.cwii_screen_hi[y][x] = value
						else: self.sim.cwii_screen_lo[y][x] = value
						return value
					elif addr == 0xd1: return 
				if addr == 0x312:
					if self.sim.shutdown_accept:
						if value == 0x3c:
							self.c_config.sfr[0x31] = 3
							self.sim.shutdown = True
						elif value != 0x5a: self.sim.shutdown_accept = False
					elif value == 0x5a: self.sim.shutdown_accept = True
				elif addr in (0x400, 0x402, 0x404, 0x405): self.sim.bcd.tick(addr)
				else: return value
			elif config.hardware_id == 6:
				if addr == 0xe: return value == 0x5a
				elif addr == 0x900: return 0x34
				elif addr == 0x901: return int(not value)
				else: return value
			elif addr == 0x46 and config.hardware_id == 2 and self.sim.is_5800p: return 4
			else: return value
		except Exception as e:
			logging.error(f'{type(e).__name__} writing to {0xf000+addr:04X}H: {e}')
			return 0

	def battery(self, core, seg, addr): return 0xff

	@staticmethod
	@functools.lru_cache
	def get_idx(x): return x // 32, x % 32

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

class Sim:
	def __init__(self, no_clipboard, bcd):
		self.copyclip = no_clipboard

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
		self.is_5800p = config.is_5800p if hasattr(config, 'is_5800p') else False
		self.sample = config.sample if hasattr(config, 'sample') else False
		self.buffers_no_2bpp = config.buffers_no_2bpp if hasattr(config, 'buffers_no_2bpp') else False

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
			for k, v in props.items(): logging.info(f'{k}: {v}')
		else:
			rom = open(config.rom_file, 'rb').read()
			if len(rom) % 2 != 0:
				logging.error('ROM size cannot be odd')
				sys.exit()

		self.pix_hi = config.pix_hi if hasattr(config, 'pix_hi') else config.pix

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
		self.init_brk = rom[4] | rom[5] << 8

		self.keys_pressed = set()
		self.keys = []
		if hasattr(config, 'keymap'):
			for key in [i[1:] for i in config.keymap.values()]: self.keys.extend(key)

		# windows
		self.jump = gui.Jump(self)
		self.brkpoint = gui.Brkpoint(self)
		self.write = gui.Write(self)
		self.data_mem = gui.DataMem(self, config.data_mem_width, config.data_mem_height, config.data_mem_font)
		self.gp_modify = gui.GPModify(self)
		self.reg_display = gui.RegDisplay(self, config.console_fg, config.console_bg, config.console_font)
		self.call_display = gui.CallStackDisplay(self, config.console_fg, config.console_bg, config.console_font)
		self.debugger = gui.Debugger(self)

		self.screen_stuff = {
	   # hwid: (alloc, used, rows,buffers,          columns)
			0: [0x8,   0x8,  3,   [],               64],
			2: [0x10,  0xc,  32,  [0x80e0 if self.is_5800p else 0x8600], 96],
			3: [0x10,  0xc,  32,  [0x87d0],         96],
			4: [0x20,  0x18, 64,  [0xddd4, 0xe3d4], 192],
			5: [0x20,  0x18, 64,  [0xca54, 0xd654], 192],
			6: [0x8,   0x8,  192, [None, None],     64],
		}

		if config.hardware_id in self.screen_stuff: self.scr = self.screen_stuff[config.hardware_id]
		else: self.scr = self.screen_stuff[3]
		if config.hardware_id != 6 and hasattr(config, 'custom_buffers') and type(config.custom_buffers) == list: self.scr[3] = config.custom_buffers

		# actual peripherals
		self.disp = peripheral.Screen(self, self.scr)
		self.wdt = peripheral.WDT(self)
		self.standby = peripheral.Standby(self)
		self.timer = peripheral.Timer(self)
		self.kb = peripheral.Keyboard(self)
		self.disas = disas_main.Disasm()

		if hasattr(config, 'labels') and config.labels:
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
							if config.real_hardware:
								self.sim.c_config.sfr[0x14] = 2
								if self.sim.c_config.sfr[0x42] & (1 << k[0]): self.standby.stop_mode = False
							else:
								self.standby.stop_mode = False
								self.write_emu_kb(1, 1 << k[0])
								self.write_emu_kb(2, 1 << k[1])
					elif len(self.keys_pressed) == 0: self.curr_key = k
					break

		def display_key(event):
			for k, v in config.keymap.items():
				p = v[0]
				if event.x in range(p[0], p[0]+p[2]) and event.y in range(p[1], p[1]+p[3]):
					nl = '\n'
					keys = [repr(_) if self.use_char else _ for _ in v[1:] if _]
					kio_str = 'Core reset key.' if k is None else f'KI: {k[0]}\nKO: {k[1]}' if config.hardware_id != 6 else f'Key ID: 0x{k:02x}'
					tk.messagebox.showinfo('Key information', f'{kio_str}\n\nBox: {p}\n{"Char" if self.use_char else "Keysym"}(s):\n{nl.join(keys) if len(keys) > 0 else "None"}')
					break

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
			embed_pygame.bind('<ButtonPress-2>', display_key)
			embed_pygame.bind('<ButtonRelease-1>', release_cb)

		if os.name != 'nt': self.root.update()

		os.environ['SDL_WINDOWID'] = str(embed_pygame.winfo_id())
		os.environ['SDL_VIDEODRIVER'] = 'windib' if os.name == 'nt' else 'x11'
		pygame.init()
		self.screen = pygame.display.set_mode()

		try:
			self.interface = pygame.transform.smoothscale(pygame.image.load(config.interface_path).convert(), (config.width, config.height))
			self.interface_rect = self.interface.get_rect()
		except IOError as e:
			logging.warning(e)
			self.interface = None
		except AttributeError: self.interface = None

		try:
			self.status_bar = pygame.transform.smoothscale(pygame.image.load(config.status_bar_path).convert(), (config.s_width, config.s_height))
			self.status_bar_rect = self.status_bar.get_rect()
		except IOError as e:
			logging.warning(e)
			self.status_bar = None
		except AttributeError: self.status_bar = None
		
		if hasattr(config, 's_height'): self.sbar_hi = config.s_height
		else: self.sbar_hi = 0

		self.disp_lcd = tk.IntVar(value = 0)
		self.init_tk_var('enable_ips', False)
		self.init_tk_var('enable_fps', True)
		self.init_tk_var('always_update', False)
		self.init_tk_var('force_display', False)
		self.init_tk_var('factory_test', False)

		self.rc_menu = tk.Menu(self.root, tearoff = 0)
		self.rc_menu.add_command(label = 'Step', accelerator = '\\', command = self.set_step)
		self.rc_menu.add_command(label = 'Enable single-step mode', accelerator = 'S', command = lambda: self.set_single_step(True))
		self.rc_menu.add_command(label = 'Resume execution (unpause)', accelerator = 'P', command = lambda: self.set_single_step(False))
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Jump to...', accelerator = 'J', command = self.jump.deiconify)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Manage breakpoints', accelerator = 'B', command = self.brkpoint.deiconify)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Show data memory', accelerator = 'M', command = self.data_mem.open)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Register display', accelerator = 'R', command = self.reg_display.open)
		self.rc_menu.add_command(label = 'Call stack display', command = self.call_display.open)
		self.rc_menu.add_command(label = 'Debugger (beta)', command = self.debugger.open)
		self.rc_menu.add_separator()
		
		if config.hardware_id == 6: self.display = pygame.Surface((self.scr[2]*config.pix if self.status_bar is None else self.status_bar.get_width(), (self.scr[4])*self.pix_hi + self.sbar_hi))
		elif config.hardware_id == 0: self.display = pygame.Surface((self.scr[4]*config.pix if self.status_bar is None else self.status_bar.get_width(), 13*self.pix_hi + self.sbar_hi))
		else: self.display = pygame.Surface((self.scr[4]*config.pix, (self.scr[2] - 1)*self.pix_hi + self.sbar_hi))
		self.display.fill((255, 255, 255))

		if config.hardware_id == 6: self.int_table = {
			# (irqsfr,bit):(vtadr,ie_sfr,bit, name)
				(0x18, 0): (0x08, None, None, 'WDTINT'),     # Watchdog timer interrupt
			}
		elif config.hardware_id == 0: self.int_table = {
			# (irqsfr,bit):(vtadr,ie_sfr,bit, name)
				(0x14, 0): (0x08, 0x10, 0,    'XI0INT'),     # External interrupt 0
				(0x14, 1): (0x0a, 0x10, 1,    'TM0INT'),     # Timer 0 interrupt
				(0x14, 2): (0x0c, 0x10, 2,    'L256SINT'),
				(0x14, 3): (0x0e, 0x10, 3,    'L1024SINT'),
				(0x14, 4): (0x10, 0x10, 4,    'L4096SINT'),
				(0x14, 5): (0x12, 0x10, 5,    'L16384SINT'),
			}

		else: self.int_table = {
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
		save_display.add_command(label = f'Copy to clipboard{" ("+("pywin32" if os.name == "nt" else "klembord")+" package required)" if not self.copyclip else ""}', state = 'normal' if self.copyclip else 'disabled', command = self.save_display)
		save_display.add_command(label = 'Save as...', command = lambda: self.save_display(False))
		extra_funcs.add_cascade(label = 'Save display', menu = save_display)

		if config.hardware_id in (4, 5) and not config.real_hardware:
			qr_menu = tk.Menu(extra_funcs, tearoff = 0)
			qr_menu.add_command(label = 'Copy URL to clipboard', command = self.save_qr)
			qr_menu.add_command(label = 'Open URL', command = self.open_qr)
			extra_funcs.add_cascade(label = 'QR code export', menu = qr_menu)

		self.rc_menu.add_cascade(label = 'Extra functions', menu = extra_funcs)
		
		options = tk.Menu(self.rc_menu, tearoff = 0)
		options.add_checkbutton(label = 'IPS display (in register display)', variable = self.enable_ips_tk, command = self.set_enable_ips)
		options.add_checkbutton(label = 'FPS display', variable = self.enable_fps_tk, command = lambda: self.set_tk_var('enable_fps'))
		if config.hardware_id == 6: options.add_checkbutton(label = 'Always update display', variable = self.always_update_tk, command = lambda: self.set_tk_var('always_update'))
		if config.hardware_id in (2, 3, 4, 5): options.add_checkbutton(label = 'Force normal screen', variable = self.force_display_tk, command = lambda: self.set_tk_var('force_display'))
		if config.hardware_id in (3, 4, 5): options.add_checkbutton(label = 'Factory test mode', variable = self.factory_test_tk, command = lambda: self.set_tk_var('factory_test'))
		self.rc_menu.add_cascade(label = 'Options', menu = options)

		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'Reset core', command = self.reset_core)
		self.rc_menu.add_command(label = 'Quit', command = self.exit_sim)
		self.rc_menu.add_separator()
		self.rc_menu.add_command(label = 'u8-emu-frontend by Steveyboi / GamingWithEvets Inc.', command = self.open_gh)
		self.root.bind('<Button-3>', self.open_popup)
		self.root.bind('\\', lambda x: self.set_step())
		self.bind_(self.root, 's', lambda x: self.set_single_step(True))
		self.bind_(self.root, 'p', lambda x: self.set_single_step(False))
		self.bind_(self.root, 'j', lambda x: self.jump.deiconify())
		self.bind_(self.root, 'b', lambda x: self.brkpoint.deiconify())
		self.bind_(self.root, 'm', lambda x: self.data_mem.open())
		self.bind_(self.root, 'r', lambda x: self.reg_display.open())
		if config.hardware_id not in (0, 6): self.bind_(self.root, 'd', lambda x: self.disp_lcd.set((self.disp_lcd.get() + 1) % (self.num_buffers + 1)))

		if config.hardware_id == 5 and config.real_hardware:
			self.cwii_screen_hi = [bytearray(32) for _ in range(64)]
			self.cwii_screen_lo = [bytearray(32) for _ in range(64)]

		self.curr_buffer = -1

		self.single_step = False
		self.ok = True
		self.step = False
		self.brkpoints = {}
		self.stack = {}
		self.clock = pygame.time.Clock()

		self.prev_csr_pc = None
		self.prev_prev_csr_pc = None
		self.shutdown_accept = False
		self.shutdown = False

		self.int_timer = 0

		self.scr_ranges = (31, 15, 19, 23, 27, 27, 9, 9)

		self.call_trace = []

		# TI MathPrint only
		self.screen_changed = False
		self.curr_key = 0

		self.qr_active = False

	@staticmethod
	def open_gh(): webbrowser.open_new_tab('https://github.com/gamingwithevets/u8-emu-frontend')

	def get_var(self, var, typ): return typ.in_dll(sim_lib, var)

	def set_enable_ips(self):
		self.enable_ips = self.enable_ips_tk.get()
		if self.enable_ips:
			self.ips = 0
			self.ips_start = time.time()
			self.ips_ctr = 0

	def init_tk_var(self, var, val):
		setattr(self, var, val)
		setattr(self, var+'_tk', tk.BooleanVar(value = getattr(self, var)))
	def set_tk_var(self, var): setattr(self, var, getattr(self, var+'_tk').get())

	@functools.lru_cache
	def get_emu_kb_addr(self, idx):
		segment = 0
		if config.hardware_id == 0: addr = 0xe800 + idx
		elif config.hardware_id in (4, 5):
			segment = 4 if config.hardware_id == 4 else 8
			if config.hardware_id == 5 and self.sample:
				if idx == 0: addr = 0x8e07
				elif idx == 1: addr = 0x8e05
				elif idx == 2: addr = 0x8e08
			else: addr = 0x8e00 + idx
		else: addr = 0x8e00 + idx
		return segment, addr

	def read_emu_kb(self, idx): return self.sim.read_mem_data(*self.get_emu_kb_addr(idx), 1)

	def write_emu_kb(self, idx, val): self.sim.write_mem_data(*self.get_emu_kb_addr(idx), 1, val)

	def run(self):
		self.reset_core()
		self.set_single_step(self.single_step)
		self.pygame_loop()

		if os.name != 'nt': os.system('xset r off')
		if config.hardware_id == 6: self.wdt.start_wdt()
		self.root.mainloop()

	@staticmethod
	def bind_(self, char, func):
		self.bind(char.lower(), func)
		self.bind(char.upper(), func)

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
			if rang:
				if len(new_str) > len(hex(rang[-1])[2:]): return False
				elif len(new_str) == len(hex(rang[-1])[2:]) and int(new_str, 16) not in rang: return False

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


	def read_cmem(self, addr, segment = 0):
		if config.hardware_id == 2 and self.is_5800p and segment > 7:
			mem = self.sim.flash_mem
			segment -= 8
		else: mem = self.sim.code_mem
		return (mem[(segment << 16) + addr + 1] << 8) + mem[(segment << 16) + addr]

	def calc_checksum(self):
		csum = 0
		if config.hardware_id == 3:
			version = self.read_dmem_bytes(0xfff4, 6, 1).decode()
			rev = self.read_dmem_bytes(0xfffa, 2, 1).decode()
			csum1 = self.read_dmem(0xfffc, 2, 1)
			is_2nd = version.startswith('CY-8')
			for i in range(0x8000 if self.ko_mode else 0x10000): csum -= self.read_dmem(i, 1, 0 if self.ko_mode else 8)
			for i in range(0xff40 if is_2nd else 0xfffc): csum -= self.read_dmem(i, 1, 1)
			if is_2nd:
				for i in range(0xffd0, 0xffd0+0x2c): csum -= self.read_dmem(i, 1, 1)
			
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
			tk.messagebox.showinfo('ROM info only supports ES PLUS and ClassWiz.')
			return
		
		tk.messagebox.showinfo('ROM info', text)

	def set_step(self): self.step = True

	def set_single_step(self, val):
		self.single_step = val
		if val: self.update_displays()
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
		if not self.sim.c_config.sfr[0x46] and self.factory_test:
			self.sim.c_config.sfr[0x40] = 0b11100111
			return

		ki = 0xff
		if len(self.keys_pressed) > 0:
			ko = self.sim.c_config.sfr[0x44] ^ 0xff if self.ko_mode else self.sim.c_config.sfr[0x46]

			try:
				for val in self.keys_pressed:
					if val == None: continue
					if ko & (1 << val[1]): ki &= ~(1 << val[0])
			except RuntimeError: pass

		self.sim.c_config.sfr[0x40] = ki

	def check_stop_type(self):
		temp = self.read_emu_kb(0)
		if temp in (2, 8): self.write_emu_kb(0, int([self.read_emu_kb(i) for i in (1, 2)] == [1<<2, 1<<4]))
		elif temp in (5, 7) and not self.qr_active:
			self.qr_active = True
			tk.messagebox.showinfo('QR code', 'Detected emulator ROM QR code!\nGet the URL with right-click > Extra functions > QR code export > Copy URL to clipboard\n\nNote: due to the nature of the emulator, you might not see the QR code immediately')
		elif temp == 6: self.qr_active = False

	@staticmethod
	def find_bit(num): return (num & -num).bit_length() - 1

	def check_ints(self):
		rang = (0x14, 0x16) if config.hardware_id != 6 else (0x18, 0x20)
		if any(v != 0 for v in self.sim.c_config.sfr[rang[0]:rang[1]]):
			for i in range(*rang):
				if self.sim.c_config.sfr[i] == 0: continue
				self.raise_int(i, self.find_bit(self.sim.c_config.sfr[i]))

	def raise_int(self, irq, bit):
		intdata = self.int_table[(irq, bit)]
		if intdata[1] is not None and intdata[2] is not None: cond = self.sim.c_config.sfr[intdata[1]] & (1 << intdata[2])
		else: cond = True

		elevel = 2 if intdata[0] == 8 else 1
		mie = elevel & (1 << 3) if elevel == 1 else 1
		if cond and (self.sim.core.regs.psw & 3 >= elevel or elevel == 2) and mie:
			#logging.info(f'{intdata[3]} interrupt raised {"@ "+self.get_addr_label(self.sim.core.regs.csr, self.sim.core.regs.pc) if intdata[3] != "WDTINT" else ""}')
			self.standby.stop_mode = False
			self.sim.c_config.sfr[irq] &= ~(1 << bit)
			self.sim.core.regs.elr[elevel-1] = self.sim.core.regs.pc
			self.sim.core.regs.ecsr[elevel-1] = self.sim.core.regs.csr
			self.sim.core.regs.epsw[elevel-1] = self.sim.core.regs.psw
			self.sim.core.regs.psw &= 0b11111100 if elevel == 2 else 0b11110100
			self.sim.core.regs.psw |= elevel
			self.sim.core.regs.csr = 0
			self.sim.core.regs.pc = (self.sim.code_mem[intdata[0]+1] << 8) + self.sim.code_mem[intdata[0]]

			self.int_timer = 2

	def core_step(self):
		if self.shutdown: return
		prev_csr_pc = f'{self.sim.core.regs.csr:X}:{self.sim.core.regs.pc:04X}H'
		if not self.standby.stop_mode:
			prev_csrpc_int = (self.sim.core.regs.csr << 16) + self.sim.core.regs.pc

			ins_word = self.read_cmem(self.sim.core.regs.pc, self.sim.core.regs.csr)
			# BL Cadr
			if ins_word & 0xf0ff == 0xf001: self.call_trace.insert(0, [((ins_word >> 8 & 0xf) << 16) + self.read_cmem(self.sim.core.regs.pc+2, self.sim.core.regs.csr), (self.sim.core.regs.csr << 16) + ((self.sim.core.regs.pc + 4) & 0xfffe)])
			# BL ERn
			elif ins_word & 0xff0f == 0xf003: self.call_trace.insert(0, [(self.sim.core.regs.csr << 16) + self.sim.read_reg_er(ins_word >> 4 & 0xf), (self.sim.core.regs.csr << 16) + ((self.sim.core.regs.pc + 2) & 0xfffe)])
			# RT/POP PC
			elif ins_word == 0xfe1f or ins_word & 0xf2ff == 0xf28e:
				if len(self.call_trace) > 0: del self.call_trace[0]
			# BRK
			elif ins_word == 0xffff:
				if self.sim.core.regs.psw & 3 < 2:
					tk.messagebox.showwarning('Warning', 'BRK instruction hit!')
					self.hit_brkpoint()

			try: sim_lib.core_step(ctypes.pointer(self.sim.c_config), ctypes.pointer(self.sim.core))
			except Exception as e: logging.error(f'{e} @ {self.get_addr_label(self.sim.core.regs.csr, self.sim.core.regs.pc-2)}')

			if self.prev_csr_pc is not None: self.prev_prev_csr_pc = self.prev_csr_pc
			if prev_csr_pc != self.prev_csr_pc: self.prev_csr_pc = prev_csr_pc

			csrpc = (self.sim.core.regs.csr << 16) + self.sim.core.regs.pc
			a = lambda x: x < self.sim.rom_length or 0x80000 <= x < 0x80000+self.sim.flash_length
			if not a(csrpc) and a(prev_csrpc_int) and not self.single_step:
				tk.messagebox.showwarning('Warning', 'Jumped to unallocated code memory!')
				self.hit_brkpoint()

			if config.hardware_id == 6:
				last_swi = self.sim.core.last_swi
				if last_swi < 0x40:
					if last_swi == 1:
						self.scr[3][0] = self.sim.read_reg_er(0)
						self.sim.core.regs.gp[0] = self.sim.core.regs.gp[1] = 0
						self.screen_changed = True
					elif last_swi == 2:
						self.sim.core.regs.gp[1] = 0
						self.sim.core.regs.gp[0] = self.curr_key
						#if self.curr_key != 0: self.hit_brkpoint()
						self.curr_key = 0
					elif last_swi == 4:
						self.scr[3][1] = self.sim.read_reg_er(0)
						self.sim.core.regs.gp[0] = self.sim.core.regs.gp[1] = 0
						self.screen_changed = True

			if self.enable_ips:
				if self.ips_ctr % 1000 == 0:
					cur = time.time()
					try: self.ips = 1000 / (cur - self.ips_start)
					except ZeroDivisionError: self.ips = None
					self.ips_start = cur
				self.ips_ctr += 1

			if len(self.brkpoints) > 0:
				if self.find_brkpoint((self.sim.core.regs.csr << 16) + self.sim.core.regs.pc, 0): self.hit_brkpoint()
				if self.sim.core.last_read_size != 0 and any(self.find_brkpoint(i, 1) for i in range(self.sim.core.last_read, self.sim.core.last_read + self.sim.core.last_read_size)): self.hit_brkpoint()
				if self.sim.core.last_write_size != 0 and any(self.find_brkpoint(i, 2) for i in range(self.sim.core.last_write, self.sim.core.last_write + self.sim.core.last_write_size)): self.hit_brkpoint()
			
		if config.hardware_id != 6:
			if self.standby.stop_mode:
				self.timer.timer()
			self.keyboard()
			if not config.real_hardware and self.standby.stop_mode: self.check_stop_type()
		if (config.hardware_id != 2 or (config.hardware_id == 2 and self.is_5800p)) and self.int_timer == 0: self.check_ints()
		if self.int_timer != 0: self.int_timer -= 1

		if config.hardware_id == 6: self.wdt.dec_wdt()

	def find_brkpoint(self, addr, typ): return any([v['enabled'] and v['addr'] == addr and v['type'] == typ for v in self.brkpoints.values()])

	def hit_brkpoint(self):
		if not self.single_step:
			self.set_single_step(True)
			self.reg_display.open()
			self.call_display.open()
			self.debugger.open()
			self.keys_pressed.clear()

	def update_displays(self):
		self.screen_changed = True
		self.reg_display.print_regs()
		self.call_display.print_regs()
		self.debugger.update()
		self.data_mem.get_mem()

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

	def get_qr(self):
		if self.qr_active:
			url = bytearray()
			x = 0xa800
			while self.sim.c_config.emu_seg[x] != 0:
				url.append(self.sim.c_config.emu_seg[x])
				x += 1
			return bytes(url).decode()
		else: tk.messagebox.showerror('Error', 'No QR code is currently present on-screen!')

	def save_qr(self):
		url = self.get_qr()
		if url is not None:
			self.root.clipboard_clear()
			self.root.clipboard_append(url)
			self.root.update()

	def open_qr(self):
		url = self.get_qr()
		if url is not None: webbrowser.open_new_tab(url)

	def core_step_loop(self):
		if profile_mode:
			with cProfile.Profile() as pr:
				while not self.single_step: self.core_step()
				pr.print_stats()
		else:
			while not self.single_step: self.core_step()

	def decode_instruction(self, csr = None, pc = None):
		if csr is None: csr = self.sim.core.regs.csr
		if pc is None: pc = self.sim.core.regs.pc
		return self.decode_instruction_(csr, pc)

	@functools.lru_cache
	def decode_instruction_(self, csr, pc):
		self.disas.input_file = b''
		for i in range(3): self.disas.input_file += self.read_cmem((pc + i*2) & 0xfffe, csr).to_bytes(2, 'little')
		self.disas.addr = 0
		ins_str, ins_len, dsr_prefix, _ = self.disas.decode_ins(True)
		if dsr_prefix:
			self.disas.last_dsr_prefix = ins_str
			last_dsr_prefix_str = f'DW {int.from_bytes(self.disas.input_file[:2], "little"):04X}'
			self.disas.addr += 2
			ins_str, inslen, _, used_dsr_prefix = self.disas.decode_ins(True)
			if used_dsr_prefix: return ins_str, inslen
			else: return last_dsr_prefix_str, 2
		return ins_str, ins_len

	@staticmethod
	def nearest_num(l, n): return max([i for i in l if i <= n], default = None)

	def get_instruction_label(self, addr):
		near = self.nearest_num(self.labels.keys(), addr)
		if near is None: return
		elif near >> 16 != addr >> 16: return
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

		elif config.hardware_id in (4, 5):
			if config.hardware_id == 4: screen_data_status_bar = [
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
			else: screen_data_status_bar = [
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
				sbar[0x10] & 1,  # ◀
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
	def get_scr_data_cwii(scr_bytes_lo, scr_bytes_hi):
		sbar = scr_bytes_lo[0]
		sbar1 = scr_bytes_hi[0]

		if hasattr(config, 'is_graphlight') and config.is_graphlight:
			screen_data_status_bar = [
			sbar[1]    & 1    + (2 if sbar1[1] & 1 else 0),  # [S]
			sbar[3]    & 1    + (2 if sbar1[3] & 1 else 0),  # √[]/
			sbar[4]    & 1    + (2 if sbar1[4] & 1 else 0),  # [Deg]
			sbar[5]    & 1    + (2 if sbar1[5] & 1 else 0),  # [Rad]
			sbar[6]    & 1    + (2 if sbar1[6] & 1 else 0),  # [Gra]
			sbar[7]    & 1    + (2 if sbar1[7] & 1 else 0),  # FIX
			sbar[8]    & 1    + (2 if sbar1[8] & 1 else 0),  # SCI
			sbar[9]    & 1    + (2 if sbar1[8] & 1 else 0),  # f(𝑥)
			sbar[0xa]  & 1  + (2 if sbar1[0xa] & 1 else 0),  # 𝐄
			sbar[0xb]  & 1  + (2 if sbar1[0xb] & 1 else 0),  # 𝒊
			sbar[0xc]  & 1  + (2 if sbar1[0xc] & 1 else 0),  # ∠
			sbar[0xd]  & 1  + (2 if sbar1[0xd] & 1 else 0),  # ⇩
			sbar[0xe]  & 1  + (2 if sbar1[0xe] & 1 else 0),  # (✓)
			sbar[0xf]  & 1  + (2 if sbar1[0xe] & 1 else 0),  # g(𝑥)
			sbar[0x10] & 1 + (2 if sbar1[0x10] & 1 else 0),  # ◀
			sbar[0x11] & 1 + (2 if sbar1[0x11] & 1 else 0),  # ▼
			sbar[0x12] & 1 + (2 if sbar1[0x12] & 1 else 0),  # ▲
			sbar[0x13] & 1 + (2 if sbar1[0x13] & 1 else 0),  # ▶
			sbar[0x15] & 1 + (2 if sbar1[0x15] & 1 else 0),  # ⏸
			sbar[0x16] & 1 + (2 if sbar1[0x16] & 1 else 0),  # ☼
			]
		else:
			screen_data_status_bar = [
			sbar[1]    & 1    + (2 if sbar1[1] & 1 else 0),  # [S]
			sbar[3]    & 1    + (2 if sbar1[3] & 1 else 0),  # √[]/
			sbar[4]    & 1    + (2 if sbar1[4] & 1 else 0),  # [D]
			sbar[5]    & 1    + (2 if sbar1[5] & 1 else 0),  # [R]
			sbar[6]    & 1    + (2 if sbar1[6] & 1 else 0),  # [G]
			sbar[7]    & 1    + (2 if sbar1[7] & 1 else 0),  # FIX
			sbar[8]    & 1    + (2 if sbar1[8] & 1 else 0),  # SCI
			sbar[0xa]  & 1  + (2 if sbar1[0xa] & 1 else 0),  # 𝐄
			sbar[0xb]  & 1  + (2 if sbar1[0xb] & 1 else 0),  # 𝒊
			sbar[0xc]  & 1  + (2 if sbar1[0xc] & 1 else 0),  # ∠
			sbar[0xd]  & 1  + (2 if sbar1[0xd] & 1 else 0),  # ⇩
			sbar[0xe]  & 1  + (2 if sbar1[0xe] & 1 else 0),  # (✓)
			sbar[0x10] & 1 + (2 if sbar1[0x10] & 1 else 0),  # ◀
			sbar[0x11] & 1 + (2 if sbar1[0x11] & 1 else 0),  # ▼
			sbar[0x12] & 1 + (2 if sbar1[0x12] & 1 else 0),  # ▲
			sbar[0x13] & 1 + (2 if sbar1[0x13] & 1 else 0),  # ▶
			sbar[0x15] & 1 + (2 if sbar1[0x15] & 1 else 0),  # ⏸
			sbar[0x16] & 1 + (2 if sbar1[0x16] & 1 else 0),  # ☼
			]

		screen_data = [[(2 if scr_bytes_hi[1+i][j] & (1 << k) > 0 else 0) + (1 if scr_bytes_lo[1+i][j] & (1 << k) else 0) for j in range(0x18) for k in range(7, -1, -1)] for i in range(63)]

		return screen_data_status_bar, screen_data

	def reset_core(self):
		self.sim.u8_reset()
		if config.hardware_id == 6:
			self.scr[3][0] = self.scr[3][1] = None
			for i in range(0x1000): self.sim.c_config.sfr[i] = 0xff
			self.sim.c_config.sfr[2] = 0x13
			self.sim.c_config.sfr[3] = 3
			self.sim.c_config.sfr[4] = 2
			self.sim.c_config.sfr[5] = 0x40
			self.sim.c_config.sfr[0xa] = 3
			self.sim.c_config.sfr[0xe] = 0
			self.sim.c_config.sfr[0xf] = 0x82
			self.sim.c_config.sfr[0x900] = 6
			self.sim.c_config.sfr[1] = 0x30
			for i in range(0x10, 0x4f): self.sim.c_config.sfr[i] = 0
		elif config.hardware_id == 2 and self.is_5800p: self.sim.write_mem_data(4, 0x7ffe, 2, 0x44ff)

		self.call_trace = []
		self.standby.stop_mode = False
		self.shutdown = False
		self.prev_csr_pc = None
		self.update_displays()

	def exit_sim(self):
		if self.rom8: os.remove(config.interface_path)

		pygame.quit()
		self.root.quit()
		if os.name != 'nt': os.system('xset r on')
		sys.exit()

	def pygame_loop(self):
		if self.single_step and self.step: self.core_step()
		if (self.single_step and self.step) or not self.single_step: self.update_displays()

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

		if (not self.single_step and ((config.hardware_id == 6 and (self.screen_changed or self.always_update)) or config.hardware_id != 6)) or (self.single_step and (self.step or disp_lcd != self.curr_buffer)):
			self.curr_buffer = disp_lcd
			self.screen_changed = False
			self.display.fill((214, 227, 214) if config.hardware_id != 6 else (255, 255, 255))

			if disp_lcd:
				if self.scr[3][disp_lcd-1] is not None: scr_bytes = [self.read_dmem_bytes(self.scr[3][disp_lcd-1] + i*self.scr[1], self.scr[1]) for i in range(self.scr[2])]
				if config.hardware_id == 6 and self.scr[3][0] is not None: scr_bytes = [0 if self.scr[3][1] is None else int.from_bytes(self.read_dmem_bytes(self.scr[3][1], 3), 'little')] + scr_bytes
				if config.hardware_id == 5 and not self.buffers_no_2bpp:
					scr_bytes_hi = [self.read_dmem_bytes(self.scr[3][disp_lcd-1] + self.scr[1]*self.scr[2] + i*self.scr[1], self.scr[1]) for i in range(self.scr[2])]
					screen_data_status_bar, screen_data = self.get_scr_data_cwii(tuple(scr_bytes), tuple(scr_bytes_hi))
				elif self.scr[3][disp_lcd-1] is not None: screen_data_status_bar, screen_data = self.get_scr_data(*scr_bytes)
			else:
				self.disp.update_emu_hi_scr() 
				screen_data_status_bar, screen_data = self.disp.get_scr_data()
			
			scr_range = 0 if self.force_display else self.sim.c_config.sfr[0x30] & 7
			scr_mode = 5 if self.force_display else self.sim.c_config.sfr[0x31] & 7

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
						if data[7] and i < 11: pygame.draw.circle(self.display, self.pix_color, (n(4.5), offset_h + self.sbar_hi + config.pix*11), config.pix * (3/4))
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

@staticmethod
def report_exception(e, exc, tb):
	message = f'[{type(exc).__name__}] '
	if issubclass(e, OSError) and exc.strerror:
		if os.name == 'nt':
			if exc.winerror: errno = f'WE{exc.winerror}'
			else: errno = exc.errno
		else: errno = exc.errno
		if exc.filename:
			fname = exc.filename
			if exc.filename2: fname += f' -> {exc.filename2}'
			fname += ':'
		else: fname = ''
		message += f"{fname} {exc.strerror} ({errno})"
	else: message += str(exc)

	logging.error(message + ' (full traceback below)')
	traceback.print_exc()

if __name__ == '__main__':
	if len(sys.argv) > 2:
		print('Usage:\n  main.py <script-path>\n  main.py <module-name>')
		sys.exit()

	logging.info(f'Importing config script {sys.argv[1] if len(sys.argv) > 1 else "config.py"}')
	spec = importlib.util.spec_from_file_location('config', sys.argv[1] if len(sys.argv) > 1 else 'config.py')
	if spec is None:
		logging.warning(f'Cannot import config script as file, importing as module')
		try: config = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else 'config')
		except ImportError as e:
			logging.error(f'Cannot import config script as module: {str(e)}')
			sys.exit()
	else:
		config = importlib.util.module_from_spec(spec)
		sys.modules['config'] = config
		spec.loader.exec_module(config)

	if hasattr(config, 'dt_format') and config.dt_format != '%d/%m/%Y %H:%M:%S':
		logging.basicConfig(datefmt = config.dt_format, format = '[%(asctime)s] %(levelname)s: %(message)s', level = level, force = True)
		logging.info(f'Config script imported sucessfully. Date-time format is {config.dt_format}')
	else: logging.info('Config script imported sucessfully')

	# Load the sim library
	sim_lib = ctypes.CDLL(os.path.abspath(config.shared_lib))

	sim_lib.u8_step.argtypes = [ctypes.POINTER(u8_core_t)]

	sim_lib.setup_mcu.argtypes = [ctypes.POINTER(c_config), ctypes.POINTER(u8_core_t), ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8), ctypes.c_int, ctypes.c_int]
	sim_lib.core_step.argtypes = [ctypes.POINTER(c_config), ctypes.POINTER(u8_core_t)]

	sim_lib.read_reg_er.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8]
	sim_lib.read_reg_er.restype = ctypes.c_uint16

	sim_lib.read_mem_data.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8]
	sim_lib.read_mem_data.restype = ctypes.c_uint64
	sim_lib.write_mem_data.argtypes = [ctypes.POINTER(u8_core_t), ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_uint64]

	tk.Tk.report_callback_exception = report_exception

	try:
		sim = Sim(no_clipboard, peripheral.bcd)
		sim.run()
	except Exception: report_exception(*sys.exc_info())
