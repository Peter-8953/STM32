"""db.database: 建立 PostgreSQL 連線。

連線字串一律從環境變數 DB_DSN 讀，不寫死在程式碼裡（文件 7 節、
9 節「資料庫連線」規範）。DB_DSN 格式範例：

    postgresql://user:password@localhost:5432/rtc3231

.env 檔放這個變數，且 .env 要加入 .gitignore，不進版本控制。
"""

import os

import psycopg2


def get_connection():
    """回傳一個新的 psycopg2 connection。

    呼叫端負責在用完後 close()，或用 `with get_connection() as conn:`
    （psycopg2 的 connection 支援 context manager，離開時會自動
    commit/rollback，但不會自動 close，仍建議搭配 try/finally 或
    自行呼叫 conn.close()）。
    """
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        raise RuntimeError(
            "環境變數 DB_DSN 未設定。請在 .env 裡設定，例如：\n"
            "DB_DSN=postgresql://user:password@localhost:5432/rtc3231"
        )
    return psycopg2.connect(dsn)
