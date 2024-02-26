#include <stdio.h>
#include <string.h>

#include "u8_emu/src/core/core.h"
#include "u8_emu/src/core/mem.h"

bool stop_accept[2];

void core_step(struct u8_core *core, bool real_hw, int hwid) {
	write_mem_data(core, 0, 0xf000, 1, core->regs.dsr);
	
	uint8_t wdp = read_mem_data(core, 0, 0xf00e, 1) & 1;
	
	u8_step(core);
	
	core->regs.csr %= (real_hw && hwid == 3) ? 2 : 0x10;
	if (hwid != 6) {
		uint8_t stpacp = read_mem_data(core, 0, 0xf008, 1);
		if (stop_accept[0]) {
			if (!stop_accept[1]) {
				if ((stpacp & 0xa0) == 0xa0)
					stop_accept[1] = true;
				else if ((stpacp & 0x50) != 0x50)
					stop_accept[0] = false;
			}
		} else if ((stpacp & 0x50) == 0x50)
			stop_accept[0] = true;
	}
}

void read_emu_kb(struct u8_core *core, int idx, int hwid, bool sample) {
	uint8_t seg = 0;
	uint16_t addr;

	if (hwid == 0) addr = 0xe800 + idx;
	else if (hwid == 4) return read_mem_data(core, 4, 0x8e00 + idx);
	else if (hwid == 5) {
		if (sample) {
			switch (idx) {
				case 0: return read_mem_data(core, 8, 0x8e07);
				case 1: return read_mem_data(core, 8, 0x8e05);
				case 2: return read_mem_data(core, 8, 0x8e08);
			}
		} else return read_mem_data(core, 8, 0x8e00 + idx);
	}
	return read_mem_data(core, 0, 0x8e00 + idx);
}

void write_emu_kb(struct u8_core *core, int idx, uint8_t val, int hwid, bool sample) {
	if (hwid == 0) write_mem_data(core, 0, 0xe800 + idx, val);
	else if (hwid == 4) write_mem_data(core, 4, 0x8e00 + idx, val);
	else if (hwid == 5) {
		if (sample) {
			switch (idx) {
				case 0: write_mem_data(core, 8, 0x8e07, val); break;
				case 1: write_mem_data(core, 8, 0x8e05, val); break;
				case 2: write_mem_data(core, 8, 0x8e08, val); break;
			}
		} else return write_mem_data(core, 8, 0x8e00 + idx);
	}
	write_mem_data(core, 0, 0x8e00 + idx, val);
}
