/* ============================================================
 * main_stm32g431rb.c
 * NUCLEO-G431RB
 *
 * 腳位（與 AVR 版保持對應，不更動）：
 *   馬達按鈕 : PC13  (User Button，低態觸發)
 *   LED  按鈕 : PB0   (低態觸發，內部上拉)
 *   馬達輸出 : PB1   (低態驅動，LOW = 馬達轉)
 *   LED  輸出 : PA5   (低態驅動，LOW = 亮)
 *
 * Timer：TIM6 → 每 1ms 觸發 ISR（軟體 PWM + millis）
 * ============================================================ */

#include "main.h"  /* 直接 include HAL，不需要 main.h */
#include <stdio.h>
#include <string.h>

/* ============================================================
 * 腳位定義（與 AVR 版完全對應，不更動）
 * ============================================================ */
#define MOTOR_GPIO_PORT   GPIOB
#define MOTOR_GPIO_PIN    GPIO_PIN_1    /* PB1 → 馬達（低態驅動）*/

#define LED_GPIO_PORT     GPIOA
#define LED_GPIO_PIN      GPIO_PIN_5    /* PA5 → LED（低態驅動） */

#define BTN_MOTOR_PORT    GPIOC
#define BTN_MOTOR_PIN     GPIO_PIN_13   /* PC13 → 馬達按鈕        */

#define BTN_LED_PORT      GPIOB
#define BTN_LED_PIN       GPIO_PIN_0    /* PB0  → LED 按鈕         */

/* ============================================================
 * PWM 段落設定（3段）
 * duty：0~10（對應 0%~100%）
 * ============================================================ */
typedef struct {
    uint8_t duty;
    uint8_t pct;
} PWMLevel;

static const PWMLevel motor_levels[3] = {
    {  0,   0 },   /* 停止：  0% */
    {  4,  40 },   /* 中速： 40% */
    { 10, 100 },   /* 全速：100% */
};

static const PWMLevel led_levels[3] = {
    {  0,   0 },   /* 熄滅：  0% */
    {  4,  40 },   /* 中亮： 40% */
    { 10, 100 },   /* 全亮：100% */
};

/* ============================================================
 * 全域變數
 * ============================================================ */
TIM_HandleTypeDef  htim6;
UART_HandleTypeDef hlpuart1;

volatile uint32_t nowTime   = 0;
volatile uint8_t  motor_pwm = 0;
volatile uint8_t  led_pwm   = 0;

/* ============================================================
 * 按鈕狀態結構（同 AVR 版）
 * ============================================================ */
typedef struct {
    uint8_t  last;
    uint32_t debounce;
} BtnState;

/* ============================================================
 * 工具函式
 * ============================================================ */
static inline uint32_t millis(void)
{
    return nowTime;
}

void UART_Print(const char *str)
{
    HAL_UART_Transmit(&hlpuart1, (uint8_t *)str, strlen(str), 100);
}

/* ============================================================
 * 函式宣告
 * ============================================================ */
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM6_Init(void);
static void MX_LPUART1_UART_Init(void);
void Error_Handler(void);

/* ============================================================
 * main
 * ============================================================ */
int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_TIM6_Init();
    MX_LPUART1_UART_Init();

    UART_Print("=== STM32G431RB Motor+LED PWM ===\r\n");
    UART_Print("PC13 = 馬達段位切換 (0%% -> 40%% -> 100%%)\r\n");
    UART_Print("PB0  = LED  段位切換 (0%% -> 40%% -> 100%%)\r\n");

    /* 啟動 TIM6 */
    HAL_TIM_Base_Start_IT(&htim6);

    /* 套用初始值 */
    __disable_irq();
    motor_pwm = motor_levels[0].duty;
    led_pwm   = led_levels[0].duty;
    __enable_irq();

    uint8_t  motor_mode = 0;
    uint8_t  led_mode   = 0;

    /* 讀取真實腳位初始狀態，防止開機假觸發 */
    BtnState btnM = {
        (uint8_t)HAL_GPIO_ReadPin(BTN_MOTOR_PORT, BTN_MOTOR_PIN), 0
    };
    BtnState btnL = {
        (uint8_t)HAL_GPIO_ReadPin(BTN_LED_PORT, BTN_LED_PIN), 0
    };

    char msg[64];

    for (;;)
    {
        uint32_t now  = millis();
        uint8_t  nowM = (uint8_t)HAL_GPIO_ReadPin(BTN_MOTOR_PORT, BTN_MOTOR_PIN);
        uint8_t  nowL = (uint8_t)HAL_GPIO_ReadPin(BTN_LED_PORT,   BTN_LED_PIN);

        /* ── 馬達按鈕（PC13）Falling edge：1→0 ── */
        if (btnM.last == 1 && nowM == 0)
        {
            if ((now - btnM.debounce) >= 350UL)
            {
                motor_mode = (motor_mode + 1) % 3;

                __disable_irq();
                motor_pwm = motor_levels[motor_mode].duty;
                __enable_irq();

                btnM.debounce = now;

                sprintf(msg, "Motor -> %3d%%\r\n", motor_levels[motor_mode].pct);
                UART_Print(msg);
            }
        }
        btnM.last = nowM;

        /* ── LED 按鈕（PB0）Falling edge：1→0 ── */
        if (btnL.last == 1 && nowL == 0)
        {
            if ((now - btnL.debounce) >= 350UL)
            {
                led_mode = (led_mode + 1) % 3;

                __disable_irq();
                led_pwm = led_levels[led_mode].duty;
                __enable_irq();

                btnL.debounce = now;

                sprintf(msg, "LED   -> %3d%%\r\n", led_levels[led_mode].pct);
                UART_Print(msg);
            }
        }
        btnL.last = nowL;
    }
}

/* ============================================================
 * TIM6 溢位 ISR：每 1ms 觸發
 * 對應 AVR TIMER0_OVF_vect
 * ============================================================ */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance != TIM6) return;

    static uint8_t pwm_count = 0;

    nowTime++;

    /* ── 軟體 PWM（低態驅動，與 AVR 版完全相同）──
     *
     *   pwm_count < duty  → RESET（LOW）= 動作（馬達轉 / LED 亮）
     *   pwm_count >= duty → SET  （HIGH）= 停止（馬達停 / LED 滅）
     * ───────────────────────────────────────────── */

    /* 馬達（PB1，低態驅動）*/
    if (pwm_count < motor_pwm)
        HAL_GPIO_WritePin(MOTOR_GPIO_PORT, MOTOR_GPIO_PIN, GPIO_PIN_RESET); /* LOW = 馬達轉 */
    else
        HAL_GPIO_WritePin(MOTOR_GPIO_PORT, MOTOR_GPIO_PIN, GPIO_PIN_SET);   /* HIGH = 馬達停 */

    /* LED（PA5，低態驅動）*/
    if (pwm_count < led_pwm)
        HAL_GPIO_WritePin(LED_GPIO_PORT, LED_GPIO_PIN, GPIO_PIN_RESET);     /* LOW = LED 亮 */
    else
        HAL_GPIO_WritePin(LED_GPIO_PORT, LED_GPIO_PIN, GPIO_PIN_SET);       /* HIGH = LED 滅 */

    pwm_count = (pwm_count + 1) % 10;
}

/* ============================================================
 * TIM6 IRQ Handler
 * ============================================================ */
void TIM6_DAC_IRQHandler(void)
{
    HAL_TIM_IRQHandler(&htim6);
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
 * TIM6：APB1 = 170 MHz
 *   Prescaler = 170-1  → 計數頻率 1 MHz
 *   Period    = 1000-1 → 每 1ms 溢位
 * ============================================================ */
static void MX_TIM6_Init(void)
{
    __HAL_RCC_TIM6_CLK_ENABLE();

    htim6.Instance               = TIM6;
    htim6.Init.Prescaler         = 170 - 1;
    htim6.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim6.Init.Period            = 1000 - 1;
    htim6.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    if (HAL_TIM_Base_Init(&htim6) != HAL_OK) Error_Handler();

    HAL_NVIC_SetPriority(TIM6_DAC_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(TIM6_DAC_IRQn);
}

/* ============================================================
 * GPIO 初始化
 *   PA5  : LED，推挽輸出，初始 HIGH（熄滅，低態驅動）
 *   PB1  : 馬達，推挽輸出，初始 HIGH（停止，低態驅動）
 *   PC13 : 馬達按鈕，輸入，無內部上拉（板上已有 100K）
 *   PB0  : LED 按鈕，輸入，內部上拉
 * ============================================================ */
static void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    /* PA5：LED，初始 HIGH（低態驅動 → 熄滅）*/
    HAL_GPIO_WritePin(LED_GPIO_PORT, LED_GPIO_PIN, GPIO_PIN_SET);
    GPIO_InitStruct.Pin   = LED_GPIO_PIN;
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(LED_GPIO_PORT, &GPIO_InitStruct);

    /* PB1：馬達，初始 HIGH（低態驅動 → 停止）*/
    HAL_GPIO_WritePin(MOTOR_GPIO_PORT, MOTOR_GPIO_PIN, GPIO_PIN_SET);
    GPIO_InitStruct.Pin   = MOTOR_GPIO_PIN;
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(MOTOR_GPIO_PORT, &GPIO_InitStruct);

    /* PC13：馬達按鈕（User Button），板上已有上拉電阻 */
    GPIO_InitStruct.Pin  = BTN_MOTOR_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(BTN_MOTOR_PORT, &GPIO_InitStruct);

    /* PB0：LED 按鈕，內部上拉（外接按鈕另一端接 GND）*/
    GPIO_InitStruct.Pin  = BTN_LED_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(BTN_LED_PORT, &GPIO_InitStruct);
}

/* ============================================================
 * LPUART1：115200 8N1，PA2(TX)/PA3(RX)
 * ============================================================ */
static void MX_LPUART1_UART_Init(void)
{
    hlpuart1.Instance            = LPUART1;
    hlpuart1.Init.BaudRate       = 115200;
    hlpuart1.Init.WordLength     = UART_WORDLENGTH_8B;
    hlpuart1.Init.StopBits       = UART_STOPBITS_1;
    hlpuart1.Init.Parity         = UART_PARITY_NONE;
    hlpuart1.Init.Mode           = UART_MODE_TX_RX;
    hlpuart1.Init.HwFlowCtl      = UART_HWCONTROL_NONE;
    hlpuart1.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    hlpuart1.Init.ClockPrescaler = UART_PRESCALER_DIV1;
    hlpuart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
    if (HAL_UART_Init(&hlpuart1) != HAL_OK)                                      Error_Handler();
    if (HAL_UARTEx_SetTxFifoThreshold(&hlpuart1, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK) Error_Handler();
    if (HAL_UARTEx_SetRxFifoThreshold(&hlpuart1, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK) Error_Handler();
    if (HAL_UARTEx_DisableFifoMode(&hlpuart1) != HAL_OK)                          Error_Handler();
}

/* ============================================================
 * Error Handler
 * ============================================================ */
void Error_Handler(void)
{
    __disable_irq();
    while (1) {}
}