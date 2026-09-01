"""db.models: 資料庫 schema 定義（devices / readings / command_logs / time_readings）。

注意：這個檔名跟 rtc3231/models.py（dataclass：TempReading 等）
是兩個不同的東西，只是文件裡都沿用 models.py 這個檔名 —— 一個是
「資料庫的 schema」，一個是「Python 回傳值的型別」，職責完全不同。

四張表：
    devices       -- 裝置基本資料
    readings      -- 溫度紀錄，read_at 用 DS3231 回傳的 UTC 時間
    command_logs  -- 所有指令的執行紀錄（temp/time/sync 三個指令都會寫）
    time_readings -- GET_TIME 實際回傳的時間值本身（跟 readings 之於溫度是同一種角色）

2026-08-23：統一 readings / command_logs / time_readings 這三張「單次操作」表
的欄位結構跟順序，固定成：
    id, device_id, seq, <本表的資料值欄位...>, recorded_at
readings 原本沒有 seq 欄位（GET_TEMP 的封包 SEQ 之前只寫進 command_logs，
readings 本身沒有），這次一併補上，語意跟 command_logs.seq 完全一致
（同一次 GET_TEMP 請求的封包 SEQ），允許 NULL（既有舊資料回填不出來，
只能留空；之後新寫入的資料才會有值）。
"""

CREATE_DEVICES = """
CREATE TABLE IF NOT EXISTS devices (
    id          SMALLINT PRIMARY KEY,
    name        VARCHAR(64),
    port        VARCHAR(32),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
"""

# 欄位順序：id, device_id, seq, read_at, temperature, recorded_at
# seq：這次 GET_TEMP 請求的封包 SEQ（跟 command_logs.seq 存的是同一個值），
# 允許 NULL —— 既有舊資料沒有這個欄位，遷移時只能補 NULL。
CREATE_READINGS = """
CREATE TABLE IF NOT EXISTS readings (
    id          BIGSERIAL PRIMARY KEY,
    device_id   SMALLINT REFERENCES devices(id),
    seq         INTEGER,
    read_at     TIMESTAMPTZ NOT NULL,
    temperature NUMERIC(5,2) NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
"""

# seq 用 INTEGER 不用 SMALLINT：uint16 最大值 65535，SMALLINT 上限只到
# 32767，會溢位（文件 4.1 節、9 節都特別強調這點）。
# 欄位順序：id, device_id, seq, command, status, recorded_at
# recorded_at（原本叫 executed_at）：跟 readings/time_readings 的
# recorded_at 是同一種欄位——Postgres 用 DEFAULT NOW() 自動補的
# 「這筆紀錄寫入資料庫的時間」，只是原本三張表沒有統一命名。
CREATE_COMMAND_LOGS = """
CREATE TABLE IF NOT EXISTS command_logs (
    id          BIGSERIAL PRIMARY KEY,
    device_id   SMALLINT REFERENCES devices(id),
    seq         INTEGER,
    command     VARCHAR(32) NOT NULL,
    status      VARCHAR(8),
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
"""

# command_logs 這張表原本就存在、原本欄位叫 executed_at，光改上面的
# CREATE TABLE IF NOT EXISTS 文字對「已經存在的表」不會有任何作用
# （IF NOT EXISTS 遇到表已存在就整句跳過）。這段用 information_schema
# 檢查：舊欄位還在、新欄位還沒出現，才執行 RENAME COLUMN；已經改過
# 名或本來就是全新資料庫（一開始就用新版 CREATE_COMMAND_LOGS 建出
# recorded_at）都會自然跳過，可以放心讓 create_tables() 重複執行。
_MIGRATE_COMMAND_LOGS_RENAME = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'command_logs' AND column_name = 'executed_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'command_logs' AND column_name = 'recorded_at'
    ) THEN
        ALTER TABLE command_logs RENAME COLUMN executed_at TO recorded_at;
    END IF;
END $$;
"""


# seq 型別理由同 CREATE_COMMAND_LOGS：uint16 最大值 65535，不可用 SMALLINT。
# 欄位順序：id, device_id, seq, device_time, recorded_at
# device_time 才是「這筆資料的值」本身（DS3231 回報的時間），跟 readings
# 的 temperature 是同一種角色；不用另外叫 read_at，避免跟 readings 的
# read_at（「讀取當下的時間」）混淆語意 —— time_readings 這裡讀取當下
# 跟讀到的值根本是同一個時間點，沒有分開命名的必要。
CREATE_TIME_READINGS = """
CREATE TABLE IF NOT EXISTS time_readings (
    id          BIGSERIAL PRIMARY KEY,
    device_id   SMALLINT REFERENCES devices(id),
    seq         INTEGER,
    device_time TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
"""


# --- 2026-08-23：欄位新增／順序統一 migration ------------------------------
#
# PostgreSQL 沒有「直接搬動既有欄位順序」的指令，只能整張表重建：
#   1. 建一張同名+_new 的新表，欄位照新順序、新結構定義好
#      （PK/FK 直接用跟原本一樣的名稱命名，這樣改名回去之後名稱不會變）
#   2. 把舊表資料搬進新表（readings 沒有 seq 的舊資料，搬的時候補 NULL）
#   3. 用 setval 讓新表自己的 id 序列接續在舊資料最大 id 之後，避免撞號
#   4. 砍掉舊表、把新表改名回原本的表名
#   5. 把新表自動產生的序列（<table>_new_id_seq）改名回 <table>_id_seq，
#      沿用原本的命名慣例（欄位的 DEFAULT nextval(...) 是用 OID 追蹤，
#      序列改名後會自動指到新名字，不用另外處理）
#
# 每段都先用 information_schema 檢查目前欄位順序是否已經符合新結構，
# 已經符合就整段跳過 —— 可以放心讓 create_tables() 重複執行，也不會
# 對已經是新結構的資料庫做多餘的重建。
# 只有在資料表已存在（information_schema 查得到欄位）時才會進行重建；
# 全新資料庫會直接由上面的 CREATE_READINGS / CREATE_COMMAND_LOGS /
# CREATE_TIME_READINGS 建出新結構，這裡的檢查會發現順序已經一致而跳過。

_MIGRATE_READINGS_ADD_SEQ_AND_REORDER = """
DO $$
DECLARE
    current_order text;
BEGIN
    SELECT string_agg(column_name, ',' ORDER BY ordinal_position)
      INTO current_order
      FROM information_schema.columns
     WHERE table_name = 'readings';

    IF current_order IS NOT NULL
       AND current_order <> 'id,device_id,seq,read_at,temperature,recorded_at' THEN

        -- 約束先用 readings_new_* 這種暫時名稱：這時候舊的 readings
        -- 表還沒被砍掉，它自己就已經有一個叫 readings_pkey 的主鍵，
        -- 如果這裡直接用最終名稱會跟舊表當場撞名。等下面把舊表砍掉、
        -- 新表改名回 readings 之後，再用 RENAME CONSTRAINT 改回最終名稱。
        CREATE TABLE readings_new (
            id          BIGSERIAL,
            device_id   SMALLINT,
            seq         INTEGER,
            read_at     TIMESTAMPTZ NOT NULL,
            temperature NUMERIC(5,2) NOT NULL,
            recorded_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT readings_new_pkey PRIMARY KEY (id),
            CONSTRAINT readings_new_device_id_fkey FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        IF EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'readings' AND column_name = 'seq'
        ) THEN
            INSERT INTO readings_new (id, device_id, seq, read_at, temperature, recorded_at)
            SELECT id, device_id, seq, read_at, temperature, recorded_at FROM readings;
        ELSE
            -- 舊資料沒有 seq 欄位可回填，補 NULL（見檔案開頭說明）
            INSERT INTO readings_new (id, device_id, seq, read_at, temperature, recorded_at)
            SELECT id, device_id, NULL, read_at, temperature, recorded_at FROM readings;
        END IF;

        IF (SELECT MAX(id) FROM readings_new) IS NOT NULL THEN
            PERFORM setval('readings_new_id_seq', (SELECT MAX(id) FROM readings_new));
        END IF;

        DROP TABLE readings;
        ALTER TABLE readings_new RENAME TO readings;
        ALTER SEQUENCE readings_new_id_seq RENAME TO readings_id_seq;
        ALTER TABLE readings RENAME CONSTRAINT readings_new_pkey TO readings_pkey;
        ALTER TABLE readings RENAME CONSTRAINT readings_new_device_id_fkey TO readings_device_id_fkey;
    END IF;
END $$;
"""

_MIGRATE_COMMAND_LOGS_REORDER_SEQ = """
DO $$
DECLARE
    current_order text;
BEGIN
    SELECT string_agg(column_name, ',' ORDER BY ordinal_position)
      INTO current_order
      FROM information_schema.columns
     WHERE table_name = 'command_logs';

    IF current_order IS NOT NULL
       AND current_order <> 'id,device_id,seq,command,status,recorded_at' THEN

        -- 約束先用暫時名稱，理由同 readings 的 migration（見上方註解）
        CREATE TABLE command_logs_new (
            id          BIGSERIAL,
            device_id   SMALLINT,
            seq         INTEGER,
            command     VARCHAR(32) NOT NULL,
            status      VARCHAR(8),
            recorded_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT command_logs_new_pkey PRIMARY KEY (id),
            CONSTRAINT command_logs_new_device_id_fkey FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        INSERT INTO command_logs_new (id, device_id, seq, command, status, recorded_at)
        SELECT id, device_id, seq, command, status, recorded_at FROM command_logs;

        IF (SELECT MAX(id) FROM command_logs_new) IS NOT NULL THEN
            PERFORM setval('command_logs_new_id_seq', (SELECT MAX(id) FROM command_logs_new));
        END IF;

        DROP TABLE command_logs;
        ALTER TABLE command_logs_new RENAME TO command_logs;
        ALTER SEQUENCE command_logs_new_id_seq RENAME TO command_logs_id_seq;
        ALTER TABLE command_logs RENAME CONSTRAINT command_logs_new_pkey TO command_logs_pkey;
        ALTER TABLE command_logs RENAME CONSTRAINT command_logs_new_device_id_fkey TO command_logs_device_id_fkey;
    END IF;
END $$;
"""

_MIGRATE_TIME_READINGS_REORDER_SEQ = """
DO $$
DECLARE
    current_order text;
BEGIN
    SELECT string_agg(column_name, ',' ORDER BY ordinal_position)
      INTO current_order
      FROM information_schema.columns
     WHERE table_name = 'time_readings';

    IF current_order IS NOT NULL
       AND current_order <> 'id,device_id,seq,device_time,recorded_at' THEN

        -- 約束先用暫時名稱，理由同 readings 的 migration（見上方註解）
        CREATE TABLE time_readings_new (
            id          BIGSERIAL,
            device_id   SMALLINT,
            seq         INTEGER,
            device_time TIMESTAMPTZ NOT NULL,
            recorded_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT time_readings_new_pkey PRIMARY KEY (id),
            CONSTRAINT time_readings_new_device_id_fkey FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        INSERT INTO time_readings_new (id, device_id, seq, device_time, recorded_at)
        SELECT id, device_id, seq, device_time, recorded_at FROM time_readings;

        IF (SELECT MAX(id) FROM time_readings_new) IS NOT NULL THEN
            PERFORM setval('time_readings_new_id_seq', (SELECT MAX(id) FROM time_readings_new));
        END IF;

        DROP TABLE time_readings;
        ALTER TABLE time_readings_new RENAME TO time_readings;
        ALTER SEQUENCE time_readings_new_id_seq RENAME TO time_readings_id_seq;
        ALTER TABLE time_readings RENAME CONSTRAINT time_readings_new_pkey TO time_readings_pkey;
        ALTER TABLE time_readings RENAME CONSTRAINT time_readings_new_device_id_fkey TO time_readings_device_id_fkey;
    END IF;
END $$;
"""


def create_tables(conn) -> None:
    """建立四張表（IF NOT EXISTS，可重複執行不會報錯），並且處理：

      1. command_logs.executed_at -> recorded_at 這個歷史欄位改名
         （見 _MIGRATE_COMMAND_LOGS_RENAME）
      2. readings 新增 seq 欄位、三張「單次操作」表統一欄位順序成
         id, device_id, seq, <資料值...>, recorded_at
         （見 _MIGRATE_*_REORDER* / _MIGRATE_READINGS_ADD_SEQ_AND_REORDER）

    兩類 migration 都寫成可重複執行、對已是新結構的資料庫會自然跳過，
    且都保留既有資料（1 是單純改名；2 是整表重建但資料原樣搬過去，
    只有 readings 舊資料的 seq 欄位因為原本就不存在，只能補 NULL）。

    2 一定要排在 1 之後執行：command_logs 的重建 migration 會用到
    recorded_at 這個欄位名稱，必須先確定改名已經做完。
    """
    with conn.cursor() as cur:
        cur.execute(CREATE_DEVICES)
        cur.execute(CREATE_READINGS)
        cur.execute(CREATE_COMMAND_LOGS)
        cur.execute(CREATE_TIME_READINGS)
        cur.execute(_MIGRATE_COMMAND_LOGS_RENAME)
        cur.execute(_MIGRATE_READINGS_ADD_SEQ_AND_REORDER)
        cur.execute(_MIGRATE_COMMAND_LOGS_REORDER_SEQ)
        cur.execute(_MIGRATE_TIME_READINGS_REORDER_SEQ)
    conn.commit()