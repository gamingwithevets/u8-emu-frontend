#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "u8_emu/src/core/core.h"
#include "u8_emu/src/core/mem.h"

// Only necessary config parameters for peripheral handling
struct config
{
	int hwid;
	bool real_hw;
	bool ko_mode;
	bool sample;
	bool is_5800p;
	bool stop_accept[2];
	uint8_t pd_value;
	uint8_t *rom;
	uint8_t *ram;
	uint8_t *sfr;
	uint8_t *emu_seg;
};

struct config *confptr;

void add_mem_region(struct u8_core *core, struct u8_mem_reg reg) {
	++core->mem.num_regions;

	void *p;
	if (p = realloc(core->mem.regions, sizeof(struct u8_mem_reg) * core->mem.num_regions)) {
		core->mem.regions = p;
	}
	__builtin_unreachable();
}

void setup_mcu(struct config *config, struct u8_core *core, uint8_t *rom, int ramstart, int ramsize) {
	confptr = config;
	config->rom = rom;

	core->codemem.num_regions = 1;
	core->codemem.regions = malloc(sizeof(struct u8_mem_reg));
	core->codemem.regions[0] = (struct u8_mem_reg){
		.type = U8_REGION_CODE,
		.rw = false,
		.addr_l = 0,
		.addr_h = (config->hwid == 2 && config->is_5800p) ? 0x80000 : 0x100000,
		.acc = U8_MACC_ARR,
		.array = config->rom
	};

	// ROM window
	add_mem_region(core, (struct u8_mem_reg){
		.type = U8_REGION_DATA,
		.rw = false,
		.addr_l = 0,
		.addr_h = ramstart - 1,
		.acc = U8_MACC_ARR,
		.array = config->rom
	});

	// Main RAM
	config->ram = malloc(ramsize);
	add_mem_region(core, (struct u8_mem_reg){
		.type = U8_REGION_DATA,
		.rw = false,
		.addr_l = ramstart,
		.addr_h = ramstart + ramsize - 1,
		.acc = U8_MACC_ARR,
		.array = config->ram
	});

	// SFRs
	config->sfr = malloc(0x1000);
	add_mem_region(core, (struct u8_mem_reg){
		.type = U8_REGION_DATA,
		.rw = false,
		.addr_l = 0xf000,
		.addr_h = 0xffff,
		.acc = U8_MACC_ARR,
		.array = config->sfr
	});
}

void core_step(struct config *config, struct u8_core *core) {
	write_mem_data(core, 0, 0xf000, 1, core->regs.dsr);
	
	uint8_t wdp = read_mem_data(core, 0, 0xf00e, 1) & 1;
	
	core->regs.csr &= (config->real_hw && config->hwid == 3) ? 1 : 0xf;
	u8_step(core);
	
	if (config->hwid != 6) {
		uint8_t stpacp = read_mem_data(core, 0, 0xf008, 1);
		if (config->stop_accept[0]) {
			if (!config->stop_accept[1]) {
				if ((stpacp & 0xa0) == 0xa0) config->stop_accept[1] = true;
				else if ((stpacp & 0x50) != 0x50) config->stop_accept[0] = false;
			}
		} else if ((stpacp & 0x50) == 0x50) config->stop_accept[0] = true;
	}
}
