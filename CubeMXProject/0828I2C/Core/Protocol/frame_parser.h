/**
  ******************************************************************************
  * @file    frame_parser.h
  * @brief   RTC3231 通訊協定 — Frame 格式定義、CRC16、build/parse API
  *
  * 對應移植計畫書「第 1 階：純邏輯先行」。純 C 邏輯，不依賴任何
  * STM32 HAL / BSP 標頭，可在任意平台（含 PC）編譯測試，之後原封不動
  * 加進 IAR 專案即可。
  *
  * Frame 格式：
  *   [SOF 2B][VER 1B][SRC 1B][DST 1B][CMD 1B][SEQ 2B][LEN 1B][PAYLOAD nB][FLAGS 1B][CRC 2B]
  *
  * - SOF 不計入 CRC 計算範圍
  * - CRC16 計算範圍：VER ~ FLAGS（共 FRAME_CRC_FIXED_LEN + payload_len bytes）
  * - CRC16 演算法：CCITT(False)，poly=0x1021, init=0xFFFF，無反射、無 final XOR
  *   驗算向量：crc16("123456789", 9) == 0x29B1
  *
  * !! 待確認假設 !!
  * SEQ、CRC 這兩個多 byte 欄位目前假設用 Big-Endian（高位元組先傳）序列化，
  * 是從 CMD_SET_TIME payload 的 [年高][年低] 記法反推的，文件裡沒有明講。
  * 務必對照 Python 端 protocol.py 核對一致；若相反，搜尋本檔案與對應 .c
  * 裡標註 "big-endian" 的那幾行對調即可。
  ******************************************************************************
  */
#ifndef FRAME_PARSER_H
#define FRAME_PARSER_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

/* ==== SOF / VER ==== */
#define FRAME_SOF0                 0xAAu
#define FRAME_SOF1                 0x55u
#define FRAME_VER                  0x01u

/* ==== Payload 上限（韌體端硬限制，PC 端沒有對齊這個限制） ==== */
#define FRAME_PAYLOAD_MAX          32u

/* CRC 計算固定長度部分：VER+SRC+DST+CMD+SEQ(2)+LEN = 8 bytes
   實際 CRC 涵蓋長度 = FRAME_CRC_FIXED_LEN + payload_len */
#define FRAME_CRC_FIXED_LEN        8u

/* 一個 frame 的最小長度（payload_len = 0 時）：
   SOF(2)+VER(1)+SRC(1)+DST(1)+CMD(1)+SEQ(2)+LEN(1)+FLAGS(1)+CRC(2) = 12 */
#define FRAME_MIN_LEN               12u
#define FRAME_MAX_LEN               (FRAME_MIN_LEN + FRAME_PAYLOAD_MAX)

/* ==== CMD 代碼表 ==== */
#define CMD_GET_TIME                0x01u   /* PC->MCU，無 payload */
#define CMD_SET_TIME                0x02u   /* PC->MCU，7B [年高][年低][月][日][時][分][秒] */
#define CMD_GET_TEMP                0x03u   /* PC->MCU，無 payload */
#define CMD_GET_ID                  0x04u   /* PC->MCU，無 payload */
#define CMD_ACK                     0x10u   /* MCU->PC，無 payload */
#define CMD_DATA_TIME                0x11u  /* MCU->PC，7B，格式同 SET_TIME */
#define CMD_DATA_TEMP                0x12u  /* MCU->PC，9B [溫度整數][溫度小數][年高][年低][月][日][時][分][秒] */
#define CMD_DATA_ID                  0x13u  /* MCU->PC，1B [device_id] */
#define CMD_ERR                      0xFFu  /* MCU->PC，1B [錯誤碼] */

/* ==== FLAGS 位元 ==== */
#define FLAG_NEED_ACK                0x01u   /* bit 0 */
#define FLAG_IS_ERROR                0x02u   /* bit 1 */

/* ==== 錯誤碼（CMD_ERR 的 payload） ==== */
#define ERR_UNKNOWN_CMD               0x01u
#define ERR_PAYLOAD_TOO_SHORT         0x02u

/* ==== frame_parse() 回傳狀態 ==== */
typedef enum
{
    FRAME_OK = 0,
    FRAME_ERR_LEN,       /* 資料不夠長，或 LEN 欄位超過 FRAME_PAYLOAD_MAX */
    FRAME_ERR_SOF,       /* 開頭兩個 byte 不是 0xAA 0x55 */
    FRAME_ERR_VER,       /* VER 不是 FRAME_VER */
    FRAME_ERR_CRC        /* CRC16 校驗失敗 */
} FrameStatus;

/* ==== 邏輯層 Frame 表示（已反序列化） ==== */
typedef struct
{
    uint8_t  ver;
    uint8_t  src;
    uint8_t  dst;
    uint8_t  cmd;
    uint16_t seq;
    uint8_t  len;                          /* payload 實際長度 */
    uint8_t  payload[FRAME_PAYLOAD_MAX];
    uint8_t  flags;
} Frame;

/**
  * @brief  CRC16-CCITT(False) 計算
  * @param  data 起始位址（從 VER 開始算，不含 SOF）
  * @param  len  計算長度（bytes）
  * @retval 16-bit CRC 值
  */
uint16_t crc16(const uint8_t *data, uint16_t len);

/**
  * @brief  將邏輯 Frame 組裝成可送出的原始 byte 序列（含 SOF 與 CRC）
  * @param  f            要組裝的 frame（f->len 不可超過 FRAME_PAYLOAD_MAX）
  * @param  out_buf       輸出緩衝區
  * @param  out_buf_size  緩衝區容量（bytes）
  * @retval 實際寫入的 byte 數；0 表示參數錯誤或緩衝區不夠大
  */
uint16_t frame_build(const Frame *f, uint8_t *out_buf, uint16_t out_buf_size);

/**
  * @brief  解析一段完整的 raw bytes（從 SOF 開始）為邏輯 Frame，並驗證 CRC
  * @param  raw       原始資料起始位址（raw[0] 必須是 SOF0）
  * @param  raw_len   raw 緩衝區內可用長度
  * @param  out_frame 解析成功時寫入這裡
  * @retval FRAME_OK 表示成功；其餘為對應錯誤原因
  */
FrameStatus frame_parse(const uint8_t *raw, uint16_t raw_len, Frame *out_frame);

#ifdef __cplusplus
}
#endif

#endif /* FRAME_PARSER_H */
