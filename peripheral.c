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
	uint8_t pd_value;
	uint8_t *rom;
	uint8_t *flash;
	uint8_t *ram;
	uint8_t *sfr;
	uint8_t *emu_seg;
	uint8_t (*sfr_write[0x1000])(uint16_t, uint8_t);
	int flash_mode;
};

struct config *confptr;

void add_mem_region(struct u8_core *core, struct u8_mem_reg reg) {
	++core->mem.num_regions;

	void *p;
	if (p = realloc(core->mem.regions, sizeof(struct u8_mem_reg) * core->mem.num_regions)) {
		core->mem.regions = p;
		core->mem.regions[core->mem.num_regions-1] = reg;
	} else __builtin_unreachable();
}

uint8_t read_sfr(struct u8_core *core, uint8_t seg, uint16_t addr) {
	return confptr->sfr[addr];
}

void write_sfr(struct u8_core *core, uint8_t seg, uint16_t addr, uint8_t val) {
	if (confptr->sfr_write[addr]) confptr->sfr[addr] = confptr->sfr_write[addr](addr, val);
}

uint8_t battery(struct u8_core *core, uint8_t seg, uint16_t addr) {
	return 0xff;
}

uint8_t read_flash(struct u8_core *core, uint8_t seg, uint16_t offset) {
	uint32_t fo = ((seg << 16) + offset) & 0x7ffff;
	if (confptr->flash_mode == 6) {
		confptr->flash_mode = 0;
		return 0x80;
	}
	return confptr->flash[fo];
}

void write_flash(struct u8_core *core, uint8_t seg, uint16_t offset, uint8_t data) {
	uint32_t fo = ((seg << 16) + offset) & 0x7ffff;
	switch (confptr->flash_mode) {
		case 0:
			if (fo == 0xaaa && data == 0xaa) {
				confptr->flash_mode = 1;
				return;
			}
			break;
		case 1:
			if (fo == 0x555 && data == 0x55) {
				confptr->flash_mode = 2;
				return;
			}
			break;
		case 2:
			if (fo == 0xAAA && data == 0xA0) {
				confptr->flash_mode = 3;
				return;
			}
			if (fo == 0xaaa && data == 0x80) {
				confptr->flash_mode = 4;
				return;
			}
			break;
		case 3:
			printf("%05X = %02x\n", fo + 0x80000, data);
			confptr->flash[fo] = data;
			confptr->flash_mode = 0;
			return;
		case 4:
			if (fo == 0xAAA && data == 0xaa) {
				confptr->flash_mode = 5;
				return;
			}
			break;
		case 5:
			if (fo == 0x555 && data == 0x55) {
				confptr->flash_mode = 6;
				return;
			}
			break;
		case 6: // we dont know sector's mapping(?)
			if (fo == 0)
				memset(&confptr->flash[fo], 0xff, 0x7fff);
			if (fo == 0x20000 || fo == 0x30000)
				memset(&confptr->flash[fo], 0xff, 0xffff);
			printf("erase %05X (%02x)\n", fo+0x80000, data);
			return;
		case 7:
			if (fo == 0xaaa && data == 0xaa) {
				confptr->flash_mode = 1;
				return;
			}
			break;
	}
	if (data == 0xf0) {
		//printf("write_flash: reset mode\n");
		confptr->flash_mode = 0;
		return;
	}
	//if (data == 0xb0) {
	//	printf("Erase Suspend.\n");
	//	return;
	//}
	//if (data == 0x30) {
	//	printf("Erase Suspend.\n");
	//	return;
	//}
	printf("write_flash: unknown JEDEC %05x = %02x\n", (int)fo, data);
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
	memset(config->ram, 0, ramsize);
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
	memset(config->sfr, 0, 0x1000);
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
		case 4:  // LAPIS ML620606
		case 5:  // LAPIS ML620609
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
				memset(config->emu_seg, 0, 0x10000);
				add_mem_region(core, (struct u8_mem_reg){
					.type = U8_REGION_DATA,
					.rw = true,
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

			// fx-5800P
			if (config->hwid == 2 && config->is_5800p) {
				// Flash (code)
				core->codemem.regions[1] = (struct u8_mem_reg){
					.type = U8_REGION_CODE,
					.rw = false,
					.addr_l = 0x80000,
					.addr_h = 0xfffff,
					.acc = U8_MACC_ARR,
					.array = config->flash
				};

				// Flash (data)
				add_mem_region(core, (struct u8_mem_reg){
					.type = U8_REGION_DATA,
					.rw = true,
					.addr_l = 0x80000,
					.addr_h = 0xfffff,
					.acc = U8_MACC_FUNC,
					.read = &read_flash,
					.write = &write_flash
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
}
