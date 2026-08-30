/* ============================================================
 * main_stm32g431rb.c  ¢w µwÅé PWM¡A¨Ó¦^´`Àô + ¼È°± + ¥þÃöª©
 * NUCLEO-G431RB
 *
 * °¨¹F ¡÷ PB4  (TIM3_CH1¡A§CºAÅX°Ê)
 * LED  ¡÷ PB10 (TIM2_CH3¡A§CºAÅX°Ê)
 * °¨¹F«ö¶s ¡÷ PA10
 *   ²Ä1¦¸«ö¡G¶}©l¨Ó¦^´`Àô¡]0%¡÷100%¡÷0%...¡^
 *   ²Ä2¦¸«ö¡G¼È°±¡Aºû«ù·í«e %¼Æ
 *   ²Ä3¦¸«ö¡GÄ~Äò´`Àô
 * LED «ö¶s ¡÷ PB3¡]¦P¤WÅÞ¿è¡^
 * ¥þÃö«ö¶s ¡÷ PB5¡G°¨¹F + LED ¥ß¨è¦^ 0% §¹¥þÃö³¬
 *
 * ­·®°¨Ó¦^¶g´Á¡G30¬í¡]¨C 150ms ¨« 1%¡^
 * LED  ¨Ó¦^¶g´Á¡G15¬í¡]¨C  75ms ¨« 1%¡^
 * °¨¹F³Ì§C¿é¥X¡G30%¡]ªùÂe¥H¤W¤~Âà¡^
 * ============================================================ */

#include "main.h"

/* ¢w¢w ¸}¦ì ¢w¢w */
#define BTN_M_PORT   GPIOA
#define BTN_M_PIN    GPIO_PIN_10   /* °¨¹F«ö¶s PA10 */
#define BTN_L_PORT   GPIOB
#define BTN_L_PIN    GPIO_PIN_3    /* LED «ö¶s  PB3  */
#define BTN_OFF_PORT GPIOB
#define BTN_OFF_PIN  GPIO_PIN_5    /* ¥þÃö«ö¶s  PB5  */

/* ¢w¢w PWM °Ñ¼Æ ¢w¢w */
#define PWM_ARR               999U  /* 1kHz */
#define MOTOR_UPDATE_INTERVAL  300U  /* ms¡A30¬í¨Ó¦^ */
#define LED_UPDATE_INTERVAL    30U  /* ms¡A15¬í¨Ó¦^ */
#define MOTOR_MIN_PCT          35U  /* °¨¹F±Ò°ÊªùÂe % */

/* ¢w¢w §CºAÅX°Ê pct ¡÷ CCR¡]LED ¥Î¡^¢w¢w */
static inline uint32_t pct_to_ccr(uint8_t pct)
{
    if (pct == 0)   return PWM_ARR;
    if (pct >= 100) return 0U;
    return (uint32_t)((100U - pct) * 10U - 1U);
}

/* ¢w¢w §CºAÅX°Ê pct ¡÷ CCR¡]°¨¹F¥Î¡A¬M®g¨ì MIN~100¡^¢w¢w */
static inline uint32_t motor_pct_to_ccr(uint8_t pct)
{
    uint32_t actual = MOTOR_MIN_PCT
                    + (uint32_t)pct * (100U - MOTOR_MIN_PCT) / 100U;
    if (actual >= 100U) return 0U;
    return (uint32_t)((100U - actual) * 10U - 1U);
}

/* ¢w¢w Timer handle ¢w¢w */
TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;

/* ¢w¢w «ö¶sª¬ºA ¢w¢w */
typedef struct {
    uint8_t  last;
    uint32_t debounce;
} BtnState;

/* ¢w¢w ¨Ó¦^ª¬ºA ¢w¢w
 * state: 0=§¹¥þ°±¤î  1=´`Àô¤¤  2=¼È°±¡]ºû«ù·í«e%¡^
 * ¢w¢w */
typedef struct {
    uint8_t  state;      /* 0=°±¤î, 1=´`Àô, 2=¼È°± */
    uint8_t  pct;        /* ¥Ø«e¦Ê¤À¤ñ 0~100        */
    int8_t   dir;        /* +1=¤W¤É, -1=¤U­°        */
    uint32_t last_tick;
} SweepState;

/* ¢w¢w ¨ç¦¡«Å§i ¢w¢w */
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM3_Init(void);

/* ============================================================
 * main
 * ============================================================ */
int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_TIM2_Init();
    MX_TIM3_Init();

    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, PWM_ARR); /* °¨¹F¥þ°± */
    __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, PWM_ARR); /* LED º¶·À */
    HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_3);

    BtnState   btnM   = { (uint8_t)HAL_GPIO_ReadPin(BTN_M_PORT,   BTN_M_PIN),   0 };
    BtnState   btnL   = { (uint8_t)HAL_GPIO_ReadPin(BTN_L_PORT,   BTN_L_PIN),   0 };
    BtnState   btnOff = { (uint8_t)HAL_GPIO_ReadPin(BTN_OFF_PORT, BTN_OFF_PIN), 0 };

    SweepState motor  = { 0, 0,  1, 0 };
    SweepState led    = { 0, 0,  1, 0 };

    for (;;)
    {
        uint32_t now = HAL_GetTick();

        /* ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù
         * ¥þÃö«ö¶s PB5¡G°¨¹F + LED ¥ß¨è¦^ 0%
         * ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù */
        uint8_t nowOff = (uint8_t)HAL_GPIO_ReadPin(BTN_OFF_PORT, BTN_OFF_PIN);
        if (btnOff.last == 1 && nowOff == 0)
        {
            if ((now - btnOff.debounce) >= 300UL)
            {
                /* °¨¹F¥þ°± */
                motor.state = 0;
                motor.pct   = 0;
                motor.dir   = 1;
                __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, PWM_ARR);

                /* LED º¶·À */
                led.state = 0;
                led.pct   = 0;
                led.dir   = 1;
                __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, PWM_ARR);

                btnOff.debounce = now;
            }
        }
        btnOff.last = nowOff;

        /* ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù
         * °¨¹F«ö¶s PA10
         *   state 0¡]°±¤î¡^¡÷ 1¡]´`Àô¡^
         *   state 1¡]´`Àô¡^¡÷ 2¡]¼È°±¡Aºû«ù·í«e%¡^
         *   state 2¡]¼È°±¡^¡÷ 1¡]Ä~Äò´`Àô¡^
         * ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù */
        uint8_t nowM = (uint8_t)HAL_GPIO_ReadPin(BTN_M_PORT, BTN_M_PIN);
        if (btnM.last == 1 && nowM == 0)
        {
            if ((now - btnM.debounce) >= 300UL)
            {
                if (motor.state == 0)
                {
                    /* °±¤î ¡÷ ´`Àô¡G±q 0% °_¸õ */
                    motor.state     = 1;
                    motor.pct       = 0;
                    motor.dir       = 1;
                    motor.last_tick = now;
                    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1,
                                          motor_pct_to_ccr(0));
                }
                else if (motor.state == 1)
                {
                    /* ´`Àô ¡÷ ¼È°±¡Gºû«ù·í«e %¼Æ¡A¤£§ï CCR */
                    motor.state = 2;
                }
                else /* state == 2 */
                {
                    /* ¼È°± ¡÷ Ä~Äò´`Àô */
                    motor.state     = 1;
                    motor.last_tick = now;   /* ­«³] tick ¨¾¤îÀþ¶¡¸õ®æ */
                }
                btnM.debounce = now;
            }
        }
        btnM.last = nowM;

        /* ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù
         * LED «ö¶s PB3¡]¦P¤WÅÞ¿è¡^
         * ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù */
        uint8_t nowL = (uint8_t)HAL_GPIO_ReadPin(BTN_L_PORT, BTN_L_PIN);
        if (btnL.last == 1 && nowL == 0)
        {
            if ((now - btnL.debounce) >= 300UL)
            {
                if (led.state == 0)
                {
                    led.state     = 1;
                    led.pct       = 0;
                    led.dir       = 1;
                    led.last_tick = now;
                    __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, pct_to_ccr(0));
                }
                else if (led.state == 1)
                {
                    led.state = 2;
                }
                else
                {
                    led.state     = 1;
                    led.last_tick = now;
                }
                btnL.debounce = now;
            }
        }
        btnL.last = nowL;

        /* ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù
         * °¨¹F¨Ó¦^§ó·s¡]state==1 ¤~§ó·s¡^
         * ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù */
        if (motor.state == 1 && (now - motor.last_tick) >= MOTOR_UPDATE_INTERVAL)
        {
            motor.last_tick = now;
            motor.pct = (uint8_t)((int16_t)motor.pct + motor.dir);

            if (motor.pct >= 100) { motor.pct = 100; motor.dir = -1; }
            if (motor.pct == 0 && motor.dir == -1) { motor.dir = 1; }

            __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1,
                                  motor_pct_to_ccr(motor.pct));
        }

        /* ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù
         * LED ¨Ó¦^§ó·s¡]state==1 ¤~§ó·s¡^
         * ùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùùù */
        if (led.state == 1 && (now - led.last_tick) >= LED_UPDATE_INTERVAL)
        {
            led.last_tick = now;
            led.pct = (uint8_t)((int16_t)led.pct + led.dir);

            if (led.pct >= 100) { led.pct = 100; led.dir = -1; }
            if (led.pct == 0 && led.dir == -1) { led.dir = 1; }

            __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, pct_to_ccr(led.pct));
        }
    }
}

/* ============================================================
 * TIM3¡G°¨¹F PB4¡]TIM3_CH1¡^¡A1kHz
 * ============================================================ */
static void MX_TIM3_Init(void)
{
    __HAL_RCC_TIM3_CLK_ENABLE();
    TIM_OC_InitTypeDef sConfigOC = {0};

    htim3.Instance               = TIM3;
    htim3.Init.Prescaler         = 170 - 1;
    htim3.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim3.Init.Period            = PWM_ARR;
    htim3.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    if (HAL_TIM_PWM_Init(&htim3) != HAL_OK) Error_Handler();

    sConfigOC.OCMode     = TIM_OCMODE_PWM1;
    sConfigOC.Pulse      = PWM_ARR;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
    if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
        Error_Handler();
}

/* ============================================================
 * TIM2¡GLED PB10¡]TIM2_CH3¡^¡A1kHz
 * ============================================================ */
static void MX_TIM2_Init(void)
{
    __HAL_RCC_TIM2_CLK_ENABLE();
    TIM_OC_InitTypeDef sConfigOC = {0};

    htim2.Instance               = TIM2;
    htim2.Init.Prescaler         = 170 - 1;
    htim2.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim2.Init.Period            = PWM_ARR;
    htim2.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    if (HAL_TIM_PWM_Init(&htim2) != HAL_OK) Error_Handler();

    sConfigOC.OCMode     = TIM_OCMODE_PWM1;
    sConfigOC.Pulse      = PWM_ARR;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
    if (HAL_TIM_PWM_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_3) != HAL_OK)
        Error_Handler();
}

/* ============================================================
 * GPIO ªì©l¤Æ
 * ============================================================ */
static void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    /* PB4¡GTIM3_CH1 AF2¡]°¨¹F¡^*/
    GPIO_InitStruct.Pin       = GPIO_PIN_4;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_NOPULL;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF2_TIM3;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* PB10¡GTIM2_CH3 AF1¡]LED¡^*/
    GPIO_InitStruct.Pin       = GPIO_PIN_10;
    GPIO_InitStruct.Alternate = GPIO_AF1_TIM2;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* PA10¡G°¨¹F«ö¶s¡A¤º³¡¤W©Ô */
    GPIO_InitStruct.Pin       = BTN_M_PIN;
    GPIO_InitStruct.Mode      = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull      = GPIO_PULLUP;
    GPIO_InitStruct.Alternate = 0;
    HAL_GPIO_Init(BTN_M_PORT, &GPIO_InitStruct);

    /* PB3¡GLED «ö¶s¡A¤º³¡¤W©Ô */
    GPIO_InitStruct.Pin  = BTN_L_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(BTN_L_PORT, &GPIO_InitStruct);

    /* PB5¡G¥þÃö«ö¶s¡A¤º³¡¤W©Ô */
    GPIO_InitStruct.Pin  = BTN_OFF_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(BTN_OFF_PORT, &GPIO_InitStruct);
}

/* ============================================================
 * System Clock¡GHSI ¡÷ PLL ¡÷ 170 MHz
 * ============================================================ */
void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

    RCC_OscInitStruct.OscillatorType      = RCC_OSCILLATORTYPE_HSI;
    RCC_OscInitStruct.HSIState            = RCC_HSI_ON;
    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState        = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource       = RCC_PLLSOURCE_HSI;
    RCC_OscInitStruct.PLL.PLLM            = RCC_PLLM_DIV4;
    RCC_OscInitStruct.PLL.PLLN            = 85;
    RCC_OscInitStruct.PLL.PLLP            = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLQ            = RCC_PLLQ_DIV2;
    RCC_OscInitStruct.PLL.PLLR            = RCC_PLLR_DIV2;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) Error_Handler();

    RCC_ClkInitStruct.ClockType      = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                     | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource   = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider  = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK) Error_Handler();
}

/* ============================================================
 * Error Handler
 * ============================================================ */
void Error_Handler(void)
{
    __disable_irq();
    while (1) {}
}