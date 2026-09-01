/**
  ******************************************************************************
  * @file    rtc_driver.c
  * @brief   DS3231 暫存器讀寫 + BCD 轉換 -- 實作
  ******************************************************************************
  */
#include "rtc_driver.h"
#include <stddef.h>

/* DS3231 月份暫存器（0x05）的 bit7 是世紀旗標，bit6/bit5 未使用。BCD 轉換
   之前一定要先遮罩掉，不然世紀位元會被誤當成「月份十位數」的一部分，
   換算出 >12 的錯誤月份（例如世紀位元=1、月份=8 時，不遮罩會被讀成
   0x88 -> 十位數8 -> 88月）。 */
#define DS3231_MONTH_MASK    0x1Fu

static uint8_t bcd2dec(uint8_t bcd)
{
    return (uint8_t)((bcd >> 4) * 10u + (bcd & 0x0Fu));
}

HAL_StatusTypeDef rtc_get_time(I2C_HandleTypeDef *hi2c, RtcDateTime *out)
{
    uint8_t raw[7];
    HAL_StatusTypeDef status;

    if ((hi2c == NULL) || (out == NULL))
    {
        return HAL_ERROR;
    }

    /* 暫存器 0x00 開始連續讀 7 bytes：秒/分/時/星期/日/月/年。
       跟 main.c 目前的作法一樣一次讀完（星期 raw[3] 這個專案不使用，
       讀出來直接丟棄，不需要另外處理「中間欄位跳著讀」的問題，因為
       HAL_I2C_Mem_Read 本來就是連續讀完整個範圍）。 */
    status = HAL_I2C_Mem_Read(hi2c, (uint16_t)(DS3231_I2C_ADDR << 1), DS3231_REG_SECONDS,
                               I2C_MEMADD_SIZE_8BIT, raw, (uint16_t)sizeof(raw), HAL_MAX_DELAY);
    if (status != HAL_OK)
    {
        return status;
    }

    /* raw[0]=sec, raw[1]=min, raw[2]=hour：BCD 轉換沿用 main.c 已實機驗證
       過的寫法（(byte>>4)*10+(byte&0x0F)），這裡假設板子跑在 24 小時模式
       ——開機後的預設值，程式裡沒有任何地方去改成 12 小時模式，所以
       bit6（12/24模式）、bit7 都是 0，直接對整個 byte 位移是安全的。 */
    out->second = bcd2dec(raw[0]);
    out->minute = bcd2dec(raw[1]);
    out->hour   = bcd2dec(raw[2]);

    /* raw[3] = day-of-week，不使用 */

    /* raw[4] = date（日），純 2 位數 BCD，不需要遮罩 */
    out->day = bcd2dec(raw[4]);

    /* raw[5] = month，bit7 是世紀旗標，要先遮罩掉才能轉 BCD */
    out->month = bcd2dec((uint8_t)(raw[5] & DS3231_MONTH_MASK));

    /* raw[6] = year，DS3231 只存 2 位數 BCD（00-99）。
       !! 待確認假設 !!：這裡固定假設世紀是 20xx（+2000），沒有去讀
       月份暫存器 bit7 的世紀旗標。專案是 2026 年建置，這個假設在可預見
       的使用期間內都成立；如果之後真的需要跨世紀（例如年份要回推到
       1999 年以前），要改成實際讀取並解讀世紀旗標，而不是寫死 +2000。 */
    out->year = (uint16_t)(2000u + bcd2dec(raw[6]));

    return HAL_OK;
}

/* 十進位 -> BCD，SET_TIME 寫入方向跟 bcd2dec() 相反（計畫書 4.5 節公式） */
static uint8_t dec2bcd(uint8_t decimal)
{
    return (uint8_t)(((decimal / 10u) << 4) | (decimal % 10u));
}

HAL_StatusTypeDef rtc_set_time(I2C_HandleTypeDef *hi2c, const RtcDateTime *t)
{
    uint8_t time_regs[3];   /* 0x00-0x02：秒/分/時 */
    uint8_t date_regs[3];   /* 0x04-0x06：日/月/年 */
    HAL_StatusTypeDef status;
    uint8_t year_2digit;

    if ((hi2c == NULL) || (t == NULL))
    {
        return HAL_ERROR;
    }
    if (t->year < 2000u)
    {
        /* 跟 rtc_get_time() 的世紀假設對稱，年份不能小於 2000 */
        return HAL_ERROR;
    }

    time_regs[0] = dec2bcd(t->second);
    time_regs[1] = dec2bcd(t->minute);
    time_regs[2] = dec2bcd(t->hour);

    status = HAL_I2C_Mem_Write(hi2c, (uint16_t)(DS3231_I2C_ADDR << 1), DS3231_REG_SECONDS,
                                I2C_MEMADD_SIZE_8BIT, time_regs, (uint16_t)sizeof(time_regs),
                                HAL_MAX_DELAY);
    if (status != HAL_OK)
    {
        return status;
    }

    year_2digit = (uint8_t)((t->year - 2000u) % 100u);
    date_regs[0] = dec2bcd(t->day);
    date_regs[1] = dec2bcd(t->month);   /* bit7(世紀旗標)維持 0，跟讀取端假設一致 */
    date_regs[2] = dec2bcd(year_2digit);

    /* 故意跳過 day-of-week（0x03）分兩段寫：協定的 7-byte payload 沒帶
       這個欄位，沒資料可寫，跳過它比硬塞一個湊出來的值乾淨 */
    return HAL_I2C_Mem_Write(hi2c, (uint16_t)(DS3231_I2C_ADDR << 1), DS3231_REG_DATE,
                              I2C_MEMADD_SIZE_8BIT, date_regs, (uint16_t)sizeof(date_regs),
                              HAL_MAX_DELAY);
}

HAL_StatusTypeDef rtc_get_temp(I2C_HandleTypeDef *hi2c, RtcTemperature *out)
{
    uint8_t raw[2];
    HAL_StatusTypeDef status;

    if ((hi2c == NULL) || (out == NULL))
    {
        return HAL_ERROR;
    }

    /* 直接定址讀 0x11-0x12，不經過 rtc_get_time()，也不用讀過
       0x00~0x10——跟 rtc_get_time() 是各自獨立的 I2C transaction */
    status = HAL_I2C_Mem_Read(hi2c, (uint16_t)(DS3231_I2C_ADDR << 1), DS3231_REG_TEMP_MSB,
                               I2C_MEMADD_SIZE_8BIT, raw, (uint16_t)sizeof(raw), HAL_MAX_DELAY);
    if (status != HAL_OK)
    {
        return status;
    }

    out->temp_int  = (int8_t)raw[0];                  /* MSB：兩補數有號整數部分 */
    out->temp_frac = (uint8_t)((raw[1] >> 6) * 25u);   /* LSB 高2位：0/25/50/75 */

    return HAL_OK;
}
