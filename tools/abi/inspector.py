#!/usr/bin/env python3
"""Inspect one PE or ELF file without loading or executing it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import stat
import struct
import sys
from typing import Any, Sequence


REPORT_VERSION = "offline-abi-report-v1"
MAX_FILE_BYTES = 16 << 20
MAX_PROGRAM_HEADERS = 128
MAX_PE_SECTIONS = 96
MAX_DYNAMIC_ENTRIES = 4096
MAX_NEEDED = 128
MAX_VERSION_RECORDS = 1024
MAX_STRING_TABLE_BYTES = 1 << 20
MAX_STRING_BYTES = 4096
SCOPE_DISCLAIMER = (
    "Offline structural inspection only; this does not load or execute the binary, "
    "prove target/device compatibility, or validate QNN, HTP, FSR4, or game behavior."
)

_PE_MACHINES = {
    0x014C: ("x86", 32),
    0x01C4: ("arm", 32),
    0x8664: ("x86_64", 64),
    0xAA64: ("arm64", 64),
}
_ELF_MACHINES = {
    3: ("x86", 32),
    40: ("arm", 32),
    62: ("x86_64", 64),
    183: ("arm64", 64),
    243: ("riscv", None),
}
_GLIBC_INTERPRETER_NAMES = frozenset(
    {
        "ld-linux.so.2",
        "ld-linux-armhf.so.3",
        "ld-linux-aarch64.so.1",
        "ld-linux-x86-64.so.2",
        "ld-linux-riscv64-lp64d.so.1",
    }
)


class AbiError(Exception):
    """The selected file is unsafe, malformed, unsupported, or mismatched."""


def _bounded(data: bytes, offset: int, size: int, label: str) -> memoryview:
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise AbiError(f"{label} is truncated or outside the file")
    return memoryview(data)[offset : offset + size]


def _unpack(data: bytes, fmt: str, offset: int, label: str) -> tuple[Any, ...]:
    size = struct.calcsize(fmt)
    _bounded(data, offset, size, label)
    return struct.unpack_from(fmt, data, offset)


def _cstring(table: bytes | memoryview, offset: int, label: str) -> str:
    if offset < 0 or offset >= len(table):
        raise AbiError(f"{label} string offset is outside its string table")
    end_limit = min(len(table), offset + MAX_STRING_BYTES + 1)
    if isinstance(table, memoryview):
        table = table.tobytes()
    end = table.find(b"\0", offset, end_limit)
    if end < 0:
        raise AbiError(f"{label} is not NUL-terminated within {MAX_STRING_BYTES} bytes")
    raw = table[offset:end]
    if not raw:
        raise AbiError(f"{label} must not be empty")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AbiError(f"{label} is not UTF-8") from exc


def _base_report(
    path: Path,
    file_format: str,
    machine: str,
    machine_id: int,
    bitness: int,
    sdk_version: str,
) -> dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "file": str(path),
        "format": file_format,
        "machine": machine,
        "machine_id": machine_id,
        "bitness": bitness,
        "sdk_version": sdk_version,
        "scope": SCOPE_DISCLAIMER,
    }


def _parse_pe(data: bytes, path: Path, sdk_version: str) -> dict[str, Any]:
    if len(data) < 64:
        raise AbiError("DOS header is truncated")
    (pe_offset,) = _unpack(data, "<I", 0x3C, "DOS e_lfanew")
    if pe_offset < 64:
        raise AbiError("PE header overlaps the DOS header")
    if bytes(_bounded(data, pe_offset, 4, "PE signature")) != b"PE\0\0":
        raise AbiError("PE signature is missing or malformed")

    coff = pe_offset + 4
    machine_id, section_count, _timestamp, _symptr, _symcount, opt_size, _flags = _unpack(
        data, "<HHIIIHH", coff, "COFF header"
    )
    if machine_id not in _PE_MACHINES:
        raise AbiError(f"unsupported PE machine 0x{machine_id:04x}")
    machine, machine_bits = _PE_MACHINES[machine_id]
    if not 1 <= section_count <= MAX_PE_SECTIONS:
        raise AbiError(f"PE section count must be between 1 and {MAX_PE_SECTIONS}")
    if opt_size < 2:
        raise AbiError("PE optional header is missing")
    opt_offset = coff + 20
    _bounded(data, opt_offset, opt_size, "PE optional header")
    (magic,) = _unpack(data, "<H", opt_offset, "PE optional-header magic")
    if magic == 0x10B:
        bitness = 32
        minimum_opt_size = 96
    elif magic == 0x20B:
        bitness = 64
        minimum_opt_size = 112
    else:
        raise AbiError(f"unsupported PE optional-header magic 0x{magic:04x}")
    if opt_size < minimum_opt_size:
        raise AbiError("PE optional header is truncated for its declared bitness")
    if bitness != machine_bits:
        raise AbiError(
            f"PE machine {machine} conflicts with {bitness}-bit optional header"
        )

    section_table = opt_offset + opt_size
    _bounded(data, section_table, section_count * 40, "PE section table")
    for index in range(section_count):
        section = section_table + index * 40
        raw_size, raw_offset = _unpack(
            data, "<II", section + 16, f"PE section {index} raw-data fields"
        )
        if raw_size:
            _bounded(data, raw_offset, raw_size, f"PE section {index} raw data")

    report = _base_report(path, "PE", machine, machine_id, bitness, sdk_version)
    report.update(
        {
            "candidate": "windows_pe",
            "classification_evidence": ["valid PE/COFF image headers"],
            "interpreter": None,
            "needed": [],
            "glibc_versions": [],
        }
    )
    return report


def _parse_elf(data: bytes, path: Path, sdk_version: str) -> dict[str, Any]:
    if len(data) < 16:
        raise AbiError("ELF identification is truncated")
    elf_class = data[4]
    data_encoding = data[5]
    if elf_class not in (1, 2):
        raise AbiError(f"unsupported ELF class {elf_class}")
    if data_encoding not in (1, 2):
        raise AbiError(f"unsupported ELF data encoding {data_encoding}")
    if data[6] != 1:
        raise AbiError(f"unsupported ELF identification version {data[6]}")
    endian = "<" if data_encoding == 1 else ">"
    endian_name = "little" if data_encoding == 1 else "big"
    bitness = 32 if elf_class == 1 else 64
    header_size = 52 if bitness == 32 else 64
    _bounded(data, 0, header_size, "ELF header")
    machine_id = _unpack(data, endian + "H", 18, "ELF machine")[0]
    version = _unpack(data, endian + "I", 20, "ELF version")[0]
    if version != 1:
        raise AbiError(f"unsupported ELF header version {version}")
    if machine_id not in _ELF_MACHINES:
        raise AbiError(f"unsupported ELF machine {machine_id}")
    machine, machine_bits = _ELF_MACHINES[machine_id]
    if machine_bits is not None and machine_bits != bitness:
        raise AbiError(f"ELF machine {machine} conflicts with ELF{bitness} class")

    if bitness == 32:
        phoff = _unpack(data, endian + "I", 28, "ELF program-header offset")[0]
        ehsize, phentsize, phnum = _unpack(
            data, endian + "HHH", 40, "ELF header sizes"
        )
        expected_ph_size = 32
    else:
        phoff = _unpack(data, endian + "Q", 32, "ELF program-header offset")[0]
        ehsize, phentsize, phnum = _unpack(
            data, endian + "HHH", 52, "ELF header sizes"
        )
        expected_ph_size = 56
    if ehsize < header_size or ehsize > len(data):
        raise AbiError("ELF header size is malformed or outside the file")
    if not 1 <= phnum <= MAX_PROGRAM_HEADERS:
        raise AbiError(
            f"ELF program-header count must be between 1 and {MAX_PROGRAM_HEADERS}"
        )
    if phentsize < expected_ph_size:
        raise AbiError("ELF program-header entry size is too small")
    _bounded(data, phoff, phentsize * phnum, "ELF program-header table")

    segments: list[dict[str, int]] = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        if bitness == 32:
            p_type, p_offset, p_vaddr, _paddr, p_filesz, p_memsz, _flags, _align = _unpack(
                data, endian + "IIIIIIII", offset, f"ELF program header {index}"
            )
        else:
            p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz, p_memsz, _align = _unpack(
                data, endian + "IIQQQQQQ", offset, f"ELF program header {index}"
            )
        if p_type == 0:  # PT_NULL fields are unused and have no file-range meaning.
            continue
        if p_type == 1 and p_filesz > p_memsz:
            raise AbiError(f"ELF segment {index} file size exceeds memory size")
        if p_filesz:
            _bounded(data, p_offset, p_filesz, f"ELF segment {index}")
        segments.append(
            {
                "type": p_type,
                "offset": p_offset,
                "vaddr": p_vaddr,
                "filesz": p_filesz,
            }
        )

    def map_vaddr(address: int, size: int, label: str) -> int:
        matches: list[int] = []
        for segment in segments:
            if segment["type"] != 1 or address < segment["vaddr"]:
                continue
            delta = address - segment["vaddr"]
            if delta <= segment["filesz"] and size <= segment["filesz"] - delta:
                matches.append(segment["offset"] + delta)
        if len(matches) != 1:
            qualifier = "not backed by" if not matches else "ambiguously backed by"
            raise AbiError(f"{label} is {qualifier} a single ELF load segment")
        return matches[0]

    interpreter: str | None = None
    dynamic_segment: dict[str, int] | None = None
    for index, segment in enumerate(segments):
        if segment["type"] == 3:
            if interpreter is not None:
                raise AbiError("ELF contains multiple interpreter segments")
            payload = bytes(
                _bounded(data, segment["offset"], segment["filesz"], f"ELF interpreter {index}")
            )
            if not payload or len(payload) > MAX_STRING_BYTES + 1 or payload[-1] != 0:
                raise AbiError("ELF interpreter is empty, too long, or not NUL-terminated")
            if b"\0" in payload[:-1]:
                raise AbiError("ELF interpreter contains embedded NUL padding")
            try:
                interpreter = payload[:-1].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise AbiError("ELF interpreter is not UTF-8") from exc
            if not interpreter:
                raise AbiError("ELF interpreter must not be empty")
        elif segment["type"] == 2:
            if dynamic_segment is not None:
                raise AbiError("ELF contains multiple dynamic segments")
            dynamic_segment = segment

    needed_offsets: list[int] = []
    singleton_tags: dict[int, int] = {}
    if dynamic_segment is not None:
        entry_size = 8 if bitness == 32 else 16
        if dynamic_segment["filesz"] % entry_size:
            raise AbiError("ELF dynamic segment size is not entry-aligned")
        entry_count = dynamic_segment["filesz"] // entry_size
        if not 1 <= entry_count <= MAX_DYNAMIC_ENTRIES:
            raise AbiError("ELF dynamic segment entry count is outside the safety limit")
        terminated = False
        for index in range(entry_count):
            offset = dynamic_segment["offset"] + index * entry_size
            fmt = endian + ("iI" if bitness == 32 else "qQ")
            tag, value = _unpack(data, fmt, offset, f"ELF dynamic entry {index}")
            if tag == 0:
                terminated = True
                break
            if tag == 1:
                if len(needed_offsets) >= MAX_NEEDED:
                    raise AbiError(f"ELF DT_NEEDED count exceeds {MAX_NEEDED}")
                needed_offsets.append(value)
            elif tag in (5, 10, 0x6FFFFFFE, 0x6FFFFFFF):
                if tag in singleton_tags:
                    raise AbiError(f"ELF dynamic tag 0x{tag:x} is duplicated")
                singleton_tags[tag] = value
        if not terminated:
            raise AbiError("ELF dynamic segment has no DT_NULL terminator")

    needed: list[str] = []
    glibc_versions: list[str] = []
    wants_strings = bool(needed_offsets) or 0x6FFFFFFE in singleton_tags
    string_table: bytes | None = None
    if wants_strings:
        if 5 not in singleton_tags or 10 not in singleton_tags:
            raise AbiError("ELF dynamic strings require both DT_STRTAB and DT_STRSZ")
        strsz = singleton_tags[10]
        if not 1 <= strsz <= MAX_STRING_TABLE_BYTES:
            raise AbiError("ELF dynamic string-table size is outside the safety limit")
        str_offset = map_vaddr(singleton_tags[5], strsz, "ELF dynamic string table")
        # Copy once: repeated dependency/version lookups must not recopy a
        # caller-controlled string table for every linked record.
        string_table = bytes(
            _bounded(data, str_offset, strsz, "ELF dynamic string table")
        )
        for index, offset in enumerate(needed_offsets):
            needed.append(_cstring(string_table, offset, f"DT_NEEDED[{index}]"))

    has_verneed = 0x6FFFFFFE in singleton_tags
    has_verneednum = 0x6FFFFFFF in singleton_tags
    if has_verneed != has_verneednum:
        raise AbiError("ELF requires both DT_VERNEED and DT_VERNEEDNUM")
    if has_verneed:
        assert string_table is not None
        count = singleton_tags[0x6FFFFFFF]
        if not 1 <= count <= MAX_VERSION_RECORDS:
            raise AbiError("ELF version-requirement count is outside the safety limit")
        base_address = singleton_tags[0x6FFFFFFE]
        record_relative = 0
        visited_records: set[int] = set()
        version_names: set[str] = set()
        for record_index in range(count):
            if record_relative in visited_records:
                raise AbiError("ELF version-requirement list contains a cycle")
            visited_records.add(record_relative)
            record_offset = map_vaddr(
                base_address + record_relative, 16, f"ELF version requirement {record_index}"
            )
            vn_version, vn_count, vn_file, vn_aux, vn_next = _unpack(
                data, endian + "HHIII", record_offset, f"ELF version requirement {record_index}"
            )
            if vn_version != 1 or not 1 <= vn_count <= MAX_VERSION_RECORDS:
                raise AbiError("ELF version-requirement record is malformed")
            _cstring(
                string_table,
                vn_file,
                f"ELF version dependency {record_index}",
            )
            aux_relative = vn_aux
            visited_aux: set[int] = set()
            for aux_index in range(vn_count):
                if aux_relative == 0 or aux_relative in visited_aux:
                    raise AbiError("ELF version auxiliary list is malformed or cyclic")
                visited_aux.add(aux_relative)
                aux_offset = map_vaddr(
                    base_address + record_relative + aux_relative,
                    16,
                    f"ELF version auxiliary {record_index}:{aux_index}",
                )
                _hash, _flags, _other, name_offset, aux_next = _unpack(
                    data,
                    endian + "IHHII",
                    aux_offset,
                    f"ELF version auxiliary {record_index}:{aux_index}",
                )
                name = _cstring(
                    string_table, name_offset, f"ELF version name {record_index}:{aux_index}"
                )
                if name.startswith("GLIBC_"):
                    version_names.add(name)
                if aux_index + 1 < vn_count:
                    if aux_next == 0:
                        raise AbiError("ELF version auxiliary list ends before vn_cnt")
                    aux_relative += aux_next
                elif aux_next != 0:
                    raise AbiError("ELF version auxiliary list exceeds vn_cnt")
            if record_index + 1 < count:
                if vn_next == 0:
                    raise AbiError("ELF version-requirement list ends before DT_VERNEEDNUM")
                record_relative += vn_next
            elif vn_next != 0:
                raise AbiError("ELF version-requirement list exceeds DT_VERNEEDNUM")
        glibc_versions = sorted(version_names)

    evidence_android: list[str] = []
    evidence_glibc: list[str] = []
    if interpreter in ("/system/bin/linker", "/system/bin/linker64") or (
        interpreter is not None
        and interpreter.startswith("/apex/com.android.runtime/bin/linker")
    ):
        evidence_android.append(f"Android dynamic linker: {interpreter}")
    android_libraries = sorted(set(needed) & {"libandroid.so", "liblog.so"})
    if android_libraries:
        evidence_android.append("Android-specific DT_NEEDED: " + ", ".join(android_libraries))
    glibc_interpreter = (
        interpreter is not None
        and interpreter.startswith(("/lib/", "/lib64/"))
        and PurePosixPath(interpreter).name in _GLIBC_INTERPRETER_NAMES
    )
    if glibc_interpreter:
        evidence_glibc.append(f"glibc-style dynamic linker: {interpreter}")
    if glibc_versions:
        evidence_glibc.append("GNU version requirements include GLIBC_* symbols")

    if evidence_android and not evidence_glibc:
        candidate = "android_candidate"
        evidence = evidence_android
    elif evidence_glibc and not evidence_android:
        candidate = "linux_glibc_candidate"
        evidence = evidence_glibc
    else:
        candidate = "unknown_elf"
        evidence = evidence_android + evidence_glibc
        if not evidence:
            evidence = ["no Android- or glibc-specific interpreter/dependency evidence"]
        else:
            evidence.append("conflicting Android and glibc evidence")

    report = _base_report(path, "ELF", machine, machine_id, bitness, sdk_version)
    report.update(
        {
            "endianness": endian_name,
            "candidate": candidate,
            "classification_evidence": evidence,
            "interpreter": interpreter,
            "needed": needed,
            "glibc_versions": glibc_versions,
        }
    )
    return report


def _validate_sdk_version(value: str | None) -> str:
    if value is None:
        return "unknown"
    if not value.strip() or len(value) > 128 or any(ord(char) < 0x20 for char in value):
        raise AbiError("SDK version metadata must be 1-128 printable characters")
    return value


def _read_file(path: Path) -> tuple[Path, bytes]:
    selected = Path(os.path.abspath(os.fspath(path)))
    try:
        before = selected.stat(follow_symlinks=False)
        reparse = bool(
            getattr(before, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        if stat.S_ISLNK(before.st_mode) or reparse:
            raise AbiError("input must not be a symlink or reparse point")
        if not stat.S_ISREG(before.st_mode):
            raise AbiError("input must be a regular file")
        if before.st_size > MAX_FILE_BYTES:
            raise AbiError(f"input exceeds the {MAX_FILE_BYTES}-byte safety limit")
        with selected.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise AbiError("input changed before it could be read")
            data = stream.read(MAX_FILE_BYTES + 1)
        after = selected.stat(follow_symlinks=False)
        if len(data) > MAX_FILE_BYTES:
            raise AbiError(f"input exceeds the {MAX_FILE_BYTES}-byte safety limit")
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ):
            raise AbiError("input changed while it was being read")
        return selected, data
    except AbiError:
        raise
    except OSError as exc:
        raise AbiError(f"cannot read input: {exc}") from exc


def inspect_file(
    path: Path, sdk_version: str | None = None, expect_machine: str | None = None
) -> dict[str, Any]:
    """Return a bounded structural report for one PE or ELF file."""
    sdk = _validate_sdk_version(sdk_version)
    selected, data = _read_file(path)
    if data.startswith(b"MZ"):
        report = _parse_pe(data, selected, sdk)
    elif data.startswith(b"\x7fELF"):
        report = _parse_elf(data, selected, sdk)
    else:
        raise AbiError("input is neither a PE nor an ELF file")
    if expect_machine is not None and report["machine"] != expect_machine:
        raise AbiError(
            f"architecture mismatch: expected {expect_machine}, found {report['machine']}"
        )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="one PE or ELF file to inspect read-only")
    parser.add_argument(
        "--sdk-version",
        help="explicit caller-supplied SDK version metadata; defaults to unknown",
    )
    parser.add_argument(
        "--expect-machine",
        choices=("x86", "x86_64", "arm", "arm64", "riscv"),
        help="fail if the parsed machine does not match",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = inspect_file(args.file, args.sdk_version, args.expect_machine)
    except AbiError as exc:
        print(f"inspection failed: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
