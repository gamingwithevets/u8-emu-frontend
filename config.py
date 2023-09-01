# Configuration file for u8_emu frontend

# Path to the shared library.
shared_lib = 'core.so'

# Path to the ROM file.
rom_file = 'rom.bin'

# Toggle real/emulator keyboard.
real_kb = False

# Path to the status bar image.
status_bar_path = 'images/interface_es_bar.png'

# Path to the interface image.
interface_path = 'images/interface_esp_83gtp.png'

# Settings for the Tkinter window.

# Width and height of the Pygame embed widget.
width = 405
height = 816

# Name of the Tkinter window.
root_w_name = 'fx-83GT PLUS Emulator'

# "Console" text font.
console_font = ('Consolas', 11)

# "Console" background color.
console_bg = '#0c0c0c'

# "Console" text color.
console_fg = '#cccccc'

# Pygame text color.
pygame_color = (255, 255, 255)

# Hex display window size.
data_mem_width = 700
data_mem_height = 600

# Hex display text font.
data_mem_font = ('Courier New', 11)

# The settings below should work out of the box for ES and ES PLUS ROMs.
# Only modify if you know what you're doing.

# Crop areas of the status bar.
status_bar_crops = (
(0, 0, 8, 10),     # [S]
(9, 0, 9, 10),     # [A]
(21, 0, 8, 9),     # M
(32, 0, 17, 10),   # STO
(50, 0, 17, 10),   # RCL
(70, 0, 21, 10),   # STAT
(91, 0, 32, 10),   # CMPLX
(123, 0, 36, 10),  # MAT
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

# Keymap for the keyboard.
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

# Date and time format for logging module.
dt_format = '%d/%m/%Y %H:%M:%S'
