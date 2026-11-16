/*
 * fan_sweep.h -- duty staircase generator for steady-state characterization:
 *
 *   0% -> 10% -> 20% -> ... -> 90% -> 100%   (each held 1 min, 100% held 2 min)
 *   100% -> 90% -> 80% -> ... -> 10%          (each held 1 min)
 *   -> back to 0% (= first step of the next lap), repeating forever
 *
 * One full lap takes 21 minutes (10x60s rising + 1x120s at 100% + 9x60s
 * falling). Because it repeats, every duty level gets sampled on both the
 * rising and falling leg each lap, and 100% gets its own 2-minute dwell
 * every lap -- not just once from a single pass.
 *
 * Pure duty-pattern logic; does not touch the timers itself -- read
 * fan_sweep_duty() each loop and feed it to fan_set_duty_both() yourself.
 */

#ifndef FAN_SWEEP_H
#define FAN_SWEEP_H

#include <stdint.h>

void fan_sweep_init(void);     /* call once, e.g. right after fan_control_init() */
void fan_sweep_update(void);   /* call every main-loop iteration */
uint8_t fan_sweep_duty(void);  /* current duty 0..100 (holds steady during each dwell) */

#endif /* FAN_SWEEP_H */
