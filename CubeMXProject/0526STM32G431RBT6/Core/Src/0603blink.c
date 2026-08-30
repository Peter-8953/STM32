/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  *                   NUCLEO-G431RB
  *                   - LD2 綠色 LED : PA5
  *                   - User Button  : PC13 (低電位觸發，邊緣偵測)
  *                   - LPUART1 TX   : PA2  (接 ST-LINK VCP)
  *
  *  修正：
  *  1. btn_prev 從實際讀取腳位初始化，避免開機假觸發
  *  2. LED 非阻塞閃爍，按鈕隨時可偵測
  ******************************************************************************
  */
/* USER CODE END Header */

#include "main.h"
#include <string.h>
#include <stdio.h>

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef hlpuart1;

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_LPUART1_UART_Init(void);

/* USER CODE BEGIN 0 */
void UART_Print(const char *str)
{
    HAL_UART_Transmit(&hlpuart1, (uint8_t *)str, strlen(str), 100);
}
/* USER CODE END 0 */

int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_LPUART1_UART_Init();

    UART_Print("=== NUCLEO-G431RB 啟動 ===\r\n");
    UART_Print("LD2 (PA5) 開始慢速閃爍 (500ms)\r\n");
    UART_Print("按 B1 切換速度 (500ms <-> 100ms)\r\n");

    uint32_t delay_ms  = 500;
    uint32_t led_tick  = 0;
    uint32_t btn_count = 0;
    char     msg[64];

    /*
     * 【修正】從實際腳位讀取初始狀態，避免開機時假觸發
     * 如果寫死 btn_prev = 1，但腳位剛啟動時短暫讀到 0，
     * 就會誤判成 falling edge，把 delay_ms 從 500 改成 100
     */
    uint8_t btn_prev = HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_13);

    while (1)
    {
        uint32_t now = HAL_GetTick();

        /* ── LED 非阻塞閃爍 ── */
        if (now - led_tick >= delay_ms)
        {
            led_tick = now;
            HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5);
        }

        /* ── 按鈕 Falling edge 偵測（1→0 = 剛按下瞬間）── */
        uint8_t btn_curr = HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_13);

        if (btn_prev == 1 && btn_curr == 0)
        {
            HAL_Delay(20);  /* 去彈跳 */
            if (HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_13) == 0)
            {
                btn_count++;

                if (delay_ms == 500)
                {
                    delay_ms = 100;
                    UART_Print(">> 快速閃爍 (100ms)\r\n");
                }
                else
                {
                    delay_ms = 500;
                    UART_Print(">> 慢速閃爍 (500ms)\r\n");
                }

                sprintf(msg, "   已切換 %lu 次\r\n", btn_count);
                UART_Print(msg);
            }
        }

        btn_prev = btn_curr;
    }
}

/**
  * @brief System Clock: HSI -> PLL -> 170 MHz
  */
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
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
        Error_Handler();

    RCC_ClkInitStruct.ClockType      = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                     | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource   = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider  = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
        Error_Handler();
}

/**
  * @brief LPUART1: 115200 8N1，PA2(TX)/PA3(RX) 接 ST-LINK VCP
  */
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
    if (HAL_UART_Init(&hlpuart1) != HAL_OK)
        Error_Handler();
    if (HAL_UARTEx_SetTxFifoThreshold(&hlpuart1, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK)
        Error_Handler();
    if (HAL_UARTEx_SetRxFifoThreshold(&hlpuart1, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK)
        Error_Handler();
    if (HAL_UARTEx_DisableFifoMode(&hlpuart1) != HAL_OK)
        Error_Handler();
}

/**
  * @brief GPIO 初始化
  *        PA5  : LD2 LED，推挽輸出，初始 LOW
  *        PC13 : User Button，輸入，外部 100K 上拉
  */
static void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_RESET);

    GPIO_InitStruct.Pin   = GPIO_PIN_5;
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    GPIO_InitStruct.Pin  = GPIO_PIN_13;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);
}

void Error_Handler(void)
{
    __disable_irq();
    while (1) {}
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line) {}
#endif