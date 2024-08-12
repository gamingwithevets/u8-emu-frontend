import copy

def write_std_string(f, string):
	f.write(len(string).to_bytes(8, 'little'))
	f.write(string)

def tuple_to_color(color): return (0xff << 24) | (color[0] << 16) | (color[1] << 8) | color[2]

class TemplateClass:
	def __str__(self): return f'{self.__class__.__name__}({", ".join(k+"="+repr(v) for k, v in vars(self).items())})'
	def __repr__(self): return self.__str__()

class SDL_Rect(TemplateClass):
	def __init__(self, x, y, w, h):
		self.x = x
		self.y = y
		self.w = w
		self.h = h

	def to_file(self, f):
		f.write(self.x.to_bytes(4, 'little'))
		f.write(self.y.to_bytes(4, 'little'))
		f.write(self.w.to_bytes(4, 'little'))
		f.write(self.h.to_bytes(4, 'little'))

class keydata(TemplateClass):
	# not generated with ChatGPT I swear
	sdl_keycodes = {
		'': 0,
		'a': 97, 'b': 98, 'c': 99, 'd': 100, 'e': 101, 'f': 102, 'g': 103, 'h': 104, 'i': 105,
		'j': 106, 'k': 107, 'l': 108, 'm': 109, 'n': 110, 'o': 111, 'p': 112, 'q': 113,
		'r': 114, 's': 115, 't': 116, 'u': 117, 'v': 118, 'w': 119, 'x': 120, 'y': 121, 'z': 122,
		'1': 49, '2': 50, '3': 51, '4': 52, '5': 53, '6': 54, '7': 55, '8': 56, '9': 57, '0': 48,
		'return': 13, 'escape': 27, 'backspace': 8, 'tab': 9, 'space': 32,
		'minus': 45, 'equal': 61, 'leftbracket': 91, 'rightbracket': 93,
		'parenleft': 40, 'parenright': 41, 'asterisk': 42, 'plus': 43, 'minus': 45,
		'backslash': 92, 'semicolon': 59, 'apostrophe': 39, 'grave': 96,
		'comma': 44, 'period': 46, 'slash': 47,
		'capslock': 1073741881, 'f1': 1073741882, 'f2': 1073741883, 'f3': 1073741884, 'f4': 1073741885,
		'f5': 1073741886, 'f6': 1073741887, 'f7': 1073741888, 'f8': 1073741889, 'f9': 1073741890, 'f10': 1073741891,
		'f11': 1073741892, 'f12': 1073741893,
		'printscreen': 1073741894, 'scrolllock': 1073741895, 'pause': 1073741896, 'insert': 1073741897,
		'home': 1073741898, 'pageup': 1073741899, 'delete': 127, 'end': 1073741901, 'pagedown': 1073741902,
		'right': 1073741903, 'left': 1073741904, 'down': 1073741905, 'up': 1073741906,
		'numlockclear': 1073741907, 'kp_divide': 1073741908, 'kp_multiply': 1073741909, 'kp_minus': 1073741910,
		'kp_plus': 1073741911, 'kp_enter': 1073741912, 'kp_1': 1073741913, 'kp_2': 1073741914, 'kp_3': 1073741915,
		'kp_4': 1073741916, 'kp_5': 1073741917, 'kp_6': 1073741918, 'kp_7': 1073741919, 'kp_8': 1073741920, 'kp_9': 1073741921,
		'kp_0': 1073741922, 'kp_period': 1073741923,
	}
	def __init__(self, rect, keys):
		self.rect = SDL_Rect(*rect)
		self.keys = keys

	def to_file(self, f):
		self.rect.to_file(f)
		f.write(len(self.keys).to_bytes(8, 'little'))
		for key in self.keys: f.write(self.sdl_keycodes[key].to_bytes(4, 'little'))

class config(TemplateClass):
	def __init__(self, config):
		self.rom_file = config.rom_file.encode('utf-8')
		self.flash_rom_file = config.flash_rom_file.encode('utf-8') if hasattr(config, 'flash_rom_file') else b''
		self.hardware_id = config.hardware_id
		self.real_hardware = int(config.real_hardware)
		self.sample = int(config.sample) if hasattr(config, 'sample') else 0
		self.is_5800p = int(config.is_5800p) if hasattr(config, 'is_5800p') else 0
		self.old_esp = config.ko_mode if hasattr(config, 'ko_mode') and config.ko_mode == 1 else 0
		self.pd_value = config.pd_value if hasattr(config, 'pd_value') else 0

		self.status_bar_path = config.status_bar_path.encode('utf-8') if hasattr(config, 'status_bar_path') else b''
		self.interface_path = config.interface_path.encode('utf-8')
		self.w_name = config.root_w_name.encode('utf-8') if hasattr(config, 'root_w_name') else b''
		self.screen_tl_w = config.screen_tl_w
		self.screen_tl_h = config.screen_tl_h
		self.pix_w = config.pix
		self.pix_h = config.pix_hi if hasattr(config, 'pix_hi') else config.pix
		self.pix_color = config.pix_color if hasattr(config, 'pix_color') else (0, 0, 0)
		self.status_bar_crops = [SDL_Rect(*v) for v in config.status_bar_crops] if hasattr(config, 'status_bar_crops') else []
		self.keymap = {(k[1] << 4 | k[0] if type(k) == tuple else (0xff if k is None else k)): keydata(v[0], v[1:]) for k, v in config.keymap.items()} if hasattr(config, 'keymap') else {}

	def to_file(self, f):
		write_std_string(f, b'Genshit configuration file v69')

		write_std_string(f, self.rom_file)
		write_std_string(f, self.flash_rom_file)
		f.write(self.hardware_id.to_bytes(4, 'little'))
		f.write(self.real_hardware.to_bytes(1, 'little'))
		f.write(self.sample.to_bytes(1, 'little'))
		f.write(self.is_5800p.to_bytes(1, 'little'))
		f.write(self.old_esp.to_bytes(1, 'little'))
		f.write(self.pd_value.to_bytes(1, 'little'))

		write_std_string(f, self.status_bar_path)
		write_std_string(f, self.interface_path)
		write_std_string(f, self.w_name)
		f.write(self.screen_tl_w.to_bytes(4, 'little'))
		f.write(self.screen_tl_h.to_bytes(4, 'little'))
		f.write(self.pix_w.to_bytes(4, 'little'))
		f.write(self.pix_h.to_bytes(4, 'little'))
		f.write(tuple_to_color(self.pix_color).to_bytes(4, 'little'))
		f.write(len(self.status_bar_crops).to_bytes(8, 'little'))
		for a in self.status_bar_crops: a.to_file(f)

		f.write(len(self.keymap).to_bytes(8, 'little'))
		for k, v in self.keymap.items():
			f.write(k.to_bytes(1, 'little'))
			v.to_file(f)
