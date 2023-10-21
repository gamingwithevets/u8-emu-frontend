This is a **frontend** for [Fraser Price / Fraserbc / Delta](https://github.com/Fraserbc)'s [u8_emu](https://github.com/Fraserbc/u8_emu) emulator written in Python. 
Most of the code was based on the [SimU8 frontend](https://github.com/gamingwithevets/simu8-frontend).

This frontend serves as a replacement to Delta's own frontend that uses `ncurses`.

# Installation
1. Clone this repository and submodules:
```shell
git clone https://github.com/gamingwithevets/u8-emu-frontend.git
git submodule init
git submodule update
```
2. Go to the repo directory and run the command below (this assumes the submodule is located in the `u8_emu` directory):
```shell
gcc u8_emu/src/core/*.c -O3 -fPIC -shared -o core.so
```
3. Edit the `config.py` file as needed.
4. Run `python main.py` (or `python3 main.py`) and you're done.

# Usage
When you open the emulator, you can right-click to see the available functions of the emulator. To step, press the backslash (`\`) key.

To use a custom configuration Python script, run `python main.py <module-name>` (or `python3 main.py <module-name>`).
`<module-name>` is the name of the Python script in module name form; for example if your configuration file is in `configs/config_main.py`, then `<module-name>` will be `configs.config_main`.
