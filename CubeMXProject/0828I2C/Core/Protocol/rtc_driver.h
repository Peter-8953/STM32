/**
  ******************************************************************************
  * @file    rtc_driver.h
  * @brief   DS3231 暫存器讀寫 + BCD 轉換
  *
  * 對應移植計畫書「檔案對照表」的 rtc_driver.h/.c。第2階只做讀
  * （rtc_get_time），寫入（SET_TIME 用）留給第3階的 rtc_set_time()。
  *
  * 暫存器位址、BCD 轉換公式對應計畫書 4.4 / 4.5 節。
  ******************************************************************************
  */
#ifndef RTC_DRIVER_H
#define RTC_DRIVER_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "stm32g4xx_hal.h"   /* I2C_HandleTypeDef, HAL_StatusTypeDef */

/* DS3231 的 I2C 7-bit 位址。跟 main.c 現有寫法一致，呼叫端自己 <<1
   （main.c 裡 HAL_I2C_IsDeviceReady/Mem_Read 現有呼叫都是這樣用的）。 */
#define DS3231_I2C_ADDR       0x68u

/* 暫存器位址（計畫書 4.4 節） */
#define DS3231_REG_SECONDS    0x00u
#define DS3231_REG_MINUTES    0x01u
#define DS3231_REG_HOURS      0x02u
#define DS3231_REG_DOW        0x03u   /* day-of-week，這個專案不使用 */
#define DS3231_REG_DATE       0x04u
#define DS3231_REG_MONTH      0x05u
#define DS3231_REG_YEAR        0x06u
#define DS3231_REG_TEMP_MSB    0x11u
#define DS3231_REG_TEMP_LSB    0x12u

/* 解碼後的時間欄位，跟協定 7-byte payload（[年高][年低][月][日][時][分][秒]，
   計畫書 4.2 節）欄位一一對應，year 是完整 4 位數。 */
typedef struct {
    uint16_t year;    /* 完整年份，例如 2026（假設世紀 20xx，見 .c 檔註解） */
    uint8_t  month;   /* 1-12 */
    uint8_t  day;     /* 1-31 */
    uint8_t  hour;    /* 0-23 */
    uint8_t  minute;  /* 0-59 */
    uint8_t  second;  /* 0-59 */
} RtcDateTime;

/**
 * @brief  讀取 DS3231 目前時間
 * @param  hi2c  已初始化好的 I2C handle（main.c 裡的 &hi2c1）
 * @param  out   輸出：解碼後的時間欄位
 * @retval HAL_OK 成功；其餘為 HAL_I2C_Mem_Read 回傳的錯誤碼
 */
HAL_StatusTypeDef rtc_get_time(I2C_HandleTypeDef *hi2c, RtcDateTime *out);

/**
 * @brief  把時間寫進 DS3231（CMD_SET_TIME 用）
 *
 * 分兩段寫：0x00-0x02（秒/分/時）跟 0x04-0x06（日/月/年），刻意跳過
 * day-of-week（0x03）——協定的 7-byte payload 沒有帶這個欄位，沒資料可寫，
 * 分兩段跳過它比硬塞一個湊出來的值乾淨。
 *
 * 世紀假設跟 rtc_get_time() 對稱：只接受 year >= 2000，內部只存
 * (year-2000)%100 進 DS3231 的兩位數年份暫存器，月份暫存器的世紀旗標
 * （bit7）維持 0。
 *
 * @param  hi2c 已初始化好的 I2C handle
 * @param  t    要寫入的時間（year 必須 >= 2000）
 * @retval HAL_OK 成功；year < 2000 或 I2C 寫入失敗回傳 HAL_ERROR
 */
HAL_StatusTypeDef rtc_set_time(I2C_HandleTypeDef *hi2c, const RtcDateTime *t);

/* 解碼後的溫度（CMD_GET_TEMP 用） */
typedef struct {
    int8_t  temp_int;    /* 攝氏溫度整數部分，有號（DS3231 MSB 暫存器原生就是兩補數） */
    uint8_t temp_frac;   /* 小數部分，0/25/50/75——DS3231 原生只有 0.25°C 解析度，
                             這裡換算成百分位方便直接當成 "XX.YY" 讀。
                             !! 待確認假設 !!：還沒有 Python 端程式碼可以核對這個
                             換算方式，如果 PC 端預期的是別的格式（例如 0-3 的原始
                             quarter count），只要改 rtc_get_temp() 內部就好。 */
} RtcTemperature;

/**
 * @brief  讀取 DS3231 目前溫度
 *
 * 直接定址讀 0x11-0x12（溫度 MSB/LSB），跟 rtc_get_time() 是各自獨立的
 * I2C transaction，不會互相影響，也不需要讀過 Alarm/Control 那段。
 *
 * @param  hi2c 已初始化好的 I2C handle
 * @param  out  輸出：解碼後的溫度
 * @retval HAL_OK 成功；其餘為 HAL_I2C_Mem_Read 回傳的錯誤碼
 */
HAL_StatusTypeDef rtc_get_temp(I2C_HandleTypeDef *hi2c, RtcTemperature *out);

#ifdef __cplusplus
}
#endif

#endif /* RTC_DRIVER_H */
