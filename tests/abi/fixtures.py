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


def elf_image(
    *,
    bitness: int,
    endianness: str,
    machine: int,
    interpreter: str | None = None,
    needed: tuple[str, ...] = (),
    glibc_versions: tuple[str, ...] = (),
    version_requirements: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> bytes:
    """Build a small ELF image whose load segment maps the whole file."""
    if bitness not in (32, 64):
        raise ValueError("ELF fixture bitness must be 32 or 64")
    if endianness not in ("little", "big"):
        raise ValueError("ELF fixture endianness must be 'little' or 'big'")
    if glibc_versions and version_requirements:
        raise ValueError(
            "use glibc_versions or version_requirements, not both"
        )
    if glibc_versions:
        version_requirements = (("libc.so.6", glibc_versions),)
    if any(not provider or not versions for provider, versions in version_requirements):
        raise ValueError("each ELF version requirement needs a provider and versions")

    elf_class = 1 if bitness == 32 else 2
    data_encoding = 1 if endianness == "little" else 2
    endian = "<" if endianness == "little" else ">"
    header_size = 52 if bitness == 32 else 64
    program_header_size = 32 if bitness == 32 else 56
    dynamic_entry_size = 8 if bitness == 32 else 16
    payload_alignment = 4 if bitness == 32 else 8

    phnum = 1 + (interpreter is not None) + bool(needed or version_requirements)
    phoff = header_size
    cursor = phoff + phnum * program_header_size
    payloads: list[tuple[str, int, bytes]] = []

    def align(value: int) -> int:
        return (value + payload_alignment - 1) & ~(payload_alignment - 1)

    def dynamic_entry(tag: int, value: int) -> bytes:
        return struct.pack(endian + ("iI" if bitness == 32 else "qQ"), tag, value)

    def program_header(
        p_type: int,
        flags: int,
        offset: int,
        vaddr: int,
        filesz: int,
        memsz: int,
        alignment: int,
    ) -> bytes:
        if bitness == 32:
            return struct.pack(
                endian + "IIIIIIII",
                p_type,
                offset,
                vaddr,
                0,
                filesz,
                memsz,
                flags,
                alignment,
            )
        return struct.pack(
            endian + "IIQQQQQQ",
            p_type,
            flags,
            offset,
            vaddr,
            0,
            filesz,
            memsz,
            alignment,
        )

    interp_offset = 0
    if interpreter is not None:
        interp_offset = cursor
        payload = interpreter.encode("utf-8") + b"\0"
        payloads.append(("interp", cursor, payload))
        cursor += len(payload)
        cursor = align(cursor)

    dynamic_offset = 0
    dynamic_size = 0
    string_offset = 0
    string_table = bytearray(b"\0")
    string_offsets: dict[str, int] = {}
    version_strings = tuple(
        value
        for provider, versions in version_requirements
        for value in (provider, *versions)
    )
    for value in (*needed, *version_strings):
        if not value or value in string_offsets:
            continue
        string_offsets[value] = len(string_table)
        string_table.extend(value.encode("ascii") + b"\0")

    base = 0x400000
    if needed or version_requirements:
        dynamic_offset = cursor
        entry_count = len(needed) + 3 + (2 if version_requirements else 0)
        dynamic_size = entry_count * dynamic_entry_size
        cursor += dynamic_size
        string_offset = cursor
        payloads.append(("strings", cursor, bytes(string_table)))
        cursor += len(string_table)
        cursor = align(cursor)
        verneed_offset = 0
        verneed = b""
        if version_requirements:
            verneed_offset = cursor
            records = bytearray()
            for record_index, (provider, versions) in enumerate(version_requirements):
                record_size = 16 + len(versions) * 16
                next_record = (
                    record_size if record_index + 1 < len(version_requirements) else 0
                )
                records.extend(
                    struct.pack(
                        endian + "HHIII",
                        1,
                        len(versions),
                        string_offsets[provider],
                        16,
                        next_record,
                    )
                )
                for aux_index, version in enumerate(versions):
                    next_aux = 16 if aux_index + 1 < len(versions) else 0
                    records.extend(
                        struct.pack(
                            endian + "IHHII",
                            0,
                            0,
                            aux_index + 2,
                            string_offsets[version],
                            next_aux,
                        )
                    )
            verneed = bytes(records)
            payloads.append(("verneed", cursor, verneed))
            cursor += len(verneed)

        dynamic = bytearray()
        for library in needed:
            dynamic.extend(dynamic_entry(1, string_offsets[library]))
        dynamic.extend(dynamic_entry(5, base + string_offset))
        dynamic.extend(dynamic_entry(10, len(string_table)))
        if version_requirements:
            dynamic.extend(dynamic_entry(0x6FFFFFFE, base + verneed_offset))
            dynamic.extend(dynamic_entry(0x6FFFFFFF, len(version_requirements)))
        dynamic.extend(dynamic_entry(0, 0))
        assert len(dynamic) == dynamic_size
        payloads.append(("dynamic", dynamic_offset, bytes(dynamic)))

    data = bytearray(cursor)
    data[:16] = b"\x7fELF" + bytes((elf_class, data_encoding, 1, 0, 0)) + b"\0" * 7
    if bitness == 32:
        struct.pack_into(
            endian + "HHIIIIIHHHHHH",
            data,
            16,
            3,
            machine,
            1,
            0,
            phoff,
            0,
            0,
            header_size,
            program_header_size,
            phnum,
            0,
            0,
            0,
        )
    else:
        struct.pack_into(
            endian + "HHIQQQIHHHHHH",
            data,
            16,
            3,
            machine,
            1,
            0,
            phoff,
            0,
            0,
            header_size,
            program_header_size,
            phnum,
            0,
            0,
            0,
        )
    final_size = len(data)
    program_headers = []
    if interpreter is not None:
        size = len(interpreter.encode("utf-8")) + 1
        program_headers.append(
            program_header(3, 4, interp_offset, base + interp_offset, size, size, 1)
        )
    program_headers.append(
        program_header(1, 5, 0, base, final_size, final_size, 0x1000)
    )
    if needed or version_requirements:
        program_headers.append(
            program_header(
                2,
                4,
                dynamic_offset,
                base + dynamic_offset,
                dynamic_size,
                dynamic_size,
                payload_alignment,
            )
        )
    for index, header in enumerate(program_headers):
        start = phoff + index * program_header_size
        data[start : start + program_header_size] = header
    for _name, offset, payload in payloads:
        data[offset : offset + len(payload)] = payload
    return bytes(data)


def elf32(
    *,
    machine: int = 3,
    endianness: str = "little",
    interpreter: str | None = None,
    needed: tuple[str, ...] = (),
    glibc_versions: tuple[str, ...] = (),
    version_requirements: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> bytes:
    return elf_image(
        bitness=32,
        endianness=endianness,
        machine=machine,
        interpreter=interpreter,
        needed=needed,
        glibc_versions=glibc_versions,
        version_requirements=version_requirements,
    )


def elf64(
    *,
    machine: int = 183,
    endianness: str = "little",
    interpreter: str | None = None,
    needed: tuple[str, ...] = (),
    glibc_versions: tuple[str, ...] = (),
    version_requirements: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> bytes:
    return elf_image(
        bitness=64,
        endianness=endianness,
        machine=machine,
        interpreter=interpreter,
        needed=needed,
        glibc_versions=glibc_versions,
        version_requirements=version_requirements,
    )
