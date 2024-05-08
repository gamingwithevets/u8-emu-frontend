import os; os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = ''
import sys
try: import pygame
except ImportError:
	print('Please install pygame!')
	sys.exit()
import platform

if sys.version_info < (3, 8, 0):
	print('This program requires at least Python 3.8.0. (You are running Python '+platform.python_version()+')')
	sys.exit()

if pygame.version.vernum < (2, 2, 0):
	print(f'This program requires at least Pygame 2.2.0. (You are running Pygame {pygame.version.ver})')
	sys.exit()

print('All good! You can run u8-emu-frontend on your system.\n(run `pip install -r requirements.txt` if you see import errors.)')
