#!/usr/bin/env python3
"""Check firmware load layout and optionally execute its actual RAM boot stub.

Requires pyelftools; --emulate also requires Unicorn. This checks the ELF image,
not board cold boot, flash-chip setup, or peripheral behavior.
"""

import argparse
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile

FLASH = (0x10000000, 0x11000000)
RAM = (0x20000000, 0x2003C000)
STACK = (0x2003C000, 0x20040000)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inside(address, length, region):
    return region[0] <= address and address + length <= region[1]


def interval(section):
    return section["sh_addr"], section["sh_addr"] + section["sh_size"]


def nonoverlapping(ranges, description):
    ordered = sorted((start, end, name) for name, start, end in ranges if start < end)
    for previous, current in zip(ordered, ordered[1:]):
        require(previous[1] <= current[0],
                f"{description}: {previous[2]} overlaps {current[2]}")


def boot_crc(data):
    """RP2040 bootrom uses CRC-32/MPEG-2 over the first 252 bytes."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
    return crc


def load_address(elf, section):
    """Find physical Flash address, independently of the section's RAM VMA."""
    for segment in elf.iter_segments():
        if segment["p_type"] != "PT_LOAD":
            continue
        offset = section["sh_offset"] - segment["p_offset"]
        if 0 <= offset and offset + section["sh_size"] <= segment["p_filesz"]:
            return segment["p_paddr"] + offset
    raise ValueError(f"{section.name} has no file-backed load segment")


def check(elf, mode):
    sections = {section.name: section for section in elf.iter_sections()}
    symbols = {
        symbol.name: symbol["st_value"]
        for symbol in elf.get_section_by_name(".symtab").iter_symbols()
    }
    require(not any("__rust_alloc" in name or "__rdl_alloc" in name for name in symbols),
            "allocation-free firmware unexpectedly links a heap allocator")
    boot2 = sections[".boot2"]
    require(boot2["sh_addr"] == FLASH[0] and boot2["sh_size"] == 256,
            "boot2 must occupy exactly the first 256 Flash bytes")
    require(load_address(elf, boot2) == FLASH[0], "boot2 has an incorrect Flash load address")
    boot_data = boot2.data()
    require(boot_crc(boot_data[:252]) == struct.unpack("<I", boot_data[252:])[0],
            "boot2 CRC would be rejected by RP2040 bootrom")
    require(symbols["_stack_start"] == STACK[1], "incorrect core0 stack top")
    require(symbols["_stack_end"] == STACK[0], "16 KiB core0 stack not reserved")
    require(inside(symbols["__euninit"], 0, RAM), "static RAM exceeds stack boundary")
    for name in (".data", ".bss", ".uninit"):
        section = sections.get(name)
        if section is None:
            continue
        require(inside(section["sh_addr"], section["sh_size"], RAM),
                f"{name} overlaps stack or leaves SRAM")
        require(not section["sh_flags"] & 4, f"{name} must not be executable")
    for name, start, end in ((".data", "__sdata", "__edata"),
                             (".bss", "__sbss", "__ebss")):
        section = sections.get(name)
        if section is None:
            require(symbols[start] == symbols[end], f"missing initialized section {name}")
            continue
        require((symbols[start], symbols[end]) == interval(section),
                f"{name} initialization symbols disagree with its bounds")
        if name == ".data" and section["sh_size"]:
            address = load_address(elf, section)
            require(inside(address, section["sh_size"], FLASH), ".data load image leaves Flash")
            require(symbols["__sidata"] == address, "incorrect initialized data load address")
    rodata = sections[".rodata"]
    require(inside(rodata["sh_addr"], rodata["sh_size"], FLASH),
            "readonly media must remain in Flash")
    vectors, text = sections[".vector_table"], sections[".text"]
    require(vectors["sh_size"] == 48 * 4, "RP2040 requires exactly 48 runtime vectors")
    require(text["sh_flags"] & 6 == 6, ".text must be allocated executable code")
    require(symbols["__vector_table"] == vectors["sh_addr"], "incorrect vector table symbol")
    expected_region = RAM if mode == "ram" else FLASH
    for section in (vectors, text):
        require(inside(section["sh_addr"], section["sh_size"], expected_region),
                f"{section.name} is outside expected {mode} region")
        require(inside(load_address(elf, section), section["sh_size"], FLASH),
                f"{section.name} load image is outside Flash")
    require(vectors["sh_addr"] % 256 == 0, "unaligned RP2040 vector table")
    words = struct.unpack("<48I", vectors.data())
    require(words[0] == STACK[1], "vector SP differs from reserved stack")
    require(words[1] == symbols["Reset"] and words[1] & 1, "invalid Reset vector")
    for index, address in enumerate(words[1:], 1):
        require(address == 0 or (address & 1 and inside(address & ~1, 2, interval(text))),
                f"vector {index} does not point to executable {mode} memory")
    # RP2040 IRQ numbers, independently checked against the rp-pac interrupt enum.
    handlers = {"TIMER_IRQ_0": 0, "USBCTRL_IRQ": 5, "PIO0_IRQ_0": 7,
                "DMA_IRQ_0": 11, "DMA_IRQ_1": 12, "SWI_IRQ_0": 26}
    for name, irq in handlers.items():
        require(name in symbols and words[16 + irq] == symbols[name],
                f"{name} is missing from its runtime vector")
        require(words[16 + irq] != symbols["DefaultHandler"],
                f"{name} unexpectedly resolves to DefaultHandler")
    if mode == "ram":
        bootstrap = sections[".boot_vectors"]
        require(bootstrap["sh_addr"] == 0x10000100, "boot2 would enter incorrect vectors")
        require(bootstrap["sh_size"] == 48 * 4, "incorrect bootstrap vector count")
        ram_boot = sections[".ram_boot"]
        for name in ("RamBoot", "RamBootFault"):
            require(symbols[name] & 1 and inside(symbols[name] & ~1, 2, interval(ram_boot)),
                    f"{name} is not a Thumb bootstrap entry")
        boot_words = struct.unpack("<48I", bootstrap.data())
        require(boot_words[:2] == (STACK[1], symbols["RamBoot"]), "invalid Flash boot vectors")
        require(all(word == symbols["RamBootFault"] for word in boot_words[2:]),
                "bootstrap exceptions lack a safe Flash handler")
        require(elf.header["e_entry"] == symbols["RamBoot"], "ELF entry bypasses relocation")
        for name, boundary in (("__sivector", vectors), ("__sitext", text)):
            require(symbols[name] == load_address(elf, boundary), f"incorrect {name}")
        require(symbols["__evector"] == vectors["sh_addr"] + vectors["sh_size"],
                "incorrect vector copy end")
        require(symbols["__stext"] == text["sh_addr"], "incorrect text copy start")
        require(symbols["__etext"] == text["sh_addr"] + text["sh_size"],
                "incorrect text copy end")
        allowed_flash_code = {".ram_boot", ".boot2"}
        for section in sections.values():
            if section["sh_flags"] & 6 == 6 and section["sh_size"]:
                region = FLASH if section.name in allowed_flash_code else RAM
                require(inside(section["sh_addr"], section["sh_size"], region),
                        f"unexpected executable section {section.name}")
    ram_ranges = []
    flash_ranges = []
    for section in sections.values():
        if not section["sh_flags"] & 2 or not section["sh_size"]:
            continue
        if inside(section["sh_addr"], section["sh_size"], RAM):
            ram_ranges.append((section.name, *interval(section)))
        if section["sh_type"] != "SHT_NOBITS":
            address = load_address(elf, section)
            require(inside(address, section["sh_size"], FLASH),
                    f"{section.name} has a non-Flash load image")
            flash_ranges.append((section.name, address, address + section["sh_size"]))
    nonoverlapping(ram_ranges, "SRAM sections")
    nonoverlapping(flash_ranges, "Flash load images")
    static_bytes = symbols["__euninit"] - RAM[0]
    print(f"{mode}: code {text['sh_size']} B; readonly Flash {rodata['sh_size']} B; "
          f"static SRAM {static_bytes} B; core0 stack {STACK[1] - STACK[0]} B; "
          f"SRAM headroom {STACK[0] - symbols['__euninit']} B")
    return sections, symbols


def emulate(elf, sections, symbols):
    from unicorn import Uc, UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MODE_MCLASS, UC_MODE_THUMB
    from unicorn.arm_const import UC_ARM_REG_MSP, UC_ARM_REG_PRIMASK

    machine = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    machine.mem_map(FLASH[0], FLASH[1] - FLASH[0])
    machine.mem_map(RAM[0], STACK[1] - RAM[0])
    machine.mem_map(0xE000E000, 0x1000)
    # Embassy pre-init writes PSM force-on/off and reads the same register back.
    # Plain mapped memory models that readback only, not actual reset hardware.
    machine.mem_map(0x40010000, 0x1000)
    machine.mem_write(RAM[0], bytes([0xA5]) * (STACK[1] - RAM[0]))
    for segment in elf.iter_segments():
        if segment["p_type"] == "PT_LOAD" and segment["p_filesz"]:
            require(inside(segment["p_paddr"], segment["p_filesz"], FLASH),
                    "file-backed program segment must have a Flash load address")
            machine.mem_write(segment["p_paddr"], segment.data())
    machine.reg_write(UC_ARM_REG_MSP, STACK[1])
    reached_reset = False
    reached_main = False
    preinit_writes = set()
    copied = [sections[".vector_table"], sections[".text"]]

    def instruction_hook(cpu, address, size, user_data):
        nonlocal reached_reset, reached_main
        if address == symbols["Reset"] & ~1:
            reached_reset = True
        if reached_reset and address == symbols["main"] & ~1:
            reached_main = True
            cpu.emu_stop()
        elif not reached_reset:
            require(inside(address, size, FLASH), "executed RAM before entering Reset")
        else:
            require(inside(address, size, RAM), "normal Reset left copied executable SRAM")

    def write_hook(cpu, access, address, size, value, user_data):
        allowed = address == 0xE000ED08 and size == 4
        allowed |= any(inside(address, size, (s["sh_addr"], s["sh_addr"] + s["sh_size"]))
                       for s in copied)
        if reached_reset:
            allowed |= inside(address, size, STACK)
            for name in (".data", ".bss"):
                section = sections.get(name)
                if section is not None:
                    allowed |= inside(address, size,
                                      (section["sh_addr"], section["sh_addr"] + section["sh_size"]))
            if address in (0x40010000, 0x40010004) and size == 4:
                preinit_writes.add(address)
                allowed = True
        require(allowed, f"bootstrap overwrote unrelated memory at {address:#x}")

    machine.hook_add(UC_HOOK_CODE, instruction_hook)
    machine.hook_add(UC_HOOK_MEM_WRITE, write_hook)
    machine.emu_start(symbols["RamBoot"], 0, count=2_000_000)
    require(reached_reset, "bootstrap never reached normal Reset")
    require(reached_main, "normal Reset never reached main")
    for section in copied:
        actual = bytes(machine.mem_read(section["sh_addr"], section["sh_size"]))
        require(actual == section.data(), f"actual bootstrap failed to copy {section.name}")
    require(machine.reg_read(UC_ARM_REG_MSP) == STACK[1], "bootstrap loaded incorrect MSP")
    require(machine.reg_read(UC_ARM_REG_PRIMASK) == 0, "bootstrap left interrupts masked")
    vtor = struct.unpack("<I", machine.mem_read(0xE000ED08, 4))[0]
    require(vtor == symbols["__vector_table"], "bootstrap did not relocate VTOR")
    data = sections.get(".data")
    if data is not None:
        require(bytes(machine.mem_read(data["sh_addr"], data["sh_size"])) == data.data(),
                "normal Reset failed initialized data copy")
    bss = sections.get(".bss")
    if bss is not None:
        require(bytes(machine.mem_read(bss["sh_addr"], bss["sh_size"])) == bytes(bss["sh_size"]),
                "normal Reset failed BSS initialization")
    require(preinit_writes == {0x40010000, 0x40010004}, "Embassy reset pre-init did not run")
    print("Actual Cortex-M0+ Thumb boot through main passed: code/vector copy, write bounds, "
          "VTOR, MSP, Embassy pre-init, data/BSS. PSM readback is modeled; hardware is untested.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("--expect", required=True, choices=("ram", "xip"))
    parser.add_argument("--emulate", action="store_true")
    args = parser.parse_args()
    require(not args.emulate or args.expect == "ram", "emulation applies to RAM boot only")
    with args.elf.open("rb") as source:
        elf = ELFFile(source)
        require(elf.elfclass == 32 and elf.little_endian, "expected little-endian ARM ELF32")
        sections, symbols = check(elf, args.expect)
        if args.emulate:
            emulate(elf, sections, symbols)


if __name__ == "__main__":
    main()
