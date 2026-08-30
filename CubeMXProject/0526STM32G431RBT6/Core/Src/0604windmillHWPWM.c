/* ============================================================
 * main_stm32g431rb.c  ─ 硬體 PWM 版
 * NUCLEO-G431RB
 *
 * 馬達 → PB4  (TIM3_CH1，低態驅動：duty 越小轉越快)
 * LED  → PB10 (TIM2_CH3，低態驅動：duty 越小越亮)
 * 馬達按鈕 → PA10（每按一次 +10%，100%後回到 0%）
 * LED 按鈕  → PB3 （每按一次 +10%，100%後回到 0%）
 *
 * PWM 頻率：1 kHz（週期 1000us）
 * ARR = 999，CCR = 0~999
 *
 * 低態驅動：
 *   CCR = 0   → 全 LOW  = 100% 動作
 *   CCR = 999 → 全 HIGH =   0% 動作
 *   CCR = (100 - pct) * 10 - 1
 * ============================================================ */

#include "main.h"

/* ── 腳位 ── */
#define BTN_M_PORT  GPIOA
#define BTN_M_PIN   GPIO_PIN_10   /* 馬達按鈕 PA10 */

#define BTN_L_PORT  GPIOB
#define BTN_L_PIN   GPIO_PIN_3    /* LED 按鈕 PB3  */

/* ── PWM 參數 ── */
#define PWM_ARR     999U          /* 計數器上限，週期 = (ARR+1)/170MHz*Prescaler */
#define PWM_FREQ_HZ 1000U         /* 目標 1kHz */
#define PWM_STEP    10U           /* 每次按鈕增加 10% */

/* ── 低態驅動：pct% → CCR 換算 ──
 * pct=0   → CCR=999 (全 HIGH = 不動)
 * pct=100 → CCR=0   (全 LOW  = 全速)
 * ────────────────────────────────── */
#define PCT_TO_CCR(pct)  ((uint32_t)((100U - (pct)) * 10U - 1U))
/* pct=0 時 CCR = 999，pct=100 時 CCR = -1 → 用 0 夾住 */
#define PCT_TO_CCR_SAFE(pct) ((pct) == 0U ? (PWM_ARR) : \
                              (pct) == 100U ? 0U : PCT_TO_CCR(pct))

/* ── Timer handle ── */
TIM_HandleTypeDef htim2;   /* LED  PB10 TIM2_CH3 */
TIM_HandleTypeDef htim3;   /* 馬達 PB4  TIM3_CH1 */

/* ── 按鈕狀態 ── */
typedef struct {
    uint8_t  last;
    uint32_t debounce;
} BtnState;

/* ── 函式宣告 ── */
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM3_Init(void);
static void SetMotorPct(uint8_t pct);
static void SetLedPct(uint8_t pct);

/* ============================================================
 * main
 * ============================================================ */
int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_TIM2_Init();   /* LED */
    MX_TIM3_Init();   /* 馬達 */

    /* 初始：0%（低態驅動 → CCR = ARR = 999，全 HIGH = 不動）*/
    SetMotorPct(0);
    SetLedPct(0);

    /* 啟動 PWM 輸出 */
    HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);   /* 馬達 PB4  */
    HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_3);   /* LED  PB10 */

    uint8_t  motor_pct = 0;
    uint8_t  led_pct   = 0;

    BtnState btnM = { (uint8_t)HAL_GPIO_ReadPin(BTN_M_PORT, BTN_M_PIN), 0 };
    BtnState btnL = { (uint8_t)HAL_GPIO_ReadPin(BTN_L_PORT, BTN_L_PIN), 0 };

    for (;;)
    {
        uint32_t now = HAL_GetTick();

        /* ── 馬達按鈕 PA10 ── */
        uint8_t nowM = (uint8_t)HAL_GPIO_ReadPin(BTN_M_PORT, BTN_M_PIN);
        if (btnM.last == 1 && nowM == 0)
        {
            if ((now - btnM.debounce) >= 300UL)
            {
                motor_pct = (motor_pct + PWM_STEP) % 110U;
                /* 110 讓 100% 之後下一步回到 0%
                 * 0 10 20 ... 100 → (100+10)%110 = 0 */
                if (motor_pct > 100U) motor_pct = 0U;
                SetMotorPct(motor_pct);
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
                led_pct = (led_pct + PWM_STEP) % 110U;
                if (led_pct > 100U) led_pct = 0U;
                SetLedPct(led_pct);
                btnL.debounce = now;
            }
        }
        btnL.last = nowL;
    }
}

/* ============================================================
 * SetMotorPct / SetLedPct
 * 輸入 0~100，換算成 CCR 寫入 Timer
 * ============================================================ */
static void SetMotorPct(uint8_t pct)
{
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, PCT_TO_CCR_SAFE(pct));
}

static void SetLedPct(uint8_t pct)
{
    __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_3, PCT_TO_CCR_SAFE(pct));
}

/* ============================================================
 * TIM3 初始化：馬達 PB4（TIM3_CH1）
 * APB1 = 170 MHz
 * Prescaler = 170-1 → 計數頻率 1 MHz
 * ARR = 999          → 週期 1ms = 1kHz
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

    sConfigOC.OCMode       = TIM_OCMODE_PWM1;
    sConfigOC.Pulse        = PWM_ARR;   /* 初始 CCR=999 → 0% */
    sConfigOC.OCPolarity   = TIM_OCPOLARITY_HIGH;
    sConfigOC.OCFastMode   = TIM_OCFAST_DISABLE;
    if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
        Error_Handler();
}

/* ============================================================
 * TIM2 初始化：LED PB10（TIM2_CH3）
 * 同上，APB1 = 170 MHz，1kHz
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

    sConfigOC.OCMode       = TIM_OCMODE_PWM1;
    sConfigOC.Pulse        = PWM_ARR;   /* 初始 CCR=999 → 0% */
    sConfigOC.OCPolarity   = TIM_OCPOLARITY_HIGH;
    sConfigOC.OCFastMode   = TIM_OCFAST_DISABLE;
    if (HAL_TIM_PWM_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_3) != HAL_OK)
        Error_Handler();
}

/* ============================================================
 * GPIO 初始化
 * PB4  → AF2（TIM3_CH1）
 * PB10 → AF1（TIM2_CH3）
 * PA10 → 輸入，內部上拉
 * PB3  → 輸入，內部上拉
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
    GPIO_InitStruct.Pin  = BTN_M_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
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