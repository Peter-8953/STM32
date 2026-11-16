/*
 * rpm_sweep.h -- closed-loop RPM staircase generator for steady-state
 * characterization:
 *
 *   0% -> 10% -> 20% -> ... -> 90% -> 100%   (each held 30 s, 100% held 60 s)
 *   100% -> 90% -> 80% -> ... -> 10%         (each held 30 s)
 *   -> back to 0% (= first step of the next lap), repeating forever
 *
 * Drives rpm_ctrl_set_percent(), so the fan stays in closed loop while the
 * target speed sweeps through its 0..100 % range.  Call rpm_sweep_update()
 * every main-loop iteration; it is a no-op while calibration is running.
 */
#ifndef RPM_SWEEP_H
#define RPM_SWEEP_H

#include <stdint.h>

void rpm_sweep_init(void);          /* optional: resets the staircase state            */
void rpm_sweep_update(void);        /* call every main-loop iteration                 */

/* runtime enable/disable for automatic characterization vs manual UART control */
void rpm_sweep_set_enable(uint8_t en);
uint8_t rpm_sweep_is_enabled(void);

#endif /* RPM_SWEEP_H */
