#!/usr/bin/env python3
import struct, re, enum, sys

try:
	import chafa
	from PIL import Image
	import io
	can_draw_image = True
	def draw_image(img):
		img_pil = Image.open(io.BytesIO(img))
		scale = 150 / img_pil.height
		config = chafa.CanvasConfig()

		config.width = int(img_pil.width * scale)
		config.height = int(img_pil.height * scale)
		config.pixel_mode = chafa.PixelMode.CHAFA_PIXEL_MODE_SIXELS

		canvas = chafa.Canvas(config)
		data = [c for pxl in img_pil.getdata() for c in (*pxl, 255)]
		canvas.draw_all_pixels(
		    chafa.PixelType.CHAFA_PIXEL_RGBA8_UNASSOCIATED,
		    data,
		    img_pil.width, img_pil.height,
		    img_pil.width * 4
		)
		print(canvas.print(fallback = True).decode())

except ImportError:
	pass

class ROM8Tag(enum.IntEnum):
	end = 0
	compatible = enum.auto()
	prop = enum.auto()
	rom = enum.auto()
	faceSVG = enum.auto()
	facePNG = enum.auto()
	faceDisplayBounds = enum.auto()
	faceGUIKeys = enum.auto()
	faceKeymap = enum.auto()
	calcType = enum.auto()
	faceKeybinds = enum.auto()

class CalcType(enum.IntFlag):
	old = 1
	cwi = 2
	cwii = 3
	type_mask = 3
	emu = 4

SUPPORTED_ROM8 = b'pitust,1'

def read8(data):
	if type(data) == str:
		with open(data, 'rb') as fd:
			data = fd.read()

	offs = 0
	while True:
		typ, len = struct.unpack('<II', data[offs:offs + 8])
		pay = data[offs + 8:offs + 8 + len]
		offs += 8 + len
		if typ == 0:
			break

		typ8 = ROM8Tag(typ)
		if typ8 == ROM8Tag.compatible:
			assert pay == SUPPORTED_ROM8
			continue

		yield typ8, pay

class write8:
	def __init__(self, file) -> None:
		self.fd = open(file, 'wb')
	def __enter__(self):
		self.write(ROM8Tag.compatible, SUPPORTED_ROM8)
		return self
	def __exit__(self, *_):
		self.write(ROM8Tag.end, b'')
		self.fd.close()
	def write(self, tag, pay):
		self.fd.write(struct.pack('<II', int(tag), len(pay)))
		self.fd.write(pay)
	def prop(self, k, v):
		self.write(ROM8Tag.prop, b'%s=%s' % (k.encode(), v.encode()))

def readkeys(data):
	if type(data) == str:
		with open(data, 'rb') as fd:
			data = fd.read()

	buf = b''
	phase = 0
	keysym = 0
	for b in data:
		if phase == 0:
			keysym = b
			phase = 1
			buf = b''
		elif phase == 1:
			if b == 0:
				yield keysym, buf.decode()
				phase = 0
			else:
				buf += bytes([b])

def fromkio(ki, ko):
	assert (ki-1)&ki == 0
	assert (ko-1)&ko == 0

	ki = (ki-1).bit_count()
	ko = (ko-1).bit_count()
	kc = (ki<<4)|ko
	return kc

def tokio(keysym):
	return 1 << (keysym >> 4), 1 << (keysym & 0xf)

class writekeys:
	def __init__(self) -> None:
		self.out = b''
	def __enter__(self):
		return self
	def __exit__(self, *_):
		pass
	def key(self, name, sym):
		self.out += bytes([sym]) + name.encode() + b'\x00'
	def keyIO(self, name, ki, ko):
		self.key(name, fromkio(ki, ko))

def run():
	if len(sys.argv) == 1:
		for k, v in list(globals().items()):
			if k.startswith('cmd_'):
				vc = v.__code__
				kwd = v.__kwdefaults__
				if kwd == None:
					kwd = {}
				assert vc.co_argcount == 0
				assert vc.co_posonlyargcount == 0
				items = []
				for arg in vc.co_varnames[:vc.co_kwonlyargcount]:
					if arg in kwd:
						items.append('[--%s=VALUE]' % arg)
					else:
						items.append('--%s=VALUE' % arg)
				print('Usage: rom8tool %s %s' % (k[4:], ' '.join(items)))
	else:
		for k, func in list(globals().items()):
			if k == 'cmd_' + sys.argv[1]:
				argdict = {}
				vc = func.__code__
				kwd = func.__kwdefaults__
				if kwd == None:
					kwd = {}
				assert vc.co_argcount == 0
				assert vc.co_posonlyargcount == 0
				
				allowed, required = [], []
				for arg in vc.co_varnames[:vc.co_kwonlyargcount]:
					allowed.append(arg)
					if arg not in kwd:
						required.append(arg)

				is_val = False
				for ent in sys.argv[2:]:
					if is_val:
						if is_val in argdict.keys():
							argdict[is_val] += ',' + ent
						else:
							argdict[is_val] = ent
						is_val = False
						continue
					else:
						if ent.startswith('--'):
							ent = ent[1:]
						assert ent.startswith('-'), 'invalid value {}'.format(ent)
						if '=' in ent:
							k, v = ent[2:].split('=')
							if k in argdict.keys():
								argdict[k] += ',' + v
							else:
								argdict[k] = v
						else:
							is_val = ent[1:]
				assert not is_val, 'expected value for argument {}'.format(is_val)
				for k in argdict:
					assert k in allowed, 'invalid argument {}'.format(k)
				for r in required:
					assert r in argdict, 'missing required argument {}'.format(r)
				func(**argdict)
				break
		else:
			print('E: invalid subcommand %s' % sys.argv[1])

def cmd_show(*, file):
	for t, data in read8(file):
		if t == ROM8Tag.prop:
			k, v = data.decode().split('=')
			print('- prop %s: %s' % (k, v))
		elif t == ROM8Tag.rom:
			print('- rom: %d KB' % (len(data) // 1024))
		elif t == ROM8Tag.calcType:
			ct = CalcType(data[0])
			is_real = ' (emulator)' if (ct & CalcType.emu) else ' (real hardware)'
			ct = ct & CalcType.type_mask
			if ct == CalcType.old:
				ct = 'ES+'
			elif ct == CalcType.cwi:
				ct = 'CWI'
			elif ct == CalcType.cwi:
				ct = 'CWII'
			else:
				ct = str(ct)
			print('- calculator type: %s' % (ct + is_real))
		elif t == ROM8Tag.facePNG:
			if can_draw_image:
				print('- png face:')
				draw_image(data)
			else:
				print('- png face')
		elif t == ROM8Tag.faceDisplayBounds:
			x, y, w, h, scale = struct.unpack('<HHHH H', data)
			print('- display bounds: (%d, %d) %dx%d scale %d' % (x, y, w, h, scale))
		elif t == ROM8Tag.faceGUIKeys:
			print('- gui keymap:')
			for i in range(0, len(data), 10):
				x, y, w, h, kc = struct.unpack('<HHHH H', data[i:i + 10])
				print('  - %d, %d %dx%d: keycode 0x%02x' % (x, y, w, h, kc))
		elif t == ROM8Tag.faceKeymap:
			print('- keymap:')
			for ks, name in readkeys(data):
				ki, ko = tokio(ks)
				print('  - [%s]  \tKI %02x KO %02x KS %02x' % (name, ki, ko, ks))
		else:
			print('- tag %s: %s' % (repr(t), repr(data)))

def autogrid(x, y, w, h, advancex, advancey, is_upper):
	if is_upper:
		map = [
			[(0x40, 0x01), (0x40, 0x02), None, None, (0x40, 0x10), (0x40, 0x20)],
			[(0x20, x) for x in (0x01, 0x02, 0x04, 0x08, 0x10, 0x20)],
			[(0x10, x) for x in (0x01, 0x02, 0x04, 0x08, 0x10, 0x20)],
			[(0x08, x) for x in (0x01, 0x02, 0x04, 0x08, 0x10, 0x20)],
		]
	else:
		map = [
			[(0x04, x) for x in (0x01, 0x02, 0x04, 0x08, 0x10)],
			[(0x02, x) for x in (0x01, 0x02, 0x04, 0x08, 0x10)],
			[(0x01, x) for x in (0x01, 0x02, 0x04, 0x08, 0x10)],
			[(x, 0x40) for x in (0x10, 0x08, 0x04, 0x02, 0x01)],
		]
	out = b''
	for xi in range(len(map[0])):
		for yi in range(len(map)):
			if map[yi][xi]:
				ex = x + advancex * xi
				ey = y + advancey * yi
				out += struct.pack('<HHHH H', ex, ey, w, h, fromkio(*map[yi][xi]))
	return out

def cmd_keytest(*, rom, x, y):
	gk = []
	keynames = {}
	x = int(x)
	y = int(y)
	for t, data in read8(rom):
		if t == ROM8Tag.faceGUIKeys:
			for i in range(0, len(data), 10):
				gk.append(struct.unpack('<HHHH H', data[i:i + 10]))
		if t == ROM8Tag.faceKeymap:
			for ks, name in readkeys(data):
				keynames[ks] = name
	for kx, ky, kw, kh, kc in gk:
		if kc in keynames:
			kc = keynames[kc]
		else:
			kc = str(kc)
		kx, ky = int(kx), int(ky)
		kw, kw = int(kw), int(kw)
		if kx <= x and x <= kx + kw and ky <= y and y <= ky + kh:
			print(' + %s' % kc)

def cmd_autogrid(*, x, y, w, h, ax, ay, half, out):
	assert half in ['lower', 'upper']
	dat = autogrid(int(x), int(y), int(w), int(h), int(ax), int(ay), half == 'upper')
	open(out, 'wb').write(dat)
def cmd_gridpoint(*, rects, out):
	ob = b''
	for rect in rects.split(','):
		xy, wh, kc = rect.split(';')
		x, y = xy.split('x')
		w, h = wh.split('x')
		ob += struct.pack('<HHHH H', int(x), int(y), int(w), int(h), int(kc, 16))
	open(out, 'wb').write(ob)

def cmd_wrap_rom_emu(*, rom, face, dispx, dispy, dispscale, gridfiles = '', out):
	rom = open(rom, 'rb').read()
	face = open(face, 'rb').read()
	gdata = b''
	for gfile in gridfiles.split(','):
		if gfile:
			gdata += open(gfile, 'rb').read()
	with write8(out) as wr:
		wr.prop('writer', 'tool8 (wwce)')
		wr.prop('writer.repo', 'https://git.malwarez.xyz/~pitust/wwce')
		wr.prop('model', 'fx-83 GT+')
		# (66, 139) 3x scale 96x31
		if face[0:4] == b'\x89PNG':
			wr.write(ROM8Tag.facePNG, face)
		else:
			wr.write(ROM8Tag.faceSVG, face)
		if gdata:
			wr.write(ROM8Tag.faceGUIKeys, gdata)
		wr.write(ROM8Tag.faceDisplayBounds, struct.pack('<HHHHH', 96, 31, int(dispx), int(dispy), int(dispscale)))
		wr.write(ROM8Tag.rom, rom)
		wr.write(ROM8Tag.calcType, bytes([CalcType.old | CalcType.emu]))

		wk = writekeys()
		wk.keyIO("Shift", 0x80, 0x01)
		wk.keyIO("Alpha", 0x80, 0x02)
		wk.keyIO("Up", 0x80, 0x04)
		wk.keyIO("Right", 0x80, 0x08)
		wk.keyIO("Mode", 0x80, 0x10)
		wk.keyIO("Abs", 0x40, 0x01)
		wk.keyIO("x^3", 0x40, 0x02)
		wk.keyIO("Left", 0x40, 0x04)
		wk.keyIO("Down", 0x40, 0x08)
		wk.keyIO("x^-1", 0x40, 0x10)
		wk.keyIO("log_x", 0x40, 0x20)
		wk.keyIO("a/b", 0x20, 0x01)
		wk.keyIO("sqrt", 0x20, 0x02)
		wk.keyIO("x^2", 0x20, 0x04)
		wk.keyIO("x^n", 0x20, 0x08)
		wk.keyIO("log", 0x20, 0x10)
		wk.keyIO("ln", 0x20, 0x20)
		wk.keyIO("(-)", 0x10, 0x01)
		wk.keyIO("dms", 0x10, 0x02)
		wk.keyIO("hyp", 0x10, 0x04)
		wk.keyIO("sin", 0x10, 0x08)
		wk.keyIO("cos", 0x10, 0x10)
		wk.keyIO("tan", 0x10, 0x20)
		wk.keyIO("RCL", 0x08, 0x01)
		wk.keyIO("ENG", 0x08, 0x02)
		wk.keyIO("(", 0x08, 0x04)
		wk.keyIO(")", 0x08, 0x08)
		wk.keyIO("S<=>D", 0x08, 0x10)
		wk.keyIO("M+", 0x08, 0x20)
		wk.keyIO("7", 0x04, 0x01)
		wk.keyIO("8", 0x04, 0x02)
		wk.keyIO("9", 0x04, 0x04)
		wk.keyIO("DEL", 0x04, 0x08)
		wk.keyIO("AC", 0x04, 0x10)
		wk.keyIO("4", 0x02, 0x01)
		wk.keyIO("5", 0x02, 0x02)
		wk.keyIO("6", 0x02, 0x04)
		wk.keyIO("X", 0x02, 0x08)
		wk.keyIO("div", 0x02, 0x10)
		wk.keyIO("1", 0x01, 0x01)
		wk.keyIO("2", 0x01, 0x02)
		wk.keyIO("3", 0x01, 0x04)
		wk.keyIO("+", 0x01, 0x08)
		wk.keyIO("-", 0x01, 0x10)
		wk.keyIO("0", 0x10, 0x40)
		wk.keyIO(".", 0x08, 0x40)
		wk.keyIO("x10", 0x04, 0x40)
		wk.keyIO("Ans", 0x02, 0x40)
		wk.keyIO("=", 0x01, 0x40)
		wr.write(ROM8Tag.faceKeymap, wk.out)

if __name__ == '__main__': run()
