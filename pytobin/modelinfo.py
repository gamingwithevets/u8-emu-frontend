import copy

def write_std_string(f, string):
	f.write(len(string).to_bytes(8, 'little'))
	f.write(string)

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

class color_info:
	def __init__(self, r, g, b):
		self.r = r
		self.g = g
		self.b = b

	def to_file(self, f):
		f.write(self.r.to_bytes(1, 'little'))
		f.write(self.g.to_bytes(1, 'little'))
		f.write(self.b.to_bytes(1, 'little'))

	def __str__(self): return f'{self.__class__.__name__}({", ".join(k+"="+repr(v) for k, v in vars(self).items())})'
	def __repr__(self): return self.__str__()


class keydata(TemplateClass):
	# not generated with ChatGPT I swear
	sdl_keycodes = {
		'': 0x0,
		'backspace': 0x8,
		'tab': 0x9,
		'return': 0xd,
		'escape': 0x1b,
		'space': 0x20,
		'quoteright': 0x27,
		'parenleft': 0x28,
		'parenright': 0x29,
		'asterisk': 0x2a,
		'plus': 0x2b,
		'comma': 0x2c,
		'minus': 0x2d,
		'period': 0x2e,
		'slash': 0x2f,
		'0': 0x30,
		'1': 0x31,
		'2': 0x32,
		'3': 0x33,
		'4': 0x34,
		'5': 0x35,
		'6': 0x36,
		'7': 0x37,
		'8': 0x38,
		'9': 0x39,
		'colon': 0x3a,
		'semicolon': 0x3b,
		'equal': 0x3d,
		'leftbracket': 0x5b,
		'backslash': 0x5c,
		'rightbracket': 0x5d,
		'asciicircum': 0x5e,
		'at': 0x40,
		'underscore': 0x5f,
		'quoteleft': 0x60,
		'a': 0x61,
		'b': 0x62,
		'c': 0x63,
		'd': 0x64,
		'e': 0x65,
		'f': 0x66,
		'g': 0x67,
		'h': 0x68,
		'i': 0x69,
		'j': 0x6a,
		'k': 0x6b,
		'l': 0x6c,
		'm': 0x6d,
		'n': 0x6e,
		'o': 0x6f,
		'p': 0x70,
		'q': 0x71,
		'r': 0x72,
		's': 0x73,
		't': 0x74,
		'u': 0x75,
		'v': 0x76,
		'w': 0x77,
		'x': 0x78,
		'y': 0x79,
		'z': 0x7a,
		'asciitilde': 0,
		'delete': 0x7f,
		'capslock': 0x40000039,
		'f1': 0x4000003a,
		'f2': 0x4000003b,
		'f3': 0x4000003c,
		'f4': 0x4000003d,
		'f5': 0x4000003e,
		'f6': 0x4000003f,
		'f7': 0x40000040,
		'f8': 0x40000041,
		'f9': 0x40000042,
		'f10': 0x40000043,
		'f11': 0x40000044,
		'f12': 0x40000045,
		'printscreen': 0x40000046,
		'scrolllock': 0x40000047,
		'pause': 0x40000048,
		'insert': 0x40000049,
		'home': 0x4000004a,
		'prior': 0x4000004b,
		'end': 0x4000004d,
		'next': 0x4000004e,
		'right': 0x4000004f,
		'left': 0x40000050,
		'down': 0x40000051,
		'up': 0x40000052,
		'numlockclear': 0x40000053,
		'kp_divide': 0x40000054,
		'kp_multiply': 0x40000055,
		'kp_minus': 0x40000056,
		'kp_plus': 0x40000057,
		'kp_enter': 0x40000058,
		'kp_1': 0x40000059,
		'kp_2': 0x4000005a,
		'kp_3': 0x4000005b,
		'kp_4': 0x4000005c,
		'kp_5': 0x4000005d,
		'kp_6': 0x4000005e,
		'kp_7': 0x4000005f,
		'kp_8': 0x40000060,
		'kp_9': 0x40000061,
		'kp_0': 0x40000062,
		'kp_period': 0x40000063,
	}

	def __init__(self, rect, keys):
		self.rect = SDL_Rect(*rect)
		self.keys = []
		for key in keys:
			if not key: continue
			if key not in self.sdl_keycodes:
				print(f'WARNING: key {key} not in valid keycodes list, skipping\n(If this is a valid Tkinter key, please create an issue on GitHub)')
				continue
			if self.sdl_keycodes[key] == 0:
				print(f'WARNING: key {key} does not map to a valid SDL2 keycode, skipping')
			self.keys.append(key)

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
		self.pix_color = color_info(*config.pix_color) if hasattr(config, 'pix_color') else color_info(0, 0, 0)
		self.status_bar_crops = [SDL_Rect(*v) for v in config.status_bar_crops] if hasattr(config, 'status_bar_crops') else []
		self.keymap = {(k[1] << 4 | k[0] if type(k) == tuple else (0xff if k is None else k)): keydata(v[0], v[1:]) for k, v in config.keymap.items()} if hasattr(config, 'keymap') else {}

		self.width = config.width if hasattr(config, 'width') else 0
		self.height = config.height if hasattr(config, 'height') else 0
		self.ram = f'ram/{self.rom_file[:-4].decode()}'.encode()

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
		self.pix_color.to_file(f)
		f.write(len(self.status_bar_crops).to_bytes(8, 'little'))
		for a in self.status_bar_crops: a.to_file(f)

		f.write(len(self.keymap).to_bytes(8, 'little'))
		for k, v in self.keymap.items():
			f.write(k.to_bytes(1, 'little'))
			v.to_file(f)

		f.write(self.width.to_bytes(4, 'little'))
		f.write(self.height.to_bytes(4, 'little'))
		write_std_string(f, self.ram)
