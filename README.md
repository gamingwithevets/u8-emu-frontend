***NOTICE!***  
This frontend is now being replaced by the faster [u8-emu-frontend-cpp](https://github.com/gamingwithevets/u8-emu-frontend-cpp).

---

This is a **frontend** for [Fraser Price / Fraserbc / Delta](https://github.com/Fraserbc)'s [u8_emu](https://github.com/Fraserbc/u8_emu) emulator core, written in mostly Python, with a small bit of C code included.  
**NOTE:** This frontend uses a **fork** of the aforementioned emulator core.  
Most of the code was based on the [SimU8 frontend](https://github.com/gamingwithevets/simu8-frontend).

This frontend serves as a replacement to Delta's own frontend that uses `ncurses`.

# Installation
1. Clone this repository and submodules:
```shell
git clone --recursive https://github.com/gamingwithevets/u8-emu-frontend.git
```
2. Go to the repo directory and run the command below (this assumes the submodule is located in the `u8_emu` directory):
```shell
gcc u8_emu/src/core/*.c peripheral.c -O3 -fPIC -shared -o core.so
```
3. Edit the `config.py` file as needed.
4. `pip install -r requirements.txt`
5. Run `python main.py` (or `python3 main.py`) and you're done.

NOTE: **This frontend uses CairoSVG.** That means if you're on Windows or macOS 
 you need to obtain the necessary libcairo library for your platform and add it to your PATH or copy it to the root of this repo. However **it is only needed for loading ROM8 SVG images**, so you don't have to worry about it too much unless you use a ROM8 with an SVG image.

# Usage
When you open the emulator, you can right-click to see the available functions of the emulator. To step [step into], press the backslash (`\`) key while in **single-step** mode.

To use a custom configuration Python script:
- Run `python main.py <script-path>`. `<script-path>` is the path to your configuration script.
- Or, run `python main.py <module-name>`. `<module-name>` is the name of the configuration script in module name form; for example if your configuration script is in `configs/config_main.py`, then `<module-name>` will be `configs.config_main`.

# Images
This emulator uses images extracted from emulators. To get them, you need to open the emulator EXE and DLL in a program like [7-Zip](https://7-zip.org) or [Resource Hacker](http://angusj.com/resourcehacker)
and extract the right bitmaps.

| | Interface bitmap (DLL) | Status bar bitmap (EXE) |
|--|--|--|
| fx-ES (PLUS) Emulator            | 3001 | 135
| ClassWiz Emulator Subscription   | 103  | 136
| fx-ES PLUS Emulator Subscription | 103  | 171
| fx-92 Collège Emulator Ver.USB   | 8000 | 136

# ROM8 support
This frontend supports the [ROM8 file format](https://hackmd.io/@pitust/HkgeNr6Mp) created by [pitust](https://github.com/pitust). See `config.py` for how to set it up.
