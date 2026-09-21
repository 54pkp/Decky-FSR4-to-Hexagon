from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from tests.abi.fixtures import elf32, elf64, pe64


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "abi" / "inspector.py"

spec = importlib.util.spec_from_file_location("abi_inspector", TOOL)
inspector = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(inspector)


class InspectorTests(unittest.TestCase):
    def _write(self, directory: str, name: str, payload: bytes) -> Path:
        path = Path(directory) / name
        path.write_bytes(payload)
        return path

    def _run(self, path: Path, *arguments: str):
        return subprocess.run(
            [sys.executable, str(TOOL), str(path), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_pe_reports_windows_machine_bitness_and_unknown_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "sdk-9.99-arm64.dll", pe64())
            report = inspector.inspect_file(path)
        self.assertEqual("PE", report["format"])
        self.assertEqual("x86_64", report["machine"])
        self.assertEqual(64, report["bitness"])
        self.assertEqual("windows_pe", report["candidate"])
        self.assertEqual("unknown", report["sdk_version"])
        self.assertIn("does not load or execute", report["scope"])

        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "arm64.dll", pe64(machine=0xAA64))
            arm64_report = inspector.inspect_file(path)
        self.assertEqual("arm64", arm64_report["machine"])
        self.assertEqual("windows_pe", arm64_report["candidate"])

    def test_linux_elf_reports_interpreter_dependencies_and_glibc_requirements(self):
        payload = elf64(
            interpreter="/lib/ld-linux-aarch64.so.1",
            needed=("libc.so.6", "libm.so.6"),
            glibc_versions=("GLIBC_2.17", "GLIBC_2.34"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "libsample.so", payload)
            report = inspector.inspect_file(path, "2.50.0", "arm64")
        self.assertEqual("ELF", report["format"])
        self.assertEqual("arm64", report["machine"])
        self.assertEqual(64, report["bitness"])
        self.assertEqual("little", report["endianness"])
        self.assertEqual("linux_glibc_candidate", report["candidate"])
        self.assertEqual(["libc.so.6", "libm.so.6"], report["needed"])
        self.assertEqual(["GLIBC_2.17", "GLIBC_2.34"], report["glibc_versions"])
        self.assertEqual("2.50.0", report["sdk_version"])

    def test_elf_class_and_data_select_layouts_and_parse_dynamic_evidence(self):
        variants = (
            (
                "elf32-le",
                elf32,
                {"machine": 3, "endianness": "little"},
                "x86",
                32,
                "/lib/ld-linux.so.2",
            ),
            (
                "elf32-be",
                elf32,
                {"machine": 40, "endianness": "big"},
                "arm",
                32,
                "/lib/ld-linux-armhf.so.3",
            ),
            (
                "elf64-le",
                elf64,
                {"machine": 62, "endianness": "little"},
                "x86_64",
                64,
                "/lib64/ld-linux-x86-64.so.2",
            ),
            (
                "elf64-be",
                elf64,
                {"machine": 183, "endianness": "big"},
                "arm64",
                64,
                "/lib/ld-linux-aarch64.so.1",
            ),
        )
        for name, builder, builder_args, machine, bitness, interpreter in variants:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                payload = builder(
                    **builder_args,
                    interpreter=interpreter,
                    needed=("libc.so.6", "libm.so.6"),
                    glibc_versions=("GLIBC_2.17", "GLIBC_2.34"),
                )
                path = self._write(directory, name + ".so", payload)
                report = inspector.inspect_file(path)
            self.assertEqual("ELF", report["format"])
            self.assertEqual(machine, report["machine"])
            self.assertEqual(bitness, report["bitness"])
            self.assertEqual(builder_args["endianness"], report["endianness"])
            self.assertEqual(interpreter, report["interpreter"])
            self.assertEqual(["libc.so.6", "libm.so.6"], report["needed"])
            self.assertEqual(["GLIBC_2.17", "GLIBC_2.34"], report["glibc_versions"])
            self.assertEqual("linux_glibc_candidate", report["candidate"])
            self.assertIn(
                f"glibc-style dynamic linker: {interpreter}",
                report["classification_evidence"],
            )
            self.assertIn(
                "GNU version requirements include GLIBC_* symbols",
                report["classification_evidence"],
            )

    def test_mismatched_elf_class_and_data_declarations_are_rejected(self):
        wrong_class = bytearray(elf32(machine=40, endianness="big"))
        wrong_class[4] = 2
        wrong_data = bytearray(elf64(machine=183, endianness="big"))
        wrong_data[5] = 1

        for name, payload, message in (
            ("wrong-class.so", wrong_class, "conflicts with ELF64 class"),
            ("wrong-data.so", wrong_data, "unsupported ELF header version"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = self._write(directory, name, bytes(payload))
                with self.assertRaises(inspector.AbiError) as caught:
                    inspector.inspect_file(path)
            self.assertIn(message, str(caught.exception))

    def test_elf_header_size_and_program_table_overlap_are_rejected(self):
        cases = []
        for name, payload, endian, ehsize_offset, phoff_offset, header_size in (
            ("elf32-le", elf32(), "<", 40, 28, 52),
            ("elf64-be", elf64(endianness="big"), ">", 52, 32, 64),
        ):
            undersized = bytearray(payload)
            struct.pack_into(endian + "H", undersized, ehsize_offset, header_size - 1)
            cases.append((name + "-size", undersized, "header size must be at least"))

            extended = bytearray(payload)
            struct.pack_into(endian + "H", extended, ehsize_offset, header_size + 8)
            cases.append((name + "-extended-overlap", extended, "overlaps the ELF header"))

            overlapping = bytearray(payload)
            struct.pack_into(
                endian + ("I" if header_size == 52 else "Q"),
                overlapping,
                phoff_offset,
                header_size - 4,
            )
            cases.append((name + "-overlap", overlapping, "overlaps the ELF header"))

        for name, payload, message in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = self._write(directory, name + ".so", bytes(payload))
                with self.assertRaises(inspector.AbiError) as caught:
                    inspector.inspect_file(path)
            self.assertIn(message, str(caught.exception))

    def test_nonoverlapping_extended_elf_header_is_accepted(self):
        for name, original, endian, ehsize_offset, phoff_offset, header_size, bitness in (
            ("elf32-le", elf32(), "<", 40, 28, 52, 32),
            ("elf64-be", elf64(endianness="big"), ">", 52, 32, 64, 64),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                payload = bytearray(original)
                payload[header_size:header_size] = b"\0" * 8
                extended_size = header_size + 8
                struct.pack_into(endian + "H", payload, ehsize_offset, extended_size)
                struct.pack_into(
                    endian + ("I" if header_size == 52 else "Q"),
                    payload,
                    phoff_offset,
                    extended_size,
                )
                filesz_offset = extended_size + (16 if header_size == 52 else 32)
                memsz_offset = extended_size + (20 if header_size == 52 else 40)
                size_format = endian + ("I" if header_size == 52 else "Q")
                struct.pack_into(size_format, payload, filesz_offset, len(payload))
                struct.pack_into(size_format, payload, memsz_offset, len(payload))
                path = self._write(directory, name + ".so", bytes(payload))
                report = inspector.inspect_file(path)
            self.assertEqual("ELF", report["format"])
            self.assertEqual(bitness, report["bitness"])

    def test_interpreter_segment_must_precede_loadable_segments(self):
        payload = bytearray(
            elf64(
                interpreter="/lib/ld-linux-aarch64.so.1",
                needed=("libc.so.6",),
            )
        )
        first = bytes(payload[64 : 64 + 56])
        second = bytes(payload[64 + 56 : 64 + 112])
        payload[64 : 64 + 56] = second
        payload[64 + 56 : 64 + 112] = first
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "late-interpreter.so", bytes(payload))
            with self.assertRaises(inspector.AbiError) as caught:
                inspector.inspect_file(path)
        self.assertIn("interpreter segment must precede", str(caught.exception))

    def test_android_candidate_requires_binary_evidence(self):
        payload = elf64(
            interpreter="/system/bin/linker64", needed=("liblog.so", "libc.so")
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "library.so", payload)
            report = inspector.inspect_file(path)
        self.assertEqual("android_candidate", report["candidate"])
        self.assertIn("liblog.so", report["needed"])

    def test_aarch64_and_android_path_name_alone_remain_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            nested = Path(directory) / "android" / "arm64"
            nested.mkdir(parents=True)
            path = self._write(str(nested), "libcandidate.so", elf64())
            report = inspector.inspect_file(path)
        self.assertEqual("arm64", report["machine"])
        self.assertEqual("unknown_elf", report["candidate"])
        self.assertIsNone(report["interpreter"])
        self.assertEqual([], report["needed"])

    def test_raw_glibc_text_and_unrecognized_linker_path_are_not_evidence(self):
        payload = elf64(interpreter="/tmp/ld-linux-aarch64.so.1") + b"GLIBC_9.99\0"
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "raw-glibc.so", payload)
            report = inspector.inspect_file(path)
        self.assertEqual("unknown_elf", report["candidate"])
        self.assertEqual([], report["glibc_versions"])

    def test_conflicting_android_and_glibc_evidence_remains_unknown(self):
        payload = elf64(
            interpreter="/system/bin/linker64",
            glibc_versions=("GLIBC_2.17",),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "ambiguous.so", payload)
            report = inspector.inspect_file(path)
        self.assertEqual("unknown_elf", report["candidate"])
        self.assertIn("conflicting Android and glibc evidence", report["classification_evidence"])

    def test_cli_emits_json_and_explicit_sdk_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "sample.dll", pe64())
            result = self._run(path, "--sdk-version", "caller-version")
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("caller-version", report["sdk_version"])
        self.assertEqual("offline-abi-report-v1", report["report_version"])
        self.assertEqual("", result.stderr)

    def test_truncated_and_non_binary_inputs_fail_cleanly(self):
        for name, payload, message in (
            ("short.exe", b"MZ", "DOS header is truncated"),
            ("short.so", b"\x7fELF", "identification is truncated"),
            ("text.bin", b"not a binary", "neither a PE nor an ELF"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = self._write(directory, name, payload)
                result = self._run(path)
            self.assertEqual(3, result.returncode)
            self.assertIn(message, result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_out_of_bounds_pe_section_and_elf_segment_are_rejected(self):
        broken_pe = bytearray(pe64())
        section = 0x80 + 24 + 112
        struct.pack_into("<II", broken_pe, section + 16, 32, len(broken_pe) - 4)

        broken_elf = bytearray(elf64())
        struct.pack_into("<Q", broken_elf, 64 + 32, len(broken_elf) + 1)
        struct.pack_into("<Q", broken_elf, 64 + 40, len(broken_elf) + 1)

        for name, payload, message in (
            ("bad.exe", bytes(broken_pe), "raw data"),
            ("bad.so", bytes(broken_elf), "segment 0"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = self._write(directory, name, payload)
                with self.assertRaises(inspector.AbiError) as caught:
                    inspector.inspect_file(path)
            self.assertIn(message, str(caught.exception))

    def test_pt_null_ignores_unused_file_and_memory_fields(self):
        payload = bytearray(elf64())
        struct.pack_into("<I", payload, 64, 0)
        struct.pack_into("<Q", payload, 64 + 32, 0xFFFFFFFFFFFFFFFF)
        struct.pack_into("<Q", payload, 64 + 40, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "null-header.so", bytes(payload))
            report = inspector.inspect_file(path)
        self.assertEqual("ELF", report["format"])
        self.assertEqual("unknown_elf", report["candidate"])

    def test_malformed_dynamic_and_version_links_are_rejected(self):
        no_null = bytearray(elf64(needed=("libc.so.6",)))
        phnum = struct.unpack_from("<H", no_null, 56)[0]
        dynamic_ph = 64 + (phnum - 1) * 56
        dynamic_offset = struct.unpack_from("<Q", no_null, dynamic_ph + 8)[0]
        dynamic_size = struct.unpack_from("<Q", no_null, dynamic_ph + 32)[0]
        struct.pack_into("<q", no_null, dynamic_offset + dynamic_size - 16, 1)

        bad_verneed = bytearray(elf64(glibc_versions=("GLIBC_2.17",)))
        dynamic_ph = 64 + (struct.unpack_from("<H", bad_verneed, 56)[0] - 1) * 56
        dynamic_offset = struct.unpack_from("<Q", bad_verneed, dynamic_ph + 8)[0]
        # DT_VERNEED is the third dynamic entry when no DT_NEEDED entries exist.
        struct.pack_into("<Q", bad_verneed, dynamic_offset + 2 * 16 + 8, 0x7FFFFFFFFFFFFFF0)

        bad_provider = bytearray(elf64(glibc_versions=("GLIBC_2.17",)))
        dynamic_ph = 64 + (struct.unpack_from("<H", bad_provider, 56)[0] - 1) * 56
        dynamic_offset = struct.unpack_from("<Q", bad_provider, dynamic_ph + 8)[0]
        verneed_address = struct.unpack_from("<Q", bad_provider, dynamic_offset + 2 * 16 + 8)[0]
        verneed_offset = verneed_address - 0x400000
        struct.pack_into("<I", bad_provider, verneed_offset + 4, 0xFFFFFFFF)

        for name, payload, message in (
            ("unterminated.so", bytes(no_null), "no DT_NULL"),
            ("bad-version.so", bytes(bad_verneed), "not backed by"),
            ("bad-provider.so", bytes(bad_provider), "version dependency"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = self._write(directory, name, payload)
                with self.assertRaises(inspector.AbiError) as caught:
                    inspector.inspect_file(path)
            self.assertIn(message, str(caught.exception))

    def test_wrong_machine_class_and_expected_architecture_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            class_mismatch = self._write(directory, "class.so", elf64(machine=40))
            with self.assertRaises(inspector.AbiError) as caught:
                inspector.inspect_file(class_mismatch)
            self.assertIn("conflicts with ELF64", str(caught.exception))

            expected_mismatch = self._write(directory, "machine.dll", pe64())
            result = self._run(expected_mismatch, "--expect-machine", "arm64")
        self.assertEqual(3, result.returncode)
        self.assertIn("expected arm64, found x86_64", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_pe_machine_bitness_conflict_and_unsupported_machine_are_rejected(self):
        for payload, message in (
            (pe64(optional_magic=0x10B), "conflicts with 32-bit"),
            (pe64(machine=0x9999), "unsupported PE machine"),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                path = self._write(directory, "bad.exe", payload)
                with self.assertRaises(inspector.AbiError) as caught:
                    inspector.inspect_file(path)
            self.assertIn(message, str(caught.exception))

    def test_size_limit_and_invalid_sdk_metadata_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "large.exe", b"MZ")
            with path.open("r+b") as stream:
                stream.truncate(inspector.MAX_FILE_BYTES + 1)
            with self.assertRaises(inspector.AbiError) as caught:
                inspector.inspect_file(path)
            self.assertIn("safety limit", str(caught.exception))

        with self.assertRaises(inspector.AbiError):
            inspector.inspect_file(Path("unused"), "\n")


if __name__ == "__main__":
    unittest.main()
