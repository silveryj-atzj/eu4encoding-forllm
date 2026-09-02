"""Encode and decode the escaped text format used by EU4DLL."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


CP1252_SPECIAL = {
    0x80: 0x20AC,
    0x82: 0x201A,
    0x83: 0x0192,
    0x84: 0x201E,
    0x85: 0x2026,
    0x86: 0x2020,
    0x87: 0x2021,
    0x88: 0x02C6,
    0x89: 0x2030,
    0x8A: 0x0160,
    0x8B: 0x2039,
    0x8C: 0x0152,
    0x8E: 0x017D,
    0x91: 0x2018,
    0x92: 0x2019,
    0x93: 0x201C,
    0x94: 0x201D,
    0x95: 0x2022,
    0x96: 0x2013,
    0x97: 0x2014,
    0x98: 0x02DC,
    0x99: 0x2122,
    0x9A: 0x0161,
    0x9B: 0x203A,
    0x9C: 0x0153,
    0x9E: 0x017E,
    0x9F: 0x0178,
}
CP1252_REVERSE = {value: key for key, value in CP1252_SPECIAL.items()}
RESERVED = {
    0xA4, 0xA3, 0xA7, 0x24, 0x5B, 0x00, 0x5C, 0x20, 0x0D, 0x0A,
    0x22, 0x7B, 0x7D, 0x40, 0x80, 0x7E, 0x2F, 0x5F, 0xBD, 0x3B,
    0x5D, 0x3D, 0x23, 0x3F, 0x3A, 0x3C, 0x3E, 0x2A, 0x7C,
}


def byte_to_cp1252(byte: int) -> int:
    return CP1252_SPECIAL.get(byte, byte)


def cp1252_to_byte(code_point: int) -> int | None:
    if code_point in CP1252_REVERSE:
        return CP1252_REVERSE[code_point]
    if code_point <= 0xFF:
        return code_point
    return None


def decode_raw(raw: bytes) -> str:
    result: list[str] = []
    index = 0
    while index < len(raw):
        marker = raw[index]
        index += 1
        if marker in (0x10, 0x11, 0x12, 0x13):
            if index + 1 >= len(raw):
                raise ValueError("truncated EU4DLL escape sequence")
            low, high = raw[index], raw[index + 1]
            index += 2
            code_point = (high << 8) | low
            if marker == 0x11:
                code_point -= 0xE
            elif marker == 0x12:
                code_point += 0x900
            elif marker == 0x13:
                code_point += 0x8F2
        else:
            code_point = byte_to_cp1252(marker)
        if code_point > 0xFFFF or 0x100 < code_point < 0x98F:
            code_point = 0x2026
        result.append(chr(code_point))
    return "".join(result)


def encode_raw(text: str) -> bytes:
    result = bytearray()
    for character in text:
        code_point = ord(character)
        direct_byte = cp1252_to_byte(code_point)
        if direct_byte is not None:
            result.append(direct_byte)
            continue
        if 0x100 < code_point < 0xA00:
            code_point += 0xE000
        high, low = code_point >> 8, code_point & 0xFF
        marker = 0x10 + int(high in RESERVED) * 2 + int(low in RESERVED)
        if marker == 0x11:
            low += 14
        elif marker == 0x12:
            high -= 9
        elif marker == 0x13:
            low += 14
            high -= 9
        result.extend((marker, low & 0xFF, high & 0xFF))
    return bytes(result)


def file_byte_to_raw(byte: int) -> int:
    code_point = byte_to_cp1252(byte)
    if code_point <= 0xFF:
        return code_point
    return CP1252_REVERSE[code_point]


def decode_file(data: bytes) -> bytes:
    lines = re.split(r"(\r\n|\n|\r)", data.decode("utf-8"))
    decoded_lines: list[str] = []
    for line in lines:
        start, end = line.find('"'), line.rfind('"')
        if start < 0 or end <= start:
            decoded_lines.append(line)
            continue
        payload = line[start + 1:end]
        if any(ord(character) > 0xFF and ord(character) not in CP1252_REVERSE for character in payload):
            decoded_lines.append(line)
            continue
        raw = bytes(file_byte_to_raw(ord(character)) for character in payload)
        decoded_lines.append(line[:start + 1] + decode_raw(raw) + line[end:])
    return "".join(decoded_lines).encode("utf-8")


def encode_file(data: bytes) -> bytes:
    text = data.decode("utf-8")
    raw = encode_raw(text)
    escaped = "".join(chr(byte_to_cp1252(byte)) for byte in raw)
    return escaped.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("decode", "encode"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    converter = decode_file if args.mode == "decode" else encode_file
    args.output.write_bytes(converter(args.input.read_bytes()))


if __name__ == "__main__":
    main()