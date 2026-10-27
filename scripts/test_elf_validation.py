#!/usr/bin/env python3
"""Prove the ELF validator rejects mutations of a real RAM firmware image.

All mutations use private in-memory copies. The supplied ELF remains unchanged.
Requires tools/requirements-validation.txt; does not build or contact hardware.
"""

import argparse
import contextlib
import io
import struct
import unittest
from pathlib import Path

from elftools.elf.elffile import ELFFile

import check_elf


class FirmwareValidationTests(unittest.TestCase):
    source: Path
    original: bytes

    @classmethod
    def setUpClass(cls):
        cls.original = cls.source.read_bytes()
        # Every negative case must start from an accepted, complete firmware ELF.
        with contextlib.redirect_stdout(io.StringIO()):
            check_elf.check(ELFFile(io.BytesIO(cls.original)), "ram")

    def section_word(self, name, relative_offset, value):
        elf = ELFFile(io.BytesIO(self.original))
        section = elf.get_section_by_name(name)
        self.assertIsNotNone(section, name)
        self.assertLessEqual(relative_offset + 4, section["sh_size"])
        result = bytearray(self.original)
        struct.pack_into("<I", result, section["sh_offset"] + relative_offset, value)
        return bytes(result)

    def symbol_value(self, name, value):
        elf = ELFFile(io.BytesIO(self.original))
        self.assertEqual(elf.elfclass, 32)
        self.assertTrue(elf.little_endian)
        table = elf.get_section_by_name(".symtab")
        self.assertEqual(table["sh_entsize"], 16)
        for index, symbol in enumerate(table.iter_symbols()):
            if symbol.name == name:
                result = bytearray(self.original)
                # ELF32 symbols begin with 4-byte st_name, then 4-byte st_value.
                offset = table["sh_offset"] + index * table["sh_entsize"] + 4
                struct.pack_into("<I", result, offset, value)
                return bytes(result)
        self.fail(f"required symbol absent: {name}")

    def reject(self, data, message):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, message):
                check_elf.check(ELFFile(io.BytesIO(data)), "ram")

    def test_bootrom_rejects_corrupted_boot2_crc(self):
        elf = ELFFile(io.BytesIO(self.original))
        offset = elf.get_section_by_name(".boot2")["sh_offset"]
        result = bytearray(self.original)
        result[offset] ^= 1
        self.reject(bytes(result), "boot2 CRC")

    def test_thumb_irq_pointer_into_bss_is_not_executable(self):
        elf = ELFFile(io.BytesIO(self.original))
        bss = elf.get_section_by_name(".bss")
        self.assertGreaterEqual(bss["sh_size"], 2)
        # DMA_IRQ_0 occupies vector 16 + 11 on RP2040. Keep its Thumb bit set.
        result = self.section_word(".vector_table", (16 + 11) * 4, bss["sh_addr"] | 1)
        self.reject(result, "vector 27 does not point to executable ram memory")

    def test_reset_requires_thumb_entry(self):
        elf = ELFFile(io.BytesIO(self.original))
        vectors = elf.get_section_by_name(".vector_table").data()
        reset = struct.unpack_from("<I", vectors, 4)[0]
        self.assertEqual(reset & 1, 1)
        self.reject(self.section_word(".vector_table", 4, reset & ~1), "invalid Reset vector")

    def test_initialized_data_load_symbol_must_match_flash_image(self):
        elf = ELFFile(io.BytesIO(self.original))
        data = elf.get_section_by_name(".data")
        self.assertGreater(data["sh_size"], 0)
        incorrect = check_elf.load_address(elf, data) + 4
        self.reject(self.symbol_value("__sidata", incorrect), "initialized data load address")

    def test_actual_bootstrap_rejects_missing_sram_store(self):
        elf = ELFFile(io.BytesIO(self.original))
        boot = elf.get_section_by_name(".ram_boot")
        # Locate the actual Thumb LDM r2!,{r3}; STM r0!,{r3} copy loop, not a
        # source-model equivalent. NOP'ing STM removes both its write and R0 advance.
        sequence = bytes.fromhex("08ca08c0")
        relative = boot.data().find(sequence)
        self.assertGreaterEqual(relative, 0, "bootstrap copy instruction sequence changed")
        result = bytearray(self.original)
        offset = boot["sh_offset"] + relative + 2
        result[offset:offset + 2] = bytes.fromhex("00bf")
        broken = ELFFile(io.BytesIO(result))
        with contextlib.redirect_stdout(io.StringIO()):
            # Metadata still passes; actual instruction execution must detect the fault.
            sections, symbols = check_elf.check(broken, "ram")
            with self.assertRaisesRegex(ValueError, "bootstrap never reached normal Reset"):
                check_elf.emulate(broken, sections, symbols)

    @classmethod
    def tearDownClass(cls):
        if cls.source.read_bytes() != cls.original:
            raise AssertionError("source ELF changed during in-memory mutation tests")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path, help="complete, non-profiling RAM firmware ELF")
    args = parser.parse_args()
    FirmwareValidationTests.source = args.elf
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FirmwareValidationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
