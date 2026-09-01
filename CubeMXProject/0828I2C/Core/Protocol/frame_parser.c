/**
  ******************************************************************************
  * @file    frame_parser.c
  * @brief   RTC3231 通訊協定 — CRC16 + Frame build/parse 實作
  ******************************************************************************
  */
#include "frame_parser.h"
#include <stddef.h>

uint16_t crc16(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFFu;
    uint16_t i;
    uint8_t  bit;

    for (i = 0u; i < len; i++)
    {
        crc = (uint16_t)(crc ^ ((uint16_t)data[i] << 8));
        for (bit = 0u; bit < 8u; bit++)
        {
            if ((crc & 0x8000u) != 0u)
            {
                crc = (uint16_t)((crc << 1) ^ 0x1021u);
            }
            else
            {
                crc = (uint16_t)(crc << 1);
            }
        }
    }
    return crc;
}

uint16_t frame_build(const Frame *f, uint8_t *out_buf, uint16_t out_buf_size)
{
    uint16_t total_len;
    uint16_t idx;
    uint16_t crc_start;
    uint16_t crc_len;
    uint16_t crc;
    uint8_t  i;

    if ((f == NULL) || (out_buf == NULL))
    {
        return 0u;
    }
    if (f->len > FRAME_PAYLOAD_MAX)
    {
        return 0u;
    }

    total_len = (uint16_t)(FRAME_MIN_LEN + f->len);
    if (out_buf_size < total_len)
    {
        return 0u;
    }

    idx = 0u;
    out_buf[idx++] = FRAME_SOF0;
    out_buf[idx++] = FRAME_SOF1;

    crc_start = idx;                              /* CRC 從 VER 開始算 */
    out_buf[idx++] = f->ver;
    out_buf[idx++] = f->src;
    out_buf[idx++] = f->dst;
    out_buf[idx++] = f->cmd;
    out_buf[idx++] = (uint8_t)(f->seq >> 8);       /* SEQ big-endian, high byte first */
    out_buf[idx++] = (uint8_t)(f->seq & 0xFFu);    /* SEQ big-endian, low byte */
    out_buf[idx++] = f->len;

    for (i = 0u; i < f->len; i++)
    {
        out_buf[idx++] = f->payload[i];
    }

    out_buf[idx++] = f->flags;

    crc_len = (uint16_t)(idx - crc_start);         /* = FRAME_CRC_FIXED_LEN + f->len */
    crc = crc16(&out_buf[crc_start], crc_len);

    out_buf[idx++] = (uint8_t)(crc >> 8);          /* CRC big-endian, high byte first */
    out_buf[idx++] = (uint8_t)(crc & 0xFFu);       /* CRC big-endian, low byte */

    return idx;                                     /* == total_len */
}

FrameStatus frame_parse(const uint8_t *raw, uint16_t raw_len, Frame *out_frame)
{
    uint16_t idx;
    uint16_t crc_start;
    uint16_t crc_len;
    uint16_t calc_crc;
    uint16_t recv_crc;
    uint16_t expected_total;
    uint8_t  ver, src, dst, cmd, len, flags;
    uint16_t seq;
    const uint8_t *payload_ptr;
    uint8_t  i;

    if ((raw == NULL) || (out_frame == NULL))
    {
        return FRAME_ERR_LEN;
    }
    if (raw_len < FRAME_MIN_LEN)
    {
        return FRAME_ERR_LEN;
    }
    if ((raw[0] != FRAME_SOF0) || (raw[1] != FRAME_SOF1))
    {
        return FRAME_ERR_SOF;
    }

    idx = 2u;
    crc_start = idx;                               /* VER 開始算 CRC */

    ver = raw[idx++];
    if (ver != FRAME_VER)
    {
        return FRAME_ERR_VER;
    }
    src = raw[idx++];
    dst = raw[idx++];
    cmd = raw[idx++];
    seq = (uint16_t)(((uint16_t)raw[idx] << 8) | raw[idx + 1]);    /* SEQ big-endian */
    idx = (uint16_t)(idx + 2);
    len = raw[idx++];

    if (len > FRAME_PAYLOAD_MAX)
    {
        return FRAME_ERR_LEN;
    }

    expected_total = (uint16_t)(FRAME_MIN_LEN + len);
    if (raw_len < expected_total)
    {
        return FRAME_ERR_LEN;
    }

    payload_ptr = &raw[idx];
    idx = (uint16_t)(idx + len);
    flags = raw[idx++];

    crc_len = (uint16_t)(idx - crc_start);          /* = FRAME_CRC_FIXED_LEN + len */
    calc_crc = crc16(&raw[crc_start], crc_len);
    recv_crc = (uint16_t)(((uint16_t)raw[idx] << 8) | raw[idx + 1]);   /* CRC big-endian */

    if (calc_crc != recv_crc)
    {
        return FRAME_ERR_CRC;
    }

    out_frame->ver   = ver;
    out_frame->src   = src;
    out_frame->dst   = dst;
    out_frame->cmd   = cmd;
    out_frame->seq   = seq;
    out_frame->len   = len;
    for (i = 0u; i < len; i++)
    {
        out_frame->payload[i] = payload_ptr[i];
    }
    out_frame->flags = flags;

    return FRAME_OK;
}
