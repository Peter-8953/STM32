#include "fan_sweep.h"
#include "main.h"   /* HAL_GetTick() */

typedef struct {
    uint8_t  duty;
    uint32_t dwell_ms;
} sweep_step_t;

/* see fan_sweep.h for the shape of this sequence */
static const sweep_step_t sweep_table[] = {
    {  0, 60000UL}, { 10, 60000UL}, { 20, 60000UL}, { 30, 60000UL}, { 40, 60000UL},
    { 50, 60000UL}, { 60, 60000UL}, { 70, 60000UL}, { 80, 60000UL}, { 90, 60000UL},
    {100,120000UL},   /* peak: double dwell */
    { 90, 60000UL}, { 80, 60000UL}, { 70, 60000UL}, { 60, 60000UL}, { 50, 60000UL},
    { 40, 60000UL}, { 30, 60000UL}, { 20, 60000UL}, { 10, 60000UL},
};
#define SWEEP_STEP_COUNT (sizeof(sweep_table) / sizeof(sweep_table[0]))

static uint8_t  step_index;
static uint32_t step_start_tick;

void fan_sweep_init(void)
{
    step_index = 0;
    step_start_tick = HAL_GetTick();
}

void fan_sweep_update(void)
{
    /* unsigned subtraction: correct even across HAL_GetTick() wraparound */
    uint32_t elapsed = HAL_GetTick() - step_start_tick;

    if (elapsed >= sweep_table[step_index].dwell_ms) {
        step_index++;
        if (step_index >= SWEEP_STEP_COUNT) {
            step_index = 0;   /* lap complete: back to 0%, loop forever */
        }
        /* reset to *now*, not step_start_tick += dwell_ms: guarantees every
           step dwells at least its full duration even if update() was
           called a little late, rather than accumulating a schedule and
           potentially skipping through steps to "catch up" */
        step_start_tick = HAL_GetTick();
    }
}

uint8_t fan_sweep_duty(void)
{
    return sweep_table[step_index].duty;
}
