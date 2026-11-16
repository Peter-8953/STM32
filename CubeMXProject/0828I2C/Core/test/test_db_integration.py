"""test_db_integration.py -- 階段2-3 驗收，需要真的 PostgreSQL 服務。

用法：
    export DB_DSN=postgresql://user:password@localhost:5432/rtc3231
    python test_db_integration.py
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_connection
from db.models import create_tables
from db import repository


def main():
    conn = get_connection()

    print("[1] 建立四張表...")
    create_tables(conn)
    print("    OK")

    print("[2] upsert_device：新增裝置...")
    repository.upsert_device(conn, device_id=2, name="Arduino Nano #1", port="COM3")
    dev = repository.get_device(conn, 2)
    assert dev is not None, "get_device 應該要查得到剛新增的裝置"
    assert dev["name"] == "Arduino Nano #1"
    assert dev["port"] == "COM3"
    print(f"    OK -> {dev}")

    print("[3] upsert_device：同一個 id，確認是 UPDATE 不是報錯...")
    repository.upsert_device(conn, device_id=2, name="Arduino Nano #1 (改名)", port="COM5")
    dev2 = repository.get_device(conn, 2)
    assert dev2["name"] == "Arduino Nano #1 (改名)"
    assert dev2["port"] == "COM5"
    print(f"    OK -> {dev2}")

    print("[4] get_device：查詢不存在的裝置，應回傳 None...")
    missing = repository.get_device(conn, 99)
    assert missing is None
    print("    OK -> None")

    print("[5] insert_reading：寫入溫度紀錄...")
    now_utc = datetime.now(timezone.utc)
    repository.insert_reading(conn, device_id=2, seq=65535, read_at=now_utc, temperature=27.25)
    print("    OK")

    print("[6] insert_command_log：寫入指令紀錄，seq 用 uint16 上限附近的值...")
    # 這是關鍵測試：SMALLINT 上限只到 32767，uint16 最大到 65535。
    # 如果 seq 欄位型別選錯（用了 SMALLINT），這裡會直接拋 DB 錯誤。
    repository.insert_command_log(conn, device_id=2, command="GET_TIME", seq=65535, status="ok")
    print("    OK -- seq=65535 寫入成功，證明 INTEGER 型別正確（SMALLINT 會在這裡失敗）")

    print("[7] insert_time_reading：寫入時間紀錄，seq 一樣測 uint16 上限...")
    # time_readings 是新加的表：device_time 存 GET_TIME 實際回傳的時間值本身
    # （不是 recorded_at 那種寫入當下的時間），這裡順便驗證 UTC 精準往返，
    # 不會被 psycopg2 或 TIMESTAMPTZ 欄位悄悄動過。
    time_utc = datetime.now(timezone.utc)
    repository.insert_time_reading(conn, device_id=2, device_time=time_utc, seq=65535)
    print("    OK -- seq=65535 寫入成功")

    print("[8] 直接查表，驗證資料真的寫進去、型別跟數值都正確...")
    with conn.cursor() as cur:
        cur.execute("SELECT temperature, read_at, seq FROM readings WHERE device_id = 2 ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        assert float(row[0]) == 27.25
        assert row[2] == 65535, f"readings.seq 型別可能選錯了：預期 65535，讀出 {row[2]}"
        print(f"    readings 最新一筆 -> temperature={row[0]}, read_at={row[1]}, seq={row[2]}")

        cur.execute("SELECT seq, command FROM command_logs WHERE device_id = 2 ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        assert row[0] == 65535
        print(f"    command_logs 最新一筆 -> seq={row[0]}, command={row[1]}")

        cur.execute("SELECT device_time, seq FROM time_readings WHERE device_id = 2 ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        assert row[0] == time_utc, f"UTC 時間沒有精準保留：寫入 {time_utc!r}，讀出 {row[0]!r}"
        assert row[1] == 65535
        print(f"    time_readings 最新一筆 -> device_time={row[0]}, seq={row[1]}")

    conn.close()
    print("\n=== 全部測試通過 ===")


if __name__ == "__main__":
    main()
