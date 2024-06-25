from .wdt import WDT
from .standby import Standby
from .timer import Timer
from .keyboard import Keyboard
from .screen import Screen

try:
	from .bcd import BCD
	bcd = True
except ImportError: bcd = False
