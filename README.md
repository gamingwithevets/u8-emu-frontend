This is a **frontend** for [Fraser Price / Fraserbc / Delta](https://github.com/Fraserbc)'s [u8_emu](https://github.com/Fraserbc/u8_emu) emulator written in Python. 
Most of the code was based on the [SimU8 frontend](https://github.com/gamingwithevets/simu8-frontend).

This frontend serves as a replacement to Delta's own frontend that uses `ncurses`. Currently, it's best to use an emulator ROM, as the keyboard for real ROMs doesn't work at the moment.

# Installation
1. Clone this repository and the submodule:
```shell
git clone https://github.com/gamingwithevets/u8-emu-frontend.git
git submodule update
```
2. Go to the repo directory and run the command below (this assumes the submodule is located in the `u8_emu` directory):
```shell
gcc u8_emu/src/core/*.c -O3 -fPIC -shared -o core.so
```
3. Edit the `config.py` file as needed.
4. Run `python main.py` (or `python3 main.py`) and you're done.

# Usage
When you open the emulator, you can right-click to see the available functions of the emulator.

To step, press any key (except the keys reserved for other functions). You can also hold down a key to run the emulator at a reasonable speed, though not as fast as when single-step mode is disabled.

# Images
This emulator uses images extracted from the ES PLUS emulators. To get them, you need to open the emulator EXE (`<model> Emulator.exe`) and DLL (`fxESPLUS_P<num>.dll`) in a program like [7-Zip](https://7-zip.org) or [Resource Hacker](http://angusj.com/resourcehacker).
- For the interface, you need to extract bitmap **3001** from the emulator **DLL**.
- For the status bar, you need to extract bitmap **135** from the emulator **EXE**.
