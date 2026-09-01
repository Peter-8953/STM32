"""repository.py: 所有 SQL 操作集中在這裡，其他模組不寫 SQL
（文件 9 節「SQL 集中」規範）。

每個函式的第一個參數 `db` 是一個 psycopg2 connection（例如
`db.database.get_connection()` 的回傳值），函式內部自己開
cursor、執行、commit，呼叫端不用管 cursor 生命週期。
"""

from datetime import datetime

import psycopg2.extras


def insert_reading(db, device_id: int, seq: int, read_at: datetime, temperature: float) -> None:
    """寫入一筆溫度紀錄。read_at 用 DS3231 回傳的 UTC 時間，不是電腦時間。

    seq：這次 GET_TEMP 請求的封包 SEQ，跟同一次操作寫進 command_logs.seq
    的是同一個值（2026-08-23 補上這個參數——readings 表原本沒有 seq
    欄位，這個值之前只進得了 command_logs，readings 本身沒有存過）。
    """
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO readings (device_id, seq, read_at, temperature)
            VALUES (%s, %s, %s, %s)
            """,
            (device_id, seq, read_at, temperature),
        )
    db.commit()


def insert_time_reading(db, device_id: int, device_time: datetime, seq: int) -> None:
    """寫入一筆時間紀錄。device_time 是 GET_TIME 實際回傳的 DS3231 時間值（UTC），
    不是這筆紀錄被寫入資料庫的時間（那個交給 recorded_at 的 DEFAULT NOW() 處理）。
    """
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO time_readings (device_id, device_time, seq)
            VALUES (%s, %s, %s)
            """,
            (device_id, device_time, seq),
        )
    db.commit()


def insert_command_log(db, device_id: int, command: str, seq: int, status: str) -> None:
    """寫入一筆指令歷史紀錄。seq 存實際封包 SEQ（來自 dataclass 的 .seq 欄位）。"""
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO command_logs (device_id, command, seq, status)
            VALUES (%s, %s, %s, %s)
            """,
            (device_id, command, seq, status),
        )
    db.commit()


def get_device(db, device_id: int):
    """查詢單一裝置資料，回傳 dict（欄位用名稱取值），查無資料回傳 None。"""
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM devices WHERE id = %s", (device_id,))
        row = cur.fetchone()
    return dict(row) if row is not None else None


def upsert_device(db, device_id: int, name: str, port: str) -> None:
    """新增或更新裝置資料（ON CONFLICT DO UPDATE）。"""
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO devices (id, name, port)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
                port = EXCLUDED.port
            """,
            (device_id, name, port),
        )
    db.commit()