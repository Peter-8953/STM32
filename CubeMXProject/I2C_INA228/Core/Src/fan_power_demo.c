/**
 * Fan power logger v2: INA228 + R002 (2 mOhm) in the +12 V line of a 4-pin fan.
 *
 * Hook into the CubeMX-generated main.c:
 *     void FanPower_Init(void);          // prototypes, e.g. in USER CODE BEGIN PFP
 *     void FanPower_Task(void);
 *     void FanPower_ResetEnergy(void);
 *     ...
 *     FanPower_Init();                   // USER CODE BEGIN BSP (after BSP_COM_Init(), so the log UART is open)
 *     while (1) {
 *         if (BspButtonState == BUTTON_PRESSED) {
 *             BspButtonState = BUTTON_RELEASED;
 *             FanPower_ResetEnergy();    // USER button = start a new run (E and Q from 0)
 *         }
 *         FanPower_Task();               // USER CODE BEGIN 3
 *     }
 *
 * Output (115200 8N1): CSV, one line every PRINT_PERIOD_MS, integers only. Lines starting with '#'
 * are comments (init result, new run, read error).
 *     # t_ms,vbus_mV,i_mA,p_mW,e_mJ,iavg_mA,pavg_mW,flags
 *     30010,12128,267,3236,231827,267,3236,0x00
 *   vbus / i / p   latest INA228 result window (about 0.2 s, 64 averages). |I| < I_DEADBAND_A shows 0.
 *   e_mJ           ENERGY since FanPower_Init() / FanPower_ResetEnergy(), in mJ (32-bit: ~1190 Wh).
 *   iavg / pavg    exact mean current / power over the whole print interval: dQ/dt and dE/dt from the
 *                  CHARGE and ENERGY accumulators, so no conversion window is missed. dt comes from
 *                  HAL_GetTick(), i.e. the MCU clock; E and Q themselves do not depend on it.
 *   flags          0x00 = every self-check passed
 *     0x01  DIAG_ALRT: MEMSTAT = 0, or MATHOF / CHARGEOF / ENERGYOF set (chip reports a problem)
 *     0x02  reserved low bits of VBUS / CURRENT were not 0 (bit error on the I2C bus)
 *     0x04  ENERGY went backwards (reset, power loss or a bad read)
 *     0x08  dE/dQ is outside the bus-voltage range: energy added without charge (chip / bus glitch)
 *     0x10  mean current over the interval is far above what the printed windows show (a real burst)
 *     0x20  SHUNT_CAL / ADC_CONFIG / ADCRANGE changed: the chip is re-initialised on the next period
 *
 * Errors: a failed read prints "# INA228 read error" and is simply retried. After MAX_READ_FAILS in a
 * row the chip is re-initialised, which also clears E. A failed init is retried every 2 s; the first
 * "no ACK" failure also prints an I2C scan (which 7-bit addresses answer).
 */
#include "main.h"
#include "ina228.h"
#include <stdio.h>
#include <string.h>

/* ---------------- adjust for your project ---------------- */
extern I2C_HandleTypeDef  hi2c1;       /* I2C instance the INA228 is on                          */
/* NUCLEO-G431RB: the BSP's COM1 is the ST-LINK virtual COM port (LPUART1). It is opened by
 * BSP_COM_Init() in main.c; hcom_uart[] is declared in stm32g4xx_nucleo.h (included via main.h). */
#define LOG_UART          hcom_uart[COM1]
#define INA228_I2C_ADDR   INA228_ADDR_DEFAULT   /* A1 = A0 = GND -> 0x40; use INA228_ADDR(0x41U) etc. if the address pins are strapped differently */
#define SHUNT_OHM         0.002        /* R002 = 2 mOhm; trim after checking against a multimeter */
#define MAX_CURRENT_A     5.12         /* headroom for start-up / stall current; 5.12 A -> SHUNT_CAL = 1024 */
#define PRINT_PERIOD_MS   500U
#define MAX_READ_FAILS    3U           /* consecutive failed reads before the chip is re-initialised */
#define VERIFY_EVERY      20U          /* re-read SHUNT_CAL / ADC_CONFIG / ADCRANGE every N prints   */
#define I_DEADBAND_A      0.001        /* |I| below this is shown as 0 mA / 0 mW (offset + noise)    */
/* --------------------------------------------------------- */

/* last column of the CSV line: 0x00 = every self-check passed */
#define FLAG_DIAG    0x01U      /* DIAG_ALRT: MEMSTAT = 0, or MATHOF / CHARGEOF / ENERGYOF set      */
#define FLAG_RAW     0x02U      /* reserved low bits of a raw read were not 0 -> bit error on the bus */
#define FLAG_E_BACK  0x04U      /* ENERGY went backwards (reset, power loss or bad read)             */
#define FLAG_VEFF    0x08U      /* dE/dQ outside the bus-voltage range: energy without charge        */
#define FLAG_BURST   0x10U      /* mean current over the interval >> what the printed windows show   */
#define FLAG_CFG     0x20U      /* SHUNT_CAL / ADC_CONFIG / ADCRANGE changed -> chip is re-initialised */

static INA228_t ina;
static uint8_t  ready;          /* 1 once INA228_Init() has succeeded */
static uint8_t  fail_cnt;       /* consecutive failed reads           */
static uint8_t  scanned;        /* 1 once the I2C bus scan has been printed */
static uint8_t  verify_cnt;     /* prints since the last config read-back   */
static uint8_t  have_prev;      /* 1 once there is a previous sample to compare with */
static uint32_t t_next_ms;      /* next time to print                 */
static uint32_t prev_t_ms;      /* time of the previous good sample   */
static double   prev_j, prev_c, prev_v, prev_i;   /* previous E [J], Q [C], VBUS [V], I [A] */

static void log_str(const char *s)
{
    HAL_UART_Transmit(&LOG_UART, (uint8_t *)s, (uint16_t)strlen(s), 100);
}

/* Lists every 7-bit address that ACKs, to tell "the INA228 is there but on another address"
 * from "nothing answers at all" (power, SDA/SCL wiring or pins, pull-ups). */
static void scan_i2c(void)
{
    char s[12];
    uint8_t a7;
    uint8_t found = 0;

    log_str("I2C1 scan:");
    for (a7 = 0x08U; a7 < 0x78U; a7++) {
        if (HAL_I2C_IsDeviceReady(&hi2c1, (uint16_t)(a7 << 1), 1, 5) == HAL_OK) {
            snprintf(s, sizeof s, " 0x%02X", (unsigned)a7);
            log_str(s);
            found = 1;
        }
    }
    log_str(found ? "\r\n" : " none\r\n");
}

static void try_init(void)
{
    char line[64];
    INA228_Status st = INA228_Init(&ina, &hi2c1, INA228_I2C_ADDR, SHUNT_OHM, MAX_CURRENT_A);

    ready      = (st == INA228_OK);
    fail_cnt   = 0;
    verify_cnt = 0;
    have_prev  = 0;                                      /* ENERGY / CHARGE restart from 0 */
    t_next_ms  = HAL_GetTick() + (ready ? 300U : 2000U); /* first result takes ~0.2 s; retry a failure every 2 s */

    /* code: 1 = no ACK (wiring / address / pull-ups), 2 = not an INA228, 3 = bad shunt / current setting */
    snprintf(line, sizeof line, "# INA228 init %s (code %d)\r\n", ready ? "OK" : "FAILED", (int)st);
    log_str(line);

    if (st == INA228_ERR_I2C && !scanned) {     /* nothing answered: show who is on the bus, once */
        scanned = 1;
        scan_i2c();
    }
}

void FanPower_Init(void)
{
    HAL_Delay(10);              /* let the INA228 finish power-up */
    log_str("# t_ms,vbus_mV,i_mA,p_mW,e_mJ,iavg_mA,pavg_mW,flags\r\n");
    try_init();
}

void FanPower_ResetEnergy(void)
{
    if (ready && INA228_ResetEnergy(&ina) == INA228_OK) {
        have_prev = 0;          /* E and Q start again from 0: re-baseline, do not flag the step */
        log_str("# new run: E and Q cleared\r\n");
    }
}

static double absd(double x)
{
    return (x < 0.0) ? -x : x;
}

void FanPower_Task(void)
{
    uint32_t now = HAL_GetTick();
    INA228_Data_t d;
    char line[96];
    uint8_t flags = 0U;
    double i_avg = 0.0, p_avg = 0.0;
    unsigned long mv, mw, ej_mj;
    long ma, ia_ma, pa_mw;

    if ((int32_t)(now - t_next_ms) < 0) {
        return;
    }
    t_next_ms = now + PRINT_PERIOD_MS;

    if (!ready) {
        try_init();
        return;
    }
    if (INA228_Read(&ina, &d) != INA228_OK) {
        log_str("# INA228 read error\r\n");
        if (++fail_cnt >= MAX_READ_FAILS) {
            ready = 0;          /* chip or bus is really gone: re-initialise on the next period */
        }
        return;
    }
    fail_cnt = 0;

    /* ---- self-checks on the chip ---- */
    if (!d.raw_ok) {
        flags |= FLAG_RAW;
    }
    if ((d.diag & 0x0001U) == 0U || (d.diag & 0x0E00U) != 0U) {   /* MEMSTAT = 0, or MATHOF / CHARGEOF / ENERGYOF */
        flags |= FLAG_DIAG;
    }
    if (++verify_cnt >= VERIFY_EVERY) {
        verify_cnt = 0;
        if (INA228_VerifyConfig(&ina) == INA228_ERR_CFG) {
            flags |= FLAG_CFG;
        }
    }

    /* ---- reconcile ENERGY with CHARGE over the whole print interval ---- */
    if (have_prev) {
        double dt   = (double)(now - prev_t_ms) / 1000.0;
        double dE   = d.joules   - prev_j;
        double dQ   = d.coulombs - prev_c;
        double i_hi = (absd(d.amps) > absd(prev_i)) ? absd(d.amps) : absd(prev_i);

        i_avg = dQ / dt;                    /* exact mean current over the interval */
        p_avg = dE / dt;                    /* exact mean power over the interval   */

        if (dE < 0.0) {
            flags |= FLAG_E_BACK;
        }
        if (dQ > 0.002) {                   /* >= ~200 counts, so the ratio means something */
            double v_eff = dE / dQ;         /* energy-weighted bus voltage over the interval */
            double v_hi  = 1.1 * ((d.volts > prev_v) ? d.volts : prev_v);
            double v_lo  = 0.5 * ((d.volts < prev_v) ? d.volts : prev_v);

            if (v_eff > v_hi || v_eff < v_lo) {
                flags |= FLAG_VEFF;         /* energy jumped without matching charge */
            }
        }
        if (i_avg > 3.0 * i_hi + 0.05) {
            flags |= FLAG_BURST;            /* real charge drawn between two printed windows */
        }
    }
    have_prev = 1U;
    prev_t_ms = now;
    prev_j = d.joules;  prev_c = d.coulombs;  prev_v = d.volts;  prev_i = d.amps;

    /* display only: below the shunt offset / noise floor the numbers are meaningless */
    if (absd(d.amps) < I_DEADBAND_A) {
        d.amps  = 0.0;
        d.watts = 0.0;
    }

    mv    = (unsigned long)(d.volts * 1000.0 + 0.5);
    ma    = (long)(d.amps * 1000.0 + (d.amps >= 0.0 ? 0.5 : -0.5));
    mw    = (unsigned long)(d.watts * 1000.0 + 0.5);
    ej_mj = (unsigned long)(d.joules * 1000.0 + 0.5);
    ia_ma = (long)(i_avg * 1000.0 + (i_avg >= 0.0 ? 0.5 : -0.5));
    pa_mw = (long)(p_avg * 1000.0 + (p_avg >= 0.0 ? 0.5 : -0.5));

    snprintf(line, sizeof line, "%lu,%lu,%ld,%lu,%lu,%ld,%ld,0x%02X\r\n",
             (unsigned long)now, mv, ma, mw, ej_mj, ia_ma, pa_mw, (unsigned)flags);
    log_str(line);

    if ((flags & FLAG_CFG) != 0U) {
        ready = 0;              /* registers no longer match what Init wrote: re-initialise */
    }
}