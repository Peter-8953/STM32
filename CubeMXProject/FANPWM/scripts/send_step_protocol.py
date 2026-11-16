#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automate an FANPWM manual step-response test.

The MCU does not run P25/P50/P75 automatically; this PC helper sends the
commands every --hold seconds and captures all serial output to a log.

Typical usage:
  python scripts\send_step_protocol.py COM4 --hold 30 --repeats 3
  python scripts\send_step_protocol.py COM4 --steps "P25 P50 P75 P25" --hold 30 --repeats 3

Outputs:
  logs/COM4_YYYYMMDD_HHMMSS.step.csv (raw serial capture, analyzable by
  scripts/analyze_rpm_test.py)
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    import serial
except ImportError as exc:
    raise SystemExit(f"pyserial required: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="COM port, e.g. COM4")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--steps", default="P25 P50 P75 P25",
                        help="Space-separated commands (default P25 P50 P75 P25)")
    parser.add_argument("--hold", type=float, default=30.0,
                        help="Seconds to hold each step (default 30)")
    parser.add_argument("--settle", type=float, default=5.0,
                        help="Seconds after protocol before stopping (default 5)")
    parser.add_argument("--repeats", type=int, default=1,
                        help="Number of full protocol repeats (default 1)")
    parser.add_argument("--startup-wait", type=float, default=3.0,
                        help="Wait after opening port before sending (default 3)")
    parser.add_argument("--csv-on", action="store_true",
                        help="Send V once before the protocol if you know CSV logging is OFF")
    parser.add_argument("--output", help="Output path; default logs/COMx_<timestamp>.step.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    steps = args.steps.split()
    if not steps:
        raise SystemExit("Empty --steps")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    port = args.port
    outfile = Path(args.output) if args.output else \
        ROOT / "logs" / f"{port}_{timestamp}.step.csv"
    outfile.parent.mkdir(parents=True, exist_ok=True)

    ser = serial.Serial(port, args.baud, timeout=0.25)
    stop_event = threading.Event()

    def log_reader() -> None:
        with outfile.open("w", encoding="utf-8", buffering=1) as f:
            while not stop_event.is_set():
                try:
                    raw = ser.readline()
                except Exception:
                    continue
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").rstrip()
                print(line)
                f.write(line + "\n")
            # drain
            while True:
                try:
                    raw = ser.read_all()
                except Exception:
                    break
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    print(line)
                    f.write(line + "\n")

    reader = threading.Thread(target=log_reader, daemon=True)
    reader.start()

    try:
        print(f"\n[record] {outfile}")
        time.sleep(args.startup_wait)

        if args.csv_on:
            ser.write(b"V\n")
            ser.flush()
            time.sleep(1.0)

        # Enter manual mode and reset target to 0 first.
        ser.write(b"A0\n")
        ser.flush()
        time.sleep(1.0)
        ser.write(b"X\n")
        ser.flush()
        time.sleep(2.0)

        for rep in range(args.repeats):
            print(f"\n=== REPEAT {rep + 1}/{args.repeats} ===")
            for cmd in steps:
                print(f"\n>>> sending {cmd}")
                ser.write((cmd + "\n").encode("utf-8"))
                ser.flush()
                time.sleep(args.hold)

        print(f"\n[done] settle {args.settle}s, then stop")
        time.sleep(args.settle)

        ser.write(b"S\n")
        ser.flush()
        time.sleep(1.0)
    finally:
        stop_event.set()
        reader.join(timeout=2.0)
        ser.close()
        print(f"\n[saved] {outfile}")


if __name__ == "__main__":
    main()