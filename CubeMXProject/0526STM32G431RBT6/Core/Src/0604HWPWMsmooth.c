/* ============================================================
 * main_stm32g431rb.c  ─ 硬體 PWM，自動來回循環版
 * NUCLEO-G431RB
 *
 * 馬達 → PB4  (TIM3_CH1，低態驅動)
 * LED  → PB10 (TIM2_CH3，低態驅動)
 * 馬達按鈕 → PA10（按一次開始循環，再按停止）
 * LED 按鈕  → PB3 （按一次開始循環，再按停止）
 *
 * 來回週期：5000ms（0→100→0）
 *   每 25ms 更新一次，共 200步
 *   0→100：100步 × 25ms = 2500ms
 *   100→0：100步 × 25ms = 2500ms
 *
 * PWM 頻率：1kHz，ARR=999
 * 低態驅動：pct=0 → CCR=999（不動），pct=100 → CCR=0（全速）
 * ============================================================ */

#include "main.h"

/* ── 腳位 ── */
#define BTN_M_PORT  GPIOA
#define BTN_M_PIN   GPIO_PIN_10
#define BTN_L_PORT  GPIOB
#define BTN_L_PIN   GPIO_PIN_3

/* ── PWM 參數 ── */
#define PWM_ARR         999U     /* 1kHz */
#define UPDATE_INTERVAL  25U     /* ms，每次更新間隔 */
#define STEP_PCT          1U     /* 每次更新增減 1% */

/* 低態驅動 pct → CCR */
static inline uint32_t pct_to_ccr(uint8_t pct)
{
    if (pct == 0)   return PWM_ARR;       /* 全 HIGH = 不動 */
    if (pct >= 100) return 0U;            /* 全 LOW  = 全速 */
    return (uint32_t)((100U - pct) * 10U - 1U);
}

/* ── Timer handle ── */
TIM_HandleTypeDef htim2;   /* LED  PB10 TIM2_CH3 */
TIM_HandleTypeDef htim3;   /* 馬達 PB4  TIM3_CH1 */

/* ── 按鈕狀態 ── */
typedef struct {
    uint8_t  last;
    uint32_t debounce;
} BtnState;

/* ── 來回狀態 ── */
typedef struct {
    uint8_t  running;    /* 0=停止，1=執行中 */
    uint8_t  pct;        /* 目前百分比 0~100 */
    int8_t   dir;        /* 方向：+1=上升，-1=下降 */
    uint32_t last_tick;  /* 上次更新時間 */
} SweepState;

/* ── 函式宣告 ── */
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

    /* 初始 0%（不動/熄滅）*/
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, pct_to_ccr(0));
    __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, pct_to_ccr(0));

    HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_3);

    BtnState   btnM = { (uint8_t)HAL_GPIO_ReadPin(BTN_M_PORT, BTN_M_PIN), 0 };
    BtnState   btnL = { (uint8_t)HAL_GPIO_ReadPin(BTN_L_PORT, BTN_L_PIN), 0 };

    SweepState motor = { 0, 0, 1, 0 };   /* 停止，0%，往上 */
    SweepState led   = { 0, 0, 1, 0 };

    for (;;)
    {
        uint32_t now = HAL_GetTick();

        /* ── 馬達按鈕 PA10 ── */
        uint8_t nowM = (uint8_t)HAL_GPIO_ReadPin(BTN_M_PORT, BTN_M_PIN);
        if (btnM.last == 1 && nowM == 0)
        {
            if ((now - btnM.debounce) >= 300UL)
            {
                if (!motor.running)
                {
                    /* 開始循環 */
                    motor.running   = 1;
                    motor.pct       = 0;
                    motor.dir       = 1;
                    motor.last_tick = now;
                    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, pct_to_ccr(0));
                }
                else
                {
                    /* 停止，回到 0% */
                    motor.running = 0;
                    motor.pct     = 0;
                    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, pct_to_ccr(0));
                }
                btnM.debounce = now;
            }
        }
        btnM.last = nowM;

        /* ── LED 按鈕 PB3 ── */
        uint8_t nowL = (uint8_t)HAL_GPIO_ReadPin(BTN_L_PORT, BTN_L_PIN);
        if (btnL.last == 1 && nowL == 0)
        {
            if ((now - btnL.debounce) >= 300UL)
            {
                if (!led.running)
                {
                    led.running   = 1;
                    led.pct       = 0;
                    led.dir       = 1;
                    led.last_tick = now;
                    __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, pct_to_ccr(0));
                }
                else
                {
                    led.running = 0;
                    led.pct     = 0;
                    __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, pct_to_ccr(0));
                }
                btnL.debounce = now;
            }
        }
        btnL.last = nowL;

        /* ── 馬達來回更新（每 25ms 走 1%）── */
        if (motor.running && (now - motor.last_tick) >= UPDATE_INTERVAL)
        {
            motor.last_tick = now;
            motor.pct = (uint8_t)((int16_t)motor.pct + motor.dir);

            if (motor.pct >= 100) { motor.pct = 100; motor.dir = -1; }
            if (motor.pct == 0  && motor.dir == -1) { motor.pct = 0; motor.dir = 1; }

            __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, pct_to_ccr(motor.pct));
        }

        /* ── LED 來回更新（每 25ms 走 1%）── */
        if (led.running && (now - led.last_tick) >= UPDATE_INTERVAL)
        {
            led.last_tick = now;
            led.pct = (uint8_t)((int16_t)led.pct + led.dir);

            if (led.pct >= 100) { led.pct = 100; led.dir = -1; }
            if (led.pct == 0   && led.dir == -1) { led.pct = 0; led.dir = 1; }

            __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, pct_to_ccr(led.pct));
        }
    }
}

/* ============================================================
 * TIM3：馬達 PB4（TIM3_CH1），1kHz
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
 * TIM2：LED PB10（TIM2_CH3），1kHz
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
 * GPIO 初始化
 * ============================================================ */
static void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    /* PB4：TIM3_CH1 AF2 */
    GPIO_InitStruct.Pin       = GPIO_PIN_4;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_NOPULL;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF2_TIM3;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* PB10：TIM2_CH3 AF1 */
    GPIO_InitStruct.Pin       = GPIO_PIN_10;
    GPIO_InitStruct.Alternate = GPIO_AF1_TIM2;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* PA10：馬達按鈕，內部上拉 */
    GPIO_InitStruct.Pin       = BTN_M_PIN;
    GPIO_InitStruct.Mode      = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull      = GPIO_PULLUP;
    GPIO_InitStruct.Alternate = 0;
    HAL_GPIO_Init(BTN_M_PORT, &GPIO_InitStruct);

    /* PB3：LED 按鈕，內部上拉 */
    GPIO_InitStruct.Pin  = BTN_L_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(BTN_L_PORT, &GPIO_InitStruct);
}

/* ============================================================
 * System Clock：HSI → PLL → 170 MHz
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