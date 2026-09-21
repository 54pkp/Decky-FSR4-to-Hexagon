"""Deterministic, synthetic PE/ELF fixture builders owned by ABI tests."""

from __future__ import annotations

import struct


def pe64(machine: int = 0x8664, optional_magic: int = 0x20B) -> bytes:
    pe_offset = 0x80
    optional_size = 112
    raw_offset = 0x200
    raw_size = 16
    data = bytearray(raw_offset + raw_size)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe_offset)
    data[pe_offset : pe_offset + 4] = b"PE\0\0"
    struct.pack_into(
        "<HHIIIHH",
        data,
        pe_offset + 4,
        machine,
        1,
        0,
        0,
        0,
        optional_size,
        0x2022,
    )
    optional = pe_offset + 24
    struct.pack_into("<H", data, optional, optional_magic)
    section = optional + optional_size
    data[section : section + 8] = b".text\0\0\0"
    struct.pack_into("<II", data, section + 16, raw_size, raw_offset)
    data[raw_offset : raw_offset + raw_size] = bytes(range(raw_size))
    return bytes(data)


def elf64(
    *,
    machine: int = 183,
    interpreter: str | None = None,
    needed: tuple[str, ...] = (),
    glibc_versions: tuple[str, ...] = (),
) -> bytes:
    """Build a small ELF64 image whose load segment maps the whole file."""
    phnum = 1 + (interpreter is not None) + bool(needed or glibc_versions)
    phoff = 64
    cursor = phoff + phnum * 56
    payloads: list[tuple[str, int, bytes]] = []

    interp_offset = 0
    if interpreter is not None:
        interp_offset = cursor
        payload = interpreter.encode("utf-8") + b"\0"
        payloads.append(("interp", cursor, payload))
        cursor += len(payload)
        cursor = (cursor + 7) & ~7

    dynamic_offset = 0
    dynamic_size = 0
    string_offset = 0
    string_table = bytearray(b"\0")
    string_offsets: dict[str, int] = {}
    for value in (*needed, "libc.so.6" if glibc_versions else "", *glibc_versions):
        if not value or value in string_offsets:
            continue
        string_offsets[value] = len(string_table)
        string_table.extend(value.encode("ascii") + b"\0")

    base = 0x400000
    if needed or glibc_versions:
        dynamic_offset = cursor
        entry_count = len(needed) + 3 + (2 if glibc_versions else 0)
        dynamic_size = entry_count * 16
        cursor += dynamic_size
        string_offset = cursor
        payloads.append(("strings", cursor, bytes(string_table)))
        cursor += len(string_table)
        cursor = (cursor + 7) & ~7
        verneed_offset = 0
        verneed = b""
        if glibc_versions:
            verneed_offset = cursor
            aux = bytearray()
            for index, version in enumerate(glibc_versions):
                next_offset = 16 if index + 1 < len(glibc_versions) else 0
                aux.extend(
                    struct.pack(
                        "<IHHII", 0, 0, index + 2, string_offsets[version], next_offset
                    )
                )
            verneed = struct.pack(
                "<HHIII",
                1,
                len(glibc_versions),
                string_offsets["libc.so.6"],
                16,
                0,
            ) + bytes(aux)
            payloads.append(("verneed", cursor, verneed))
            cursor += len(verneed)

        dynamic = bytearray()
        for library in needed:
            dynamic.extend(struct.pack("<qQ", 1, string_offsets[library]))
        dynamic.extend(struct.pack("<qQ", 5, base + string_offset))
        dynamic.extend(struct.pack("<qQ", 10, len(string_table)))
        if glibc_versions:
            dynamic.extend(struct.pack("<qQ", 0x6FFFFFFE, base + verneed_offset))
            dynamic.extend(struct.pack("<qQ", 0x6FFFFFFF, 1))
        dynamic.extend(struct.pack("<qQ", 0, 0))
        assert len(dynamic) == dynamic_size
        payloads.append(("dynamic", dynamic_offset, bytes(dynamic)))

    data = bytearray(cursor)
    data[:16] = b"\x7fELF" + bytes((2, 1, 1, 0, 0)) + b"\0" * 7
    struct.pack_into(
        "<HHIQQQIHHHHHH",
        data,
        16,
        3,
        machine,
        1,
        0,
        phoff,
        0,
        0,
        64,
        56,
        phnum,
        0,
        0,
        0,
    )
    final_size = len(data)
    program_headers = [
        struct.pack("<IIQQQQQQ", 1, 5, 0, base, base, final_size, final_size, 0x1000)
    ]
    if interpreter is not None:
        size = len(interpreter.encode("utf-8")) + 1
        program_headers.append(
            struct.pack(
                "<IIQQQQQQ", 3, 4, interp_offset, base + interp_offset, 0, size, size, 1
            )
        )
    if needed or glibc_versions:
        program_headers.append(
            struct.pack(
                "<IIQQQQQQ",
                2,
                4,
                dynamic_offset,
                base + dynamic_offset,
                0,
                dynamic_size,
                dynamic_size,
                8,
            )
        )
    for index, header in enumerate(program_headers):
        start = phoff + index * 56
        data[start : start + 56] = header
    for _name, offset, payload in payloads:
        data[offset : offset + len(payload)] = payload
    return bytes(data)
