"""commands.py: CLI 指令表，把 DS3231 操作、格式化輸出、資料庫寫入串在一起。

每個指令三個部分（對應文件 4.3 節）：
    func       -- 呼叫 DS3231 的哪個操作，回傳 dataclass
                  （TempReading / TimeReading / SyncResult）
    format     -- 把 dataclass 格式化成一行字串印出來
    on_result  -- 把 dataclass 寫進資料庫

F5：on_result 直接用 v.seq / v.temperature 這種欄位名稱取值，
不用 isinstance 判斷回傳值是哪一種型別。
"""

from datetime import timezone, timedelta

from db import repository

# 台灣不使用日光節約時間，固定 UTC+8 即可，不需要 zoneinfo/tzdata
# 這種需要額外資料庫的方案（Windows 預設不一定裝了 IANA 時區資料）。
TAIPEI_TZ = timezone(timedelta(hours=8))


def _format_taipei(dt) -> str:
    """把（UTC，timezone-aware 的）datetime 轉成台灣時間字串，只給
    CLI 顯示用。底層協定、資料庫全部維持 UTC 不變——DS3231 存 UTC
    是刻意的設計（文件 F3 修正），這裡只是顯示層轉換，不影響任何
    寫入資料庫或送封包的邏輯。
    """
    return dt.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _on_temp_result(db, rtc, v) -> None:
    """temp 現在寫兩張表：readings 存溫度值本身，command_logs 補上
    這次 GET_TEMP 的執行紀錄（seq/status）。

    2026-08-23：readings 新增了 seq 欄位（跟 command_logs.seq 存的是
    同一個值，這次 GET_TEMP 請求的封包 SEQ），之前這個值只進得了
    command_logs，readings 本身沒有存過，這次一併補上，讓兩張表都
    留得下同一筆操作的封包 SEQ 對應關係。

    兩個 insert_* 各自獨立 commit（沿用 repository.py 原本的寫法），
    不是同一個 transaction；如果兩者的原子性以後變得重要，可以再
    考慮包成一個 transaction。
    """
    repository.insert_reading(
        db,
        device_id=rtc.device_id,
        seq=v.seq,                      # 封包 SEQ，跟下面 command_logs 存的是同一個值
        read_at=v.read_at,              # 資料庫仍然存 UTC，不受顯示層影響
        temperature=v.temperature,
    )
    repository.insert_command_log(
        db,
        device_id=rtc.device_id,
        command="GET_TEMP",
        seq=v.seq,
        status="ok",
    )


def _on_time_result(db, rtc, v) -> None:
    """time 現在也寫兩張表：time_readings 存 DS3231 實際回傳的時間值
    本身（之前這個值只印在終端機、沒有進資料庫），command_logs 維持
    原本就有的執行紀錄。
    """
    repository.insert_time_reading(
        db,
        device_id=rtc.device_id,
        device_time=v.datetime,
        seq=v.seq,
    )
    repository.insert_command_log(
        db,
        device_id=rtc.device_id,
        command="GET_TIME",
        seq=v.seq,                      # 真實封包 SEQ
        status="ok",
    )


COMMANDS = {
    "temp": {
        "desc": "每秒讀取溫度並存入資料庫",
        "mode": "loop",
        "func": lambda rtc: rtc.temperature,
        "format": lambda v: f"{v.temperature:.2f} °C",
        "on_result": _on_temp_result,
    },
    "time": {
        "desc": "每秒讀取時間並存入資料庫",
        "mode": "loop",
        "func": lambda rtc: rtc.datetime,
        "format": lambda v: f"{_format_taipei(v.datetime)}（台灣時間）",
        "on_result": _on_time_result,
    },
    "sync": {
        "desc": "校正時間（對準電腦 UTC，只執行一次）",
        "mode": "once",
        "func": lambda rtc: rtc.sync_from_pc(),
        "format": lambda v: "校正完成",
        "on_result": lambda db, rtc, v: repository.insert_command_log(
            db,
            device_id=rtc.device_id,
            command="SET_TIME",
            seq=v.seq,
            status="ok",
        ),
    },
}