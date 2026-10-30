#!/usr/bin/env python3
"""Bounded USB console capture with optional timed single-character controls."""
import argparse
import json
from pathlib import Path
import time
import serial
from esptool.reset import HardReset

parser = argparse.ArgumentParser()
parser.add_argument('--port', required=True)
parser.add_argument('--seconds', type=float, default=10)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--reset', action='store_true', help='Reset the observed native USB Serial/JTAG board')
parser.add_argument('--event', action='append', default=[], help='Seconds:character, e.g. 2:n or 5:o')
parser.add_argument('--events-file', type=Path, help='JSON array of [seconds, character] pairs')
args = parser.parse_args()
if not 0 < args.seconds <= 60: parser.error('Capture duration must be between 0 and 60 seconds')
events = []
if args.events_file:
    args.event.extend(f'{at}:{text}' for at,text in json.loads(args.events_file.read_text()))
for raw in args.event:
    at, text = raw.split(':', 1)
    if len(text) != 1 or not 0 <= float(at) < args.seconds: parser.error('Invalid event '+raw)
    events.append((float(at), text.encode('ascii')))
events.sort(key=lambda event: event[0])
link = serial.Serial(baudrate=115200, timeout=0.05)
link.dtr = False
link.rts = False
link.port = args.port
link.open()
try:
    if args.reset: HardReset(link, uses_usb=True)()
    started = time.monotonic()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('wb') as output:
        while time.monotonic() - started < args.seconds:
            while events and time.monotonic() - started >= events[0][0]:
                at, payload = events.pop(0)
                link.write(payload)
                print(f'Sent {payload.decode()!r} at {at:g}s', flush=True)
            data = link.read(max(1, link.in_waiting))
            if data: output.write(data)
    print(f'Captured {args.output.stat().st_size} bytes to {args.output}', flush=True)
finally:
    link.close()
