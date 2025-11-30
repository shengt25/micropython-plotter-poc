from __future__ import annotations

from dataclasses import dataclass
from typing import List

import serial.tools.list_ports


@dataclass
class SerialPortInfo:
    device: str
    description: str


PICO_VID = 0x2E8A


def find_pico_ports() -> List[SerialPortInfo]:
    """Return detected Raspberry Pi Pico serial ports."""
    ports = serial.tools.list_ports.comports()

    pico_ports: List[SerialPortInfo] = []
    for port in ports:
        if port.vid != PICO_VID:
            continue

        if "CMSIS-DAP" in (port.description or ""):
            continue

        pico_ports.append(SerialPortInfo(device=port.device, description=port.description or port.device))

    return pico_ports


def format_label(info: SerialPortInfo) -> str:
    description = info.description
    device = info.device

    if description and description != device:
        return f"{description} ({device})"

    return device

