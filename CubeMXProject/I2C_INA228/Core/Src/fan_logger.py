#!/usr/bin/env python3
"""
Fan power logger: STM32 serial output -> PostgreSQL.

The firmware prints a header once after every boot, then one CSV line every 0.5 s over the
ST-LINK virtual COM port:
    # t_ms,vbus_mV,i_mA,p_mW,e_mJ,iavg_mA,pavg_mW,flags
    # INA228 init OK (code 0)
    12825,12176,82,1001,346,57,688,0x00
This program reads those lines, stamps them with the PC clock and stores them in the table
fan_power (created on first run). The firmware does not have to change.

    pip install pyserial "psycopg[binary]"
    python fan_logger.py --port COM4 --dsn postgresql://postgres:PASSWORD@localhost:5432/fanlog

Only one program can open a COM port at a time: close Tera Term / the IDE terminal first.
The database itself must already exist; the table is created automatically.
--dsn can be left out when DATABASE_URL or the standard PG* variables (PGHOST, PGPORT, PGDATABASE,
PGUSER, PGPASSWORD) are set.

A wrong port or database stops the program at start-up with a message. After that it keeps going
through a database restart (rows are queued and written once the server is back) and through an
unplugged board (the port is re-opened). Stop it with Ctrl+C.

Rows that belong together share run_start. A new run begins when this program starts, when the board
prints its banner / header / "INA228 init OK" again, or when t_ms goes backwards (the board restarted).
Inside a run e_mj only counts up, so the energy used in a run is max(e_mj) - min(e_mj).
"""
import argparse
import collections
import os
import re
import sys
import time
from datetime import datetime, timezone

import psycopg
import serial

COLUMNS = ["t_ms", "vbus_mV", "i_mA", "p_mW", "e_mJ", "iavg_mA", "pavg_mW", "flags"]   # the CSV header

SCHEMA = """
CREATE TABLE fan_power (
    id         bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts         timestamptz NOT NULL DEFAULT now(),  -- PC clock when the line arrived
    run_start  timestamptz NOT NULL,                -- PC clock when this run was first seen (see top of file)
    t_ms       bigint      NOT NULL,                -- board uptime, ms
    vbus_mv    integer     NOT NULL,                -- mV
    i_ma       integer     NOT NULL,                -- mA (negative: current flows the other way)
    p_mw       integer     NOT NULL,                -- mW
    e_mj       bigint      NOT NULL,                -- mJ, INA228 energy counter (restarts at 0 after a chip reset)
    iavg_ma    integer     NOT NULL,                -- mA, exactly as the firmware prints it
    pavg_mw    integer     NOT NULL,                -- mW, exactly as the firmware prints it
    flags      bigint      NOT NULL                 -- the firmware's flags value (0x00 = none)
);
CREATE INDEX fan_power_ts_idx ON fan_power (ts);
"""

TABLE_COLUMNS = ("ts", "run_start", "t_ms", "vbus_mv", "i_ma", "p_mw", "e_mj", "iavg_ma", "pavg_mw", "flags")
INSERT = ("INSERT INTO fan_power (" + ", ".join(TABLE_COLUMNS) + ") VALUES ("
          + ", ".join(["%s"] * len(TABLE_COLUMNS)) + ")")

# One data line, same order as COLUMNS. At most 9 digits in the integer columns, so a garbled line
# can never overflow one; i_mA and iavg_mA may be negative.
FIELDS = [r"\d{1,12}", r"\d{1,9}", r"-?\d{1,9}", r"\d{1,9}", r"\d{1,15}", r"-?\d{1,9}", r"\d{1,9}",
          r"0[xX][0-9A-Fa-f]{1,8}|\d{1,9}"]
ROW = re.compile(r"\s*,\s*".join("(" + f + ")" for f in FIELDS))

QUEUE_MAX = 100_000     # about 14 hours of rows at 2 per second; beyond that the oldest are dropped
RETRY_S = 5             # pause between attempts while the database is unreachable


class SchemaError(Exception):
    """The table fan_power exists but does not have the columns this program writes."""


def log(msg):
    print(msg, flush=True)


def oneline(err):
    return " ".join(str(err).split())


def parse_line(text):
    """(t_ms, vbus_mv, i_ma, p_mw, e_mj, iavg_ma, pavg_mw, flags) for a data line, None for any other line."""
    m = ROW.fullmatch(text)
    if m is None:
        return None
    *numbers, flags = m.groups()
    return (*[int(n) for n in numbers], int(flags, 16) if flags[:2] in ("0x", "0X") else int(flags))


def header_columns(text):
    """Column names of the '# t_ms,vbus_mV,...' line the firmware prints at boot, None for any other line."""
    names = [c.strip().lower() for c in text.lstrip("#").split(",")]
    return names if "t_ms" in names else None


class Db:
    """PostgreSQL connection that survives a server restart: rows wait in a queue until written."""

    def __init__(self, dsn):
        self.dsn = dsn
        self.conn = None
        self.queue = collections.deque()
        self.retry_at = 0.0
        self.saved = 0
        self.dropped = 0

    def connect(self):
        conn = psycopg.connect(self.dsn, connect_timeout=5, application_name="fan_logger")
        try:
            # Only create the table when it is missing, so a role without CREATE rights still works.
            if not conn.execute("SELECT to_regclass('fan_power') IS NOT NULL").fetchone()[0]:
                conn.execute(SCHEMA)
            else:
                have = {r[0] for r in conn.execute(
                    "SELECT attname FROM pg_attribute "
                    "WHERE attrelid = 'fan_power'::regclass AND attnum > 0 AND NOT attisdropped")}
                missing = [c for c in TABLE_COLUMNS if c not in have]
                if missing:
                    raise SchemaError(
                        "Table fan_power already exists but lacks the columns " + ", ".join(missing) + ".\n"
                        "It was probably made by an older version of this program. If it holds nothing you need:\n"
                        "    DROP TABLE fan_power;\n"
                        "or keep the old rows under another name:\n"
                        "    ALTER TABLE fan_power RENAME TO fan_power_old;\n"
                        "then start this program again.")
            conn.commit()
        except BaseException:
            conn.close()
            raise
        self.conn = conn

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except psycopg.Error:
                pass
            self.conn = None

    def add(self, row):
        if len(self.queue) >= QUEUE_MAX:
            self.queue.popleft()
            self.dropped += 1
            if self.dropped % 1000 == 1:
                log(f"! queue full, {self.dropped} oldest rows dropped so far")
        self.queue.append(row)

    def flush(self, force=False):
        """Write the queued rows. If the server cannot be reached they stay queued for the next try."""
        if not self.queue or (not force and time.monotonic() < self.retry_at):
            return
        try:
            if self.conn is None:
                self.connect()
                log("database connection restored")
            rows = list(self.queue)
            with self.conn.cursor() as cur:
                cur.executemany(INSERT, rows)
            self.conn.commit()
            self.queue.clear()
            self.saved += len(rows)
        except (psycopg.Error, SchemaError) as e:
            # Server down, connection dropped, table dropped, missing privilege ...: keep the rows
            # and try again on a fresh connection (which also re-creates a missing table).
            log(f"! database error, {len(self.queue)} rows waiting: {oneline(e)}")
            self.close()
            self.retry_at = time.monotonic() + RETRY_S


class Port:
    """Serial port that re-opens itself when it disappears (USB unplugged, ST-LINK reset)."""

    def __init__(self, name, baud):
        self.name = name
        self.baud = baud
        self.ser = self._open()                             # a wrong or busy port fails right here

    def _open(self):
        ser = serial.Serial(self.name, self.baud, timeout=1)
        try:
            ser.readline()                                  # we join in the middle of a line: drop that fragment
        except serial.SerialException:
            ser.close()
            raise
        return ser

    def readline(self):
        """One decoded, stripped line. "" after 1 s without data or while the port is away."""
        try:
            if self.ser is None:
                self.ser = self._open()
                log(f"{self.name} is back")
            raw = self.ser.readline()
        except serial.SerialException as e:
            if self.ser is not None:
                log(f"! lost {self.name}, retrying every 2 s: {oneline(e)}")
                try:
                    self.ser.close()
                except (serial.SerialException, OSError):
                    pass
                self.ser = None
            time.sleep(2)
            return ""
        return raw.decode("ascii", errors="backslashreplace").strip()

    def close(self):
        if self.ser is not None:
            self.ser.close()


def main():
    ap = argparse.ArgumentParser(description="Store the STM32 fan power log in PostgreSQL.")
    ap.add_argument("--port", default="COM4", help="ST-LINK virtual COM port (default: COM4)")
    ap.add_argument("--baud", type=int, default=115200, help="default: 115200")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""),
                    help="e.g. postgresql://user:password@localhost:5432/fanlog "
                         "(default: DATABASE_URL, else the PG* environment variables)")
    ap.add_argument("--quiet", action="store_true", help="do not print every stored line")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(errors="backslashreplace")   # odd bytes must not crash a cp950 console
    except AttributeError:
        pass

    db = Db(args.dsn)
    try:
        db.connect()
    except SchemaError as e:
        sys.exit(str(e))
    except psycopg.Error as e:
        sys.exit(f"Cannot connect to PostgreSQL: {oneline(e)}")
    try:
        port = Port(args.port, args.baud)
    except serial.SerialException as e:
        sys.exit(f"Cannot open {args.port}: {oneline(e)}")
    log(f"Logging {args.port} to PostgreSQL. Press Ctrl+C to stop.")

    expected = [c.lower() for c in COLUMNS]
    run_start = None        # PC clock when the current run was first seen
    last_t = None           # t_ms of the previous row
    new_run = True          # the next row begins a new run
    layout_ok = True        # False after a header with columns this program does not store
    unknown = 0             # lines in a row that were not understood
    try:
        while True:
            text = port.readline()
            if text:
                now = datetime.now(timezone.utc)
                row = parse_line(text)
                msg = text.lstrip("#").strip()
                if row is not None:
                    if not layout_ok:
                        log(f"? {text}")                    # not stored, see the warning about the header
                    else:
                        if new_run or row[0] < last_t:      # first row, a banner/init line came, or t_ms went back
                            if last_t is not None:
                                log("new run: the board restarted or the chip was re-initialised")
                            run_start, new_run = now, False
                        last_t = row[0]
                        db.add((now, run_start, *row))
                        unknown = 0
                        if not args.quiet:
                            log(f"{now.astimezone():%H:%M:%S}  {text}")
                elif header_columns(text) is not None:
                    new_run = True
                    layout_ok = header_columns(text) == expected
                    if not layout_ok:
                        log("! the board now prints different columns (" + text.lstrip("#").strip()
                            + "); rows are NOT stored until this program is updated")
                elif msg.startswith("INA228 init OK"):
                    new_run = True                          # the chip was reset, so e_mJ restarts from 0
                    log("INA228 initialised, energy counter restarted")
                elif msg.startswith("INA228"):
                    log(f"! {text}")                        # init FAILED / read error: check the wiring
                elif text.startswith("Welcome"):
                    new_run = True                          # boot banner
                    log(text)
                else:
                    log(f"? {text}")                        # line noise, a changed format
                    unknown += 1
                    if unknown == 10:
                        log("! 10 lines in a row were not understood: wrong --baud, or different firmware?")
            db.flush()
    except KeyboardInterrupt:
        pass
    finally:
        db.flush(force=True)
        port.close()
        db.close()
    log(f"Stopped. {db.saved} rows saved" + (f", {len(db.queue)} could not be saved." if db.queue else "."))


if __name__ == "__main__":
    main()
