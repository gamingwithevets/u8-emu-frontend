# Configuration file for u8_emu frontend

# * Required if ROM8 mode is disabled. If ROM8 mode is enabled this setting may be overwritten.
# ** Optional, may be overwritten by a ROM8.

# Path to the shared library.
shared_lib = 'core.so'

# Path to the ROM/ROM8 file.
rom_file = 'rom.bin'

# ROM8 mode; set to True if a ROM8 file was provided. (optional; default = False)
rom8 = False

# Labels files for debugging. (optional)
# Please provide file paths.
labels = []

# Hardware type. *
# 0 = SOLAR II
# 2 = ES, FC, fx-5800P
# 3 = ES PLUS
# 4 = ClassWiz (First generation - EX/X/CWI)
# 5 = ClassWiz (Second generation - CW/CWII)
# 6 = TI MathPrint (ML620418A)
hardware_id = 3

# Enable this for "sample" CW ROMs. (optional)
sample = False

# Toggle Graph Light mode. Optional; default = False. ClassWiz CW only.
is_graphlight = False

# Custom buffers. If this is a list, it overwrites the internal screen buffer list.
# Not applicable for TI MathPrint.
custom_buffers = None

# Disable 2BPP mode for buffers. ClassWiz CW only.
buffers_no_2bpp = False

# Toggle fx-5800P mode. Optional; default = False. ES only.
is_5800p = False

# Path to the flash ROM. fx-5800P mode only.
#flash_rom_file = None

# Toggle real/emulator ROM mode. *
real_hardware = False

# KO mode. ES PLUS hardware type only. If omitted or has an invalid value, 0 will be used.
# NOTE: Also defines the hardware subtype of ES PLUS.
# 0 = Later ES PLUS - Use F046H for KO (default)
# 1 = Early ES PLUS - Use F044H for KO
ko_mode = 0

# Pd value. Set on startup.
# If omitted, Pd value is not set.
pd_value = 0

# Path to the status bar image. **
status_bar_path = 'images/interface_es_bar.png'

# Path to the interface image. **
interface_path = 'images/interface_esp_83gtp.png'

# Settings for the Tkinter window.

# Width and height of the Pygame embed widget and interface image. (optional)
width = 405
height = 816

# Width and height of the status bar. (optional)
s_width = 288
s_height = 12

# Name of the Tkinter window. **
# Default: 'u8-emu-frontend'
root_w_name = 'fx-83GT PLUS Emulator'

# "Console" text font.
console_font = ('Consolas', 11)

# "Console" background color.
console_bg = '#0c0c0c'

# "Console" text color.
console_fg = '#cccccc'

# Pygame text color.
pygame_color = (255, 255, 255)

# Y coordinate of the text. (default: 22)
text_y = 22

# Top left corner of the screen. *
screen_tl_w = 58
screen_tl_h = 132

# Note that decimal pixel sizes do not look correctly.

# Pixel width. *
pix = 3

# Pixel height. Not used for SOLAR II and TI MathPrint.
# If omitted, the pixel width will be used.
#pix_hi = None

# Small pixel size. Only used for SOLAR II.
# pix_s = None

# Pixel color. (default: (0, 0, 0))
pix_color = (0, 0, 0)

# Hex display window size.
data_mem_width = 700
data_mem_height = 600

# Hex display text font.
data_mem_font = ('Courier New', 11)

# Crop areas of the status bar. (optional)
status_bar_crops = (
(0, 0, 8, 10),     # [S]
(9, 0, 9, 10),     # [A]
(21, 0, 8, 9),     # M
(32, 0, 17, 10),   # STO
(50, 0, 17, 10),   # RCL
(70, 0, 21, 10),   # STAT
(91, 0, 32, 10),   # CMPLX
(123, 0, 19, 9),   # MAT
(142, 0, 17, 10),  # VCT
(161, 0, 9, 10),   # [D]
(170, 0, 9, 10),   # [R]
(180, 0, 9, 10),   # [G]
(192, 0, 14, 9),   # FIX
(206, 0, 14, 10),  # SCI
(224, 0, 23, 10),  # Math
(249, 0, 9, 9),    # v
(258, 0, 9, 9),    # ^
(268, 0, 19, 11),  # Disp
)

# Keymap for the keyboard. **
# None = core reset
keymap = {
	(7, 0): ((41,  293, 48, 38), 'f1',         ''),
	(7, 1): ((95,  301, 48, 38), 'f2',         ''),
	(7, 2): ((187, 293, 32, 23), 'up',         ''),
	(7, 3): ((233, 323, 21, 31), 'right',      ''),
	(7, 4): ((262, 301, 48, 38), 'f3',         'home'),
	None:   ((316, 293, 48, 38), 'f4',         ''),
	(6, 0): ((38,  364, 49, 29), 'f5',         ''),
	(6, 1): ((92,  364, 49, 29), 'f6',         ''),
	(6, 2): ((152, 323, 21, 31), 'left',       ''),
	(6, 3): ((187, 363, 32, 23), 'down',       ''),
	(6, 4): ((264, 364, 49, 29), 'f7',         ''),
	(6, 5): ((318, 364, 49, 29), 'f8',         ''),
	(5, 0): ((43,  411, 49, 29), '',           ''),
	(5, 1): ((97,  411, 49, 29), '',           ''),
	(5, 2): ((151, 411, 49, 29), '',           ''),
	(5, 3): ((205, 411, 49, 29), '',           ''),
	(5, 4): ((259, 411, 49, 29), '',           ''),
	(5, 5): ((313, 411, 49, 29), '',           ''),
	(4, 0): ((43,  457, 49, 29), '',           ''),
	(4, 1): ((97,  457, 49, 29), '',           ''),
	(4, 2): ((151, 457, 49, 29), '',           ''),
	(4, 3): ((205, 457, 49, 29), '',           ''),
	(4, 4): ((259, 457, 49, 29), '',           ''),
	(4, 5): ((313, 457, 49, 29), '',           ''),
	(3, 0): ((43,  503, 49, 29), '',           ''),
	(3, 1): ((97,  503, 49, 29), '',           ''),
	(3, 2): ((151, 503, 49, 29), 'parenleft',  ''),
	(3, 3): ((205, 503, 49, 29), 'parenright', ''),
	(3, 4): ((259, 503, 49, 29), '',           ''),
	(3, 5): ((313, 503, 49, 29), '',           ''),
	(2, 0): ((42,  550, 61, 41), '7',          ''),
	(2, 1): ((107, 550, 61, 41), '8',          ''),
	(2, 2): ((172, 550, 61, 41), '9',          ''),
	(2, 3): ((237, 550, 61, 41), 'backspace',  ''),
	(2, 4): ((302, 550, 61, 41), 'space',      'tab'),
	(1, 0): ((42,  607, 61, 41), '4',          ''),
	(1, 1): ((107, 607, 61, 41), '5',          ''),
	(1, 2): ((172, 607, 61, 41), '6',          ''),
	(1, 3): ((237, 607, 61, 41), 'asterisk',   ''),
	(1, 4): ((302, 607, 61, 41), 'slash',      ''),
	(0, 0): ((42,  664, 61, 41), '1',          ''),
	(0, 1): ((107, 664, 61, 41), '2',          ''),
	(0, 2): ((172, 664, 61, 41), '3',          ''),
	(0, 3): ((237, 664, 61, 41), 'plus',       ''),
	(0, 4): ((302, 664, 61, 41), 'minus',      ''),
	(4, 6): ((42,  721, 61, 41), '0',          ''),
	(3, 6): ((107, 721, 61, 41), 'period',     ''),
	(2, 6): ((172, 721, 61, 41), 'e',          ''),
	(1, 6): ((237, 721, 61, 41), '',           ''),
	(0, 6): ((302, 721, 61, 41), 'return',     ''),
}

# Keymap: use chars instead of keysyms. **
use_char = False

# Date and time format for logging module. (optional)
# Default: '%d/%m/%Y %H:%M:%S'
dt_format = '%d/%m/%Y %H:%M:%S'
