#include <stdio.h>
#include <string.h>

#include "u8_emu/src/core/core.h"
#include "u8_emu/src/core/mem.h"

bool stop_accept[2];

// Only necessary config parameters for peripheral handling
struct peripheral
{
	int hwid;
	bool real_hw;
	bool sample;
	bool is_5800p;
	uint8_t pd_value;
};

void core_step(struct u8_core *core, bool real_hw, int hwid) {
	write_mem_data(core, 0, 0xf000, 1, core->regs.dsr);
	
	uint8_t wdp = read_mem_data(core, 0, 0xf00e, 1) & 1;
	
	core->regs.csr &= (real_hw && hwid == 3) ? 1 : 0xf;
	u8_step(core);
	
	if (hwid != 6) {
		uint8_t stpacp = read_mem_data(core, 0, 0xf008, 1);
		if (stop_accept[0]) {
			if (!stop_accept[1]) {
				if ((stpacp & 0xa0) == 0xa0) stop_accept[1] = true;
				else if ((stpacp & 0x50) != 0x50) stop_accept[0] = false;
			}
		} else if ((stpacp & 0x50) == 0x50) stop_accept[0] = true;
	}
}
