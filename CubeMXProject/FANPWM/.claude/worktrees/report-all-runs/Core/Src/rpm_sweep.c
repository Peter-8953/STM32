#include "rpm_sweep.h"
#include "main.h"
#include "rpm_ctrl.h"

typedef struct {
    uint8_t  percent;
    uint32_t dwell_ms;
} rpm_step_t;

static const rpm_step_t rpm_table[] = {
    {  0, 30000UL}, { 10, 30000UL}, { 20, 30000UL}, { 30, 30000UL}, { 40, 30000UL},
    { 50, 30000UL}, { 60, 30000UL}, { 70, 30000UL}, { 80, 30000UL}, { 90, 30000UL},
    {100,60000UL},   /* peak: double dwell */
    { 90, 30000UL}, { 80, 30000UL}, { 70, 30000UL}, { 60, 30000UL}, { 50, 30000UL},
    { 40, 30000UL}, { 30, 30000UL}, { 20, 30000UL}, { 10, 30000UL},
};
#define RPM_STEP_COUNT (sizeof(rpm_table) / sizeof(rpm_table[0]))

static uint8_t  s_started = 0U;
static uint8_t  s_step     = 0U;
static uint32_t s_step_start_tick = 0U;

/* runtime enable: 1 = automatic sweep, 0 = manual UART control only */
static uint8_t  s_auto_sweep = 1U;

void rpm_sweep_init(void)
{
    s_started = 0U;
    s_step    = 0U;
}

void rpm_sweep_set_enable(uint8_t en)
{
    s_auto_sweep = en ? 1U : 0U;
    /* reset staircase state so re-enable starts cleanly */
    s_started = 0U;
    s_step    = 0U;
}

uint8_t rpm_sweep_is_enabled(void)
{
    return s_auto_sweep;
}

void rpm_sweep_update(void)
{
    if (!s_auto_sweep)
    {
        return;   /* manual UART mode: do not overwrite target */
    }

    if (rpm_ctrl_is_calibrating() || rpm_ctrl_is_failed())
    {
        /* let calibration finish first; reset so we restart at 0% afterwards */
        s_started = 0U;
        return;
    }

    uint32_t now = HAL_GetTick();

    if (!s_started)
    {
        s_started         = 1U;
        s_step            = 0U;
        s_step_start_tick = now;
        rpm_ctrl_set_percent((float)rpm_table[s_step].percent);
        return;
    }

    uint32_t elapsed = now - s_step_start_tick;
    if (elapsed >= rpm_table[s_step].dwell_ms)
    {
        s_step++;
        if (s_step >= RPM_STEP_COUNT)
        {
            s_step = 0U;
        }
        s_step_start_tick = now;
        rpm_ctrl_set_percent((float)rpm_table[s_step].percent);
    }
}
