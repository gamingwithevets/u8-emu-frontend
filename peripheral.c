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
	uint8_t *flash;
	uint8_t *ram;
	uint8_t *sfr;
	uint8_t *emu_seg;
	uint8_t (*sfr_write[0x1000])(uint16_t, uint8_t);
};

struct config *confptr;

void add_mem_region(struct u8_core *core, struct u8_mem_reg reg) {
	++core->mem.num_regions;

	void *p;
	if (p = realloc(core->mem.regions, sizeof(struct u8_mem_reg) * core->mem.num_regions)) {
		core->mem.regions = p;
		core->mem.regions[core->mem.num_regions-1] = reg;
	} else {
		__builtin_unreachable();
	}
}

uint8_t read_sfr(struct u8_core *core, uint8_t seg, uint16_t addr) {
	return confptr->sfr[addr];
}

void write_sfr(struct u8_core *core, uint8_t seg, uint16_t addr, uint8_t val) {
	uint8_t (*funcptr)(uint16_t, uint8_t);
	if (funcptr = confptr->sfr_write[addr]) confptr->sfr[addr] = funcptr(addr, val);
}

uint8_t battery(struct u8_core *core, uint8_t seg, uint16_t addr) {
	return 0xff;
}

void setup_mcu(struct config *config, struct u8_core *core, uint8_t *rom, uint8_t *flash, int ramstart, int ramsize) {
	confptr = config;
	config->rom = rom;
	config->flash = flash;

	// ROM
	core->codemem.num_regions = (config->hwid == 2 && config->is_5800p) ? 2 : 1;
	core->codemem.regions = malloc(sizeof(struct u8_mem_reg) * core->codemem.num_regions);
	core->codemem.regions[0] = (struct u8_mem_reg){
		.type = U8_REGION_CODE,
		.rw = false,
		.addr_l = 0,
		.addr_h = (config->hwid == 2 && config->is_5800p) ? 0x7ffff : 0xfffff,
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
		.rw = true,
		.addr_l = ramstart,
		.addr_h = ramstart + ramsize - 1,
		.acc = U8_MACC_ARR,
		.array = config->ram
	});

	// SFRs
	config->sfr = malloc(0x1000);
	add_mem_region(core, (struct u8_mem_reg){
		.type = U8_REGION_DATA,
		.rw = true,
		.addr_l = 0xf000,
		.addr_h = 0xffff,
		.acc = U8_MACC_FUNC,
		.read = &read_sfr,
		.write = &write_sfr
	});

	switch (config->hwid) {
		// ClassWiz
		case 4:
		case 5:
			// Code segment 1+ mirror
			add_mem_region(core, (struct u8_mem_reg){
				.type = U8_REGION_DATA,
				.rw = false,
				.addr_l = 0x10000,
				.addr_h = config->hwid == 5 ? 0x7ffff : 0x3ffff,
				.acc = U8_MACC_ARR,
				.array = (uint8_t *)(config->rom + 0x10000)
			});


			if (config->real_hw) {
				// Code segment 0 mirror
				add_mem_region(core, (struct u8_mem_reg){
					.type = U8_REGION_DATA,
					.rw = false,
					.addr_l = config->hwid == 5 ? 0x80000 : 0x50000,
					.addr_h = config->hwid == 5 ? 0x8ffff : 0x5ffff,
					.acc = U8_MACC_ARR,
					.array = config->rom
				});

				core->u16_mode = true;

			} else {
				// Segment 4/8 [emulator]
				config->emu_seg = malloc(0x10000);
				add_mem_region(core, (struct u8_mem_reg){
					.type = U8_REGION_DATA,
					.rw = false,
					.addr_l = config->hwid == 5 ? 0x80000 : 0x40000,
					.addr_h = config->hwid == 5 ? 0x8ffff : 0x4ffff,
					.acc = U8_MACC_ARR,
					.array = config->emu_seg
				});
			}

			break;

		// TI MathPrint - LAPIS ML620418A
		case 6:
			// Code segment 1+ mirror
			add_mem_region(core, (struct u8_mem_reg){
				.type = U8_REGION_DATA,
				.rw = false,
				.addr_l = 0x10000,
				.addr_h = 0x3ffff,
				.acc = U8_MACC_ARR,
				.array = (uint8_t *)(config->rom + 0x10000)
			});

			// Code segment 0+ mirror 2
			add_mem_region(core, (struct u8_mem_reg){
				.type = U8_REGION_DATA,
				.rw = false,
				.addr_l = 0x80000,
				.addr_h = 0xaffff,
				.acc = U8_MACC_ARR,
				.array = config->rom
			});

			break;

		// SOLAR II
		case 0:
			core->small_mm = true;
			break;

		// ES, ES PLUS
		default:
			// Code segment 1 mirror
			add_mem_region(core, (struct u8_mem_reg){
				.type = U8_REGION_DATA,
				.rw = false,
				.addr_l = 0x10000,
				.addr_h = 0x1ffff,
				.acc = U8_MACC_ARR,
				.array = (uint8_t *)(config->rom + 0x10000)
			});

			if (!config->ko_mode) {
				// Code segment 8 mirror
				add_mem_region(core, (struct u8_mem_reg){
					.type = U8_REGION_DATA,
					.rw = false,
					.addr_l = 0x80000,
					.addr_h = 0x8ffff,
					.acc = U8_MACC_ARR,
					.array = config->rom
				});
			}

			// fx-5800P stuff
			if (config->hwid == 2 && config->is_5800p) {
				// Flash
				core->codemem.regions[1] = (struct u8_mem_reg){
					.type = U8_REGION_CODE,
					.rw = false,
					.addr_l = 0x80000,
					.addr_h = 0xfffff,
					.acc = U8_MACC_ARR,
					.array = config->flash
				};

				// Flash but data
				add_mem_region(core, (struct u8_mem_reg){
					.type = U8_REGION_DATA,
					.rw = false,
					.addr_l = 0x80000,
					.addr_h = 0xfffff,
					.acc = U8_MACC_ARR,
					.array = config->flash
				});

				// Flash RAM
				add_mem_region(core, (struct u8_mem_reg){
					.type = U8_REGION_DATA,
					.rw = true,
					.addr_l = 0x40000,
					.addr_h = 0x47fff,
					.acc = U8_MACC_ARR,
					.array = (uint8_t *)(config->flash + 0x20000)
				});

				// Fake battery
				add_mem_region(core, (struct u8_mem_reg){
					.type = U8_REGION_DATA,
					.rw = false,
					.addr_l = 0x100000,
					.addr_h = 0x100000,
					.acc = U8_MACC_FUNC,
					.read = &battery
				});
			}

			break;
	}

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
