#include "ina228.h"

/* ---- register map ---- */
#define REG_CONFIG       0x00U
#define REG_ADC_CONFIG   0x01U
#define REG_SHUNT_CAL    0x02U
#define REG_VBUS         0x05U
#define REG_CURRENT      0x07U
#define REG_POWER        0x08U
#define REG_ENERGY       0x09U
#define REG_CHARGE       0x0AU
#define REG_DIAG_ALRT    0x0BU
#define REG_MANUF_ID     0x3EU
#define REG_DEVICE_ID    0x3FU

/* ---- CONFIG bits ---- */
#define CFG_RST          (1U << 15)   /* full reset, self-clearing        */
#define CFG_RSTACC       (1U << 14)   /* clear ENERGY and CHARGE          */
#define CFG_ADCRANGE     (1U << 4)    /* 1: +/-40.96 mV, 0: +/-163.84 mV  */

/* ADC_CONFIG: MODE = 0xF (continuous VBUS + VSHUNT + TEMP),
 * VBUSCT = VSHCT = VTCT = 5 (1052 us), AVG = 3 (64 samples)  ->  0xFB6B */
#define ADC_CONFIG_VAL   ((0xFU << 12) | (5U << 9) | (5U << 6) | (5U << 3) | 3U)

#define I2C_TIMEOUT_MS   50U

/* ---- scale factors from the datasheet ---- */
#define VBUS_LSB_V       195.3125e-6      /* volts per VBUS LSB                                   */
#define SHUNT_CAL_K      13107.2e6        /* SHUNT_CAL = K * CURRENT_LSB * R_SHUNT (x4 at +/-40.96 mV) */
#define CURRENT_FS_CNT   524288.0         /* 2^19 counts correspond to max current                */

/* Reads nbytes (1..5) big-endian from a register. */
static HAL_StatusTypeDef read_reg(const INA228_t *d, uint8_t reg, uint8_t nbytes, uint64_t *out)
{
    uint8_t buf[5];
    uint64_t v = 0;
    HAL_StatusTypeDef st;

    if (nbytes == 0U || nbytes > 5U) {
        return HAL_ERROR;
    }
    st = HAL_I2C_Mem_Read(d->hi2c, d->addr, reg, I2C_MEMADD_SIZE_8BIT, buf, nbytes, I2C_TIMEOUT_MS);
    if (st != HAL_OK) {
        return st;
    }
    for (uint8_t i = 0; i < nbytes; i++) {
        v = (v << 8) | buf[i];
    }
    *out = v;
    return HAL_OK;
}

static HAL_StatusTypeDef write_reg16(const INA228_t *d, uint8_t reg, uint16_t val)
{
    uint8_t buf[2] = { (uint8_t)(val >> 8), (uint8_t)(val & 0xFFU) };

    return HAL_I2C_Mem_Write(d->hi2c, d->addr, reg, I2C_MEMADD_SIZE_8BIT, buf, 2, I2C_TIMEOUT_MS);
}

/* 20-bit two's complement -> int32_t */
static int32_t sign_extend_20(uint32_t v)
{
    v &= 0xFFFFFU;
    return (v & 0x80000U) ? ((int32_t)v - 0x100000) : (int32_t)v;
}

/* 40-bit two's complement -> int64_t */
static int64_t sign_extend_40(uint64_t v)
{
    v &= 0xFFFFFFFFFFULL;
    return (v & 0x8000000000ULL) ? ((int64_t)v - 0x10000000000LL) : (int64_t)v;
}

INA228_Status INA228_Init(INA228_t *dev, I2C_HandleTypeDef *hi2c, uint16_t addr,
                          double shunt_ohm, double max_current_a)
{
    uint64_t v;
    double vshunt_max, range_mult, cal;
    uint16_t cfg;

    if (dev == NULL || hi2c == NULL || shunt_ohm <= 0.0 || max_current_a <= 0.0) {
        return INA228_ERR_PARAM;
    }
    dev->hi2c = hi2c;
    dev->addr = addr;

    /* Is it really an INA228?  MANUFACTURER_ID = 0x5449 ("TI"), DEVICE_ID[15:4] = 0x228 */
    if (read_reg(dev, REG_MANUF_ID, 2, &v) != HAL_OK)  { return INA228_ERR_I2C; }
    if (v != 0x5449U)                                  { return INA228_ERR_ID;  }
    if (read_reg(dev, REG_DEVICE_ID, 2, &v) != HAL_OK) { return INA228_ERR_I2C; }
    if ((v >> 4) != 0x228U)                            { return INA228_ERR_ID;  }

    /* Pick the ADC range from the shunt voltage at max current. */
    vshunt_max = max_current_a * shunt_ohm;
    if (vshunt_max <= 0.04096) {
        cfg = (uint16_t)CFG_ADCRANGE;
        range_mult = 4.0;
    } else if (vshunt_max <= 0.16384) {
        cfg = 0U;
        range_mult = 1.0;
    } else {
        return INA228_ERR_PARAM;           /* shunt voltage would exceed +/-163.84 mV */
    }

    /* SHUNT_CAL = 13107.2e6 * CURRENT_LSB * R_SHUNT (x4 for the +/-40.96 mV range),
     * with CURRENT_LSB = max current / 2^19. It is a 15-bit register. */
    cal = SHUNT_CAL_K * (max_current_a / CURRENT_FS_CNT) * shunt_ohm * range_mult;
    if (cal < 1.0 || cal > 32767.0) {
        return INA228_ERR_PARAM;
    }
    dev->shunt_cal = (uint16_t)(cal + 0.5);
    dev->config = cfg;

    /* Use the CURRENT_LSB that the *rounded* SHUNT_CAL really produces,
     * so the rounding does not turn into a scale error. */
    dev->current_lsb = (double)dev->shunt_cal / (SHUNT_CAL_K * shunt_ohm * range_mult);

    if (write_reg16(dev, REG_CONFIG, (uint16_t)CFG_RST) != HAL_OK) { return INA228_ERR_I2C; }
    HAL_Delay(5);

    if (write_reg16(dev, REG_CONFIG,     dev->config)    != HAL_OK) { return INA228_ERR_I2C; }
    if (write_reg16(dev, REG_SHUNT_CAL,  dev->shunt_cal) != HAL_OK) { return INA228_ERR_I2C; }
    if (write_reg16(dev, REG_ADC_CONFIG, (uint16_t)ADC_CONFIG_VAL) != HAL_OK) { return INA228_ERR_I2C; }

    /* Read SHUNT_CAL back to make sure the writes landed. */
    if (read_reg(dev, REG_SHUNT_CAL, 2, &v) != HAL_OK) { return INA228_ERR_I2C; }
    if (v != dev->shunt_cal)                           { return INA228_ERR_I2C; }

    return INA228_OK;
}

INA228_Status INA228_Read(INA228_t *dev, INA228_Data_t *out)
{
    uint64_t vbus, cur, pwr, eng, chg, dia;

    if (dev == NULL || out == NULL) {
        return INA228_ERR_PARAM;
    }
    if (read_reg(dev, REG_VBUS,    3, &vbus) != HAL_OK) { return INA228_ERR_I2C; }
    if (read_reg(dev, REG_CURRENT, 3, &cur)  != HAL_OK) { return INA228_ERR_I2C; }
    if (read_reg(dev, REG_POWER,   3, &pwr)  != HAL_OK) { return INA228_ERR_I2C; }
    if (read_reg(dev, REG_ENERGY,  5, &eng)  != HAL_OK) { return INA228_ERR_I2C; }
    if (read_reg(dev, REG_CHARGE,  5, &chg)  != HAL_OK) { return INA228_ERR_I2C; }
    if (read_reg(dev, REG_DIAG_ALRT, 2, &dia) != HAL_OK) { return INA228_ERR_I2C; }

    /* VBUS and CURRENT are 20-bit values in bits 23:4. VBUS is never negative.
     * POWER is a plain 24-bit unsigned value, ENERGY a 40-bit unsigned one. */
    out->volts  = (double)((vbus >> 4) & 0xFFFFFU) * VBUS_LSB_V;
    out->amps   = (double)sign_extend_20((uint32_t)(cur >> 4)) * dev->current_lsb;
    out->watts  = (double)pwr * 3.2 * dev->current_lsb;
    out->joules = (double)eng * 16.0 * 3.2 * dev->current_lsb;
    out->coulombs = (double)sign_extend_40(chg) * dev->current_lsb;
    out->diag   = (uint16_t)dia;
    out->raw_ok = (uint8_t)((((vbus | cur) & 0xFU) == 0U) ? 1U : 0U);
    return INA228_OK;
}

INA228_Status INA228_ResetEnergy(INA228_t *dev)
{
    if (dev == NULL) {
        return INA228_ERR_PARAM;
    }
    /* Set RSTACC, then write the normal CONFIG back so the bit does not stay set. */
    if (write_reg16(dev, REG_CONFIG, (uint16_t)(dev->config | CFG_RSTACC)) != HAL_OK) { return INA228_ERR_I2C; }
    if (write_reg16(dev, REG_CONFIG, dev->config) != HAL_OK)                          { return INA228_ERR_I2C; }
    return INA228_OK;
}

INA228_Status INA228_VerifyConfig(INA228_t *dev)
{
    uint64_t v;

    if (dev == NULL) {
        return INA228_ERR_PARAM;
    }
    if (read_reg(dev, REG_CONFIG,     2, &v) != HAL_OK) { return INA228_ERR_I2C; }
    if ((v & CFG_ADCRANGE) != (dev->config & CFG_ADCRANGE)) { return INA228_ERR_CFG; }
    if (read_reg(dev, REG_SHUNT_CAL,  2, &v) != HAL_OK) { return INA228_ERR_I2C; }
    if (v != dev->shunt_cal)                            { return INA228_ERR_CFG; }
    if (read_reg(dev, REG_ADC_CONFIG, 2, &v) != HAL_OK) { return INA228_ERR_I2C; }
    if (v != (uint16_t)ADC_CONFIG_VAL)                  { return INA228_ERR_CFG; }
    return INA228_OK;
}