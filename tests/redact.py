#!/usr/bin/env python3
"""Redact device-identifying data from captured SwitchOS/SwOS Lite fixtures.

Replaces MAC addresses, serial numbers and IP addresses with stable
placeholders so fixtures captured from a real device can be committed to a
public repository. Counters, port names, models and versions are left intact.

Usage:
    python3 tests/redact.py tests/fixtures/<device-dir>

It rewrites the files in place, so run it on a freshly-captured directory
before committing. See tests/README.md for the capture + redaction workflow.
"""
import re
import sys
import pathlib

FAKE_MAC = "aabbccddeeff"
FAKE_RMAC = "aabbccddee00"
FAKE_IP = "0x00000000"
FAKE_SERIAL_HEX = "52454441435445442d534e"  # "REDACTED-SN"


def _redact_sys(text: str) -> str:
    # Device and router MAC: SwOS (mac/rmac) and SwOS Lite (i03/i11)
    text = re.sub(r"((?:mac|i03):')[0-9a-fA-F]{12}(')",
                  lambda m: m.group(1) + FAKE_MAC + m.group(2), text)
    text = re.sub(r"((?:rmac|i11):')[0-9a-fA-F]{12}(')",
                  lambda m: m.group(1) + FAKE_RMAC + m.group(2), text)
    # Serial number: SwOS (sid) and SwOS Lite (i04, scalar in sys.b)
    text = re.sub(r"((?:sid|i04):')[0-9a-fA-F]+(')",
                  lambda m: m.group(1) + FAKE_SERIAL_HEX + m.group(2), text)
    # IP addresses: SwOS (ip/cip/sip) and SwOS Lite (i02/i09, only in sys.b)
    text = re.sub(r"\b(ip|cip|sip|i02|i09):0x[0-9a-fA-F]+",
                  lambda m: f"{m.group(1)}:{FAKE_IP}", text)
    return text


def _redact_sfp(text: str) -> str:
    # SFP module serial: SwOS (ser:[...]) and SwOS Lite (i04:[...] array)
    text = re.sub(r"((?:ser|i04):\[')[0-9a-fA-F]+(')",
                  lambda m: m.group(1) + FAKE_SERIAL_HEX + m.group(2), text)
    return text


def _redact_dhost(text: str) -> str:
    # MAC address table: replace each host MAC with a sequential placeholder.
    # SwOS uses adr:'..'; SwOS Lite uses i01:'..'.
    counter = [0]

    def repl(m):
        counter[0] += 1
        return f"{m.group(1)}:'020000{counter[0]:06x}'"

    return re.sub(r"(adr|i01):'[0-9a-fA-F]{12}'", repl, text)


def redact_file(path: pathlib.Path) -> None:
    text = path.read_text()
    name = path.name
    if name == "sys.b":
        text = _redact_sys(text)
    elif name == "sfp.b":
        text = _redact_sfp(text)
    elif name in ("bang_dhost.b", "!dhost.b"):
        text = _redact_dhost(text)
    path.write_text(text)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1
    target = pathlib.Path(argv[1])
    paths = [target] if target.is_file() else sorted(target.glob("*.b"))
    for p in paths:
        redact_file(p)
        print(f"redacted {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
