/**
  ******************************************************************************
  * @file    test_frame.c
  * @brief   frame_parser 的 PC 端獨立驗證程式（僅供開發時驗證用）
  *
  * !! 注意 !!：這個檔案有自己的 main()，不要加進 IAR 專案，會跟
  * main.c 的 main() 衝突。這裡編譯出來的執行檔只在你的電腦上跑，
  * 純粹用來驗證 frame_parser.c 的邏輯，不涉及任何 STM32 硬體。
  ******************************************************************************
  */
#include <stdio.h>
#include <string.h>
#include "frame_parser.h"

static void print_bytes(const uint8_t *buf, uint16_t len)
{
    uint16_t i;
    for (i = 0; i < len; i++)
    {
        printf("%02X ", buf[i]);
    }
    printf("\n");
}

int main(void)
{
    int fail = 0;

    /* Test 1: CRC16 known test vector (文件 4.1 節指定的驗算向量) */
    {
        const uint8_t vec[9] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
        uint16_t crc = crc16(vec, 9);
        printf("[Test1] crc16(\"123456789\") = 0x%04X (expect 0x29B1) -> %s\n",
               crc, (crc == 0x29B1) ? "PASS" : "FAIL");
        if (crc != 0x29B1) fail++;
    }

    /* Test 2: build/parse round trip, CMD_GET_TIME (no payload) */
    {
        Frame f;
        uint8_t buf[64];
        uint16_t n;
        Frame parsed;
        FrameStatus st;
        int ok;

        memset(&f, 0, sizeof(f));
        f.ver = FRAME_VER;
        f.src = 0x01;
        f.dst = 0x02;
        f.cmd = CMD_GET_TIME;
        f.seq = 0x1234;
        f.len = 0;
        f.flags = FLAG_NEED_ACK;

        n = frame_build(&f, buf, sizeof(buf));
        printf("[Test2] frame_build len=%u bytes= ", n);
        print_bytes(buf, n);

        st = frame_parse(buf, n, &parsed);
        printf("[Test2] frame_parse status=%d (expect 0) -> %s\n",
               (int)st, (st == FRAME_OK) ? "PASS" : "FAIL");
        if (st != FRAME_OK) fail++;

        ok = (parsed.ver == f.ver) && (parsed.src == f.src) &&
             (parsed.dst == f.dst) && (parsed.cmd == f.cmd) &&
             (parsed.seq == f.seq) && (parsed.len == f.len) &&
             (parsed.flags == f.flags);
        printf("[Test2] field round-trip -> %s\n", ok ? "PASS" : "FAIL");
        if (!ok) fail++;
    }

    /* Test 3: build/parse round trip, CMD_SET_TIME (7-byte payload) */
    {
        Frame f;
        uint8_t buf[64];
        uint16_t n;
        Frame parsed;
        FrameStatus st;
        /* 測試用途的 payload bytes，數值僅供 round-trip 測試，不代表真正 BCD 編碼 */
        uint8_t payload[7] = {0x20, 0x26, 0x08, 0x30, 0x12, 0x00, 0x00};
        int ok;

        memset(&f, 0, sizeof(f));
        f.ver = FRAME_VER;
        f.src = 0x00;
        f.dst = 0x01;
        f.cmd = CMD_SET_TIME;
        f.seq = 0x0007;
        f.len = 7;
        memcpy(f.payload, payload, 7);
        f.flags = 0;

        n = frame_build(&f, buf, sizeof(buf));
        printf("[Test3] frame_build len=%u bytes= ", n);
        print_bytes(buf, n);

        st = frame_parse(buf, n, &parsed);
        printf("[Test3] frame_parse status=%d (expect 0) -> %s\n",
               (int)st, (st == FRAME_OK) ? "PASS" : "FAIL");
        if (st != FRAME_OK) fail++;

        ok = (parsed.len == 7) && (memcmp(parsed.payload, payload, 7) == 0);
        printf("[Test3] payload round-trip -> %s\n", ok ? "PASS" : "FAIL");
        if (!ok) fail++;
    }

    /* Test 4: corrupted CRC must be rejected */
    {
        Frame f;
        uint8_t buf[64];
        uint16_t n;
        Frame parsed;
        FrameStatus st;

        memset(&f, 0, sizeof(f));
        f.ver = FRAME_VER;
        f.cmd = CMD_GET_TEMP;
        f.len = 0;

        n = frame_build(&f, buf, sizeof(buf));
        buf[n - 1] ^= 0xFF;   /* 故意打壞 CRC 最後一個 byte */

        st = frame_parse(buf, n, &parsed);
        printf("[Test4] corrupted CRC rejected -> %s\n",
               (st == FRAME_ERR_CRC) ? "PASS" : "FAIL");
        if (st != FRAME_ERR_CRC) fail++;
    }

    /* Test 5: bad SOF must be rejected */
    {
        uint8_t buf[12] = {0x00, 0x00, FRAME_VER, 0, 0, 0, 0, 0, 0, 0, 0, 0};
        Frame parsed;
        FrameStatus st = frame_parse(buf, sizeof(buf), &parsed);
        printf("[Test5] bad SOF rejected -> %s\n",
               (st == FRAME_ERR_SOF) ? "PASS" : "FAIL");
        if (st != FRAME_ERR_SOF) fail++;
    }

    printf("\n%s\n", (fail == 0) ? "ALL TESTS PASSED" : "SOME TESTS FAILED");
    return fail;
}
