/**
 * INA228 driver for STM32 HAL (blocking I2C), written for the STM32G431RB.
 *
 * Fixed setup:
 *   - continuous mode: VBUS + VSHUNT + die temperature
 *   - 1052 us conversion time each, 64x averaging -> a new result about every 0.2 s
 *   - ADCRANGE is chosen automatically: +/-40.96 mV when the shunt voltage at max
 *     current stays inside it (4x finer resolution), otherwise +/-163.84 mV
 *
 * ENERGY / CHARGE only accumulate in continuous mode, the only mode used here.
 */
#ifndef INA228_H
#define INA228_H

#include <stdint.h>
#include "stm32g4xx_hal.h"

#ifdef __cplusplus
extern "C" {
#endif

/* HAL wants the 7-bit address shifted left by one. A1 = A0 = GND -> 0x40. */
#define INA228_ADDR(a7)       ((uint16_t)((a7) << 1))
#define INA228_ADDR_DEFAULT   INA228_ADDR(0x40U)

typedef enum {
    INA228_OK = 0,
    INA228_ERR_I2C,      /* 1: no ACK, bus error or timeout */
    INA228_ERR_ID,       /* 2: a device answered, but it is not an INA228 */
    INA228_ERR_PARAM,    /* 3: shunt / max current cannot be represented */
    INA228_ERR_CFG       /* 4: SHUNT_CAL / ADC_CONFIG / ADCRANGE no longer match what Init wrote */
} INA228_Status;

typedef struct {
    I2C_HandleTypeDef *hi2c;
    uint16_t addr;           /* HAL (shifted) address */
    uint16_t config;         /* CONFIG value in use (holds the ADCRANGE bit) */
    uint16_t shunt_cal;      /* value written to SHUNT_CAL */
    double   current_lsb;    /* amps per CURRENT-register LSB, derived from shunt_cal */
} INA228_t;

typedef struct {
    double   volts;          /* V */
    double   amps;           /* A, signed */
    double   watts;          /* W */
    double   joules;         /* J accumulated since the last reset */
    double   coulombs;       /* C, CHARGE register: integral of the current, signed */
    uint16_t diag;           /* DIAG_ALRT (0x0B) */
    uint8_t  raw_ok;         /* 1 = the 4 reserved LSBs of the VBUS / CURRENT reads were 0 */
} INA228_Data_t;

/* Resets the chip and configures it.
 * max_current_a sets the resolution (CURRENT_LSB = max / 2^19) and the largest current
 * that can be reported, so leave headroom for start-up / stall current. 5.12 A with a 2 mOhm
 * shunt gives SHUNT_CAL = 1024 exactly. */
INA228_Status INA228_Init(INA228_t *dev, I2C_HandleTypeDef *hi2c, uint16_t addr,
                          double shunt_ohm, double max_current_a);

/* Reads VBUS, CURRENT, POWER and ENERGY (four short I2C transactions). */
INA228_Status INA228_Read(INA228_t *dev, INA228_Data_t *out);

/* Clears the ENERGY and CHARGE accumulators. */
INA228_Status INA228_ResetEnergy(INA228_t *dev);

/* Re-reads SHUNT_CAL, ADC_CONFIG and the ADCRANGE bit. INA228_ERR_CFG = the chip was reset or a register was overwritten. */
INA228_Status INA228_VerifyConfig(INA228_t *dev);

#ifdef __cplusplus
}
#endif

#endif /* INA228_H */