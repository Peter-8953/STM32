/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <string.h>
#include "frame_parser.h"
#include "rtc_driver.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* 這片板子自己的裝置 ID。0x02 是先給的預留值（0x00=broadcast、
   0x01=PC，見 protocol.py 的 ID 分配註解）。第3階 CMD_GET_ID 會回傳
   同一個值；第6階如果要接第二片板子，那片板子要改成不同的值
   （例如 0x03），不能兩片板子共用同一個 ID。 */
#define MY_DEVICE_ID    0x02u

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

COM_InitTypeDef BspCOMInit;
__IO uint32_t BspButtonState = BUTTON_RELEASED;
I2C_HandleTypeDef hi2c1;

/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_I2C1_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/**
 * @brief 組包 + 送出一個 frame。固定把 f.ver 設成 FRAME_VER，呼叫端不用
 *        自己記——frame_build() 是照單全收呼叫端填的 f->ver，不像 Python
 *        端 build_frame() 內部寫死 VERSION；如果哪個呼叫端漏設 .ver，組
 *        出來的 VER byte 會是 0x00，PC 端會直接判「Unsupported protocol
 *        version」拒收，很難第一時間查到問題出在這裡，所以集中在這一個
 *        function 裡處理，之後每個 CMD 分支都不用自己記得補這行。
 */
static void send_frame(uint8_t src, uint8_t dst, uint8_t cmd, uint16_t seq,
                        const uint8_t *payload, uint8_t len, uint8_t flags)
{
    Frame f;
    uint8_t buf[FRAME_MAX_LEN];
    uint16_t n;

    memset(&f, 0, sizeof(f));
    f.ver = FRAME_VER;
    f.src = src;
    f.dst = dst;
    f.cmd = cmd;
    f.seq = seq;
    if (len > 0u)
    {
        memcpy(f.payload, payload, len);
    }
    f.len = len;
    f.flags = flags;

    n = frame_build(&f, buf, sizeof(buf));
    if (n > 0u)
    {
        HAL_UART_Transmit(&hcom_uart[COM1], buf, n, HAL_MAX_DELAY);
    }
}

static void send_error(uint8_t dst, uint16_t seq, uint8_t err_code)
{
    uint8_t payload[1];
    payload[0] = err_code;
    send_frame(MY_DEVICE_ID, dst, CMD_ERR, seq, payload, 1u, FLAG_IS_ERROR);
}
/**
 * @brief 阻塞式讀出一個完整 frame（先不做 timeout，對齊第2階 checklist
 *        的 MVP 範圍）。讀法對齊 Python 端 transport.py 的
 *        SerialTransport.recv()：
 *          (1) 逐 byte 找 SOF（只留最後兩個 byte，不累積垃圾，天然免疫
 *              payload 裡剛好出現 0xAA 0x55 的情況——理由跟 transport.py
 *              的 _wait_sof() 完全一樣）
 *          (2) 讀固定長度 header（VER+SRC+DST+CMD+SEQ(2)+LEN = 7 bytes）
 *          (3) 依 LEN 讀 PAYLOAD + FLAGS(1) + CRC(2)
 * @param out_buf      輸出緩衝區，呼叫端要保證至少 FRAME_MAX_LEN bytes
 * @param out_buf_size 緩衝區容量
 * @retval 實際收到的 byte 數（含 SOF）；0 表示 HAL 讀取失敗，或是 LEN
 *         聲稱的長度放不進緩衝區（正常合法封包不會發生，見下面註解）
 */
static uint16_t recv_frame(uint8_t *out_buf, uint16_t out_buf_size)
{
    uint8_t prev = 0x00u;
    uint8_t cur;
    uint8_t header[7];
    uint8_t payload_len;
    uint16_t total;

    /* (1) 找 SOF */
    for (;;)
    {
        if (HAL_UART_Receive(&hcom_uart[COM1], &cur, 1, HAL_MAX_DELAY) != HAL_OK)
        {
            return 0u;
        }
        if ((prev == FRAME_SOF0) && (cur == FRAME_SOF1))
        {
            break;
        }
        prev = cur;
    }

    /* (2) 讀固定長度 header */
    if (HAL_UART_Receive(&hcom_uart[COM1], header, sizeof(header), HAL_MAX_DELAY) != HAL_OK)
    {
        return 0u;
    }
    payload_len = header[6];   /* header[6] = LEN 欄位 */

    total = (uint16_t)(2u + sizeof(header) + payload_len + 3u);
    if (total > out_buf_size)
    {
        /* LEN 聲稱的長度超過緩衝區。正常情況不會發生（合法封包的
           payload 上限是 FRAME_PAYLOAD_MAX=32，早就在 out_buf_size 之
           內），會走到這裡代表 LEN 欄位本身壞掉或收到雜訊。這裡先簡單
           回傳 0（呼叫端跳過這輪、回去重新找 SOF），還沒把「照 LEN 讀掉
           payload 讓串流對齊回下一個 SOF」這件事做完整——那個邊界檢查
           排在第4階（計畫書 5.4 節），這裡先不做。 */
        return 0u;
    }

    out_buf[0] = FRAME_SOF0;
    out_buf[1] = FRAME_SOF1;
    memcpy(&out_buf[2], header, sizeof(header));

    /* (3) 依 LEN 讀 PAYLOAD + FLAGS + CRC */
    if (HAL_UART_Receive(&hcom_uart[COM1], &out_buf[2 + sizeof(header)],
                          (uint16_t)(payload_len + 3u), HAL_MAX_DELAY) != HAL_OK)
    {
        return 0u;
    }

    return total;
}

/**
 * @brief 處理 CMD_GET_TIME：讀 DS3231 目前時間，回 CMD_DATA_TIME。
 *
 * 注意：這個 dispatch 迴圈跑起來之後，hcom_uart[COM1] 同時是「協定的
 * 傳輸線」也是 printf() 的輸出線——板子只有這一個 UART 接到 ST-Link
 * VCP（計畫書 1.1 節）。這裡刻意不加任何 printf()：一旦協定在跑，任何
 * 額外的除錯文字都會插進 PC 端正在等待的 binary frame 中間，讓
 * SerialTransport._wait_sof()/_read_exact() 對不上，表現出來會是很難查
 * 的間歇性 CRC 或長度錯誤。要看即時狀態的話，改用 SWO/ITM，或者先把
 * dispatch 迴圈換回舊的 demo loop 單獨測 UART。
 */
static void handle_get_time(const Frame *req)
{
    RtcDateTime dt;

    if (rtc_get_time(&hi2c1, &dt) == HAL_OK)
    {
        uint8_t payload[7];
        payload[0] = (uint8_t)(dt.year >> 8);
        payload[1] = (uint8_t)(dt.year & 0xFFu);
        payload[2] = dt.month;
        payload[3] = dt.day;
        payload[4] = dt.hour;
        payload[5] = dt.minute;
        payload[6] = dt.second;
        send_frame(MY_DEVICE_ID, req->src, CMD_DATA_TIME, req->seq, payload, 7u, 0u);
    }
    /* I2C 讀取失敗時的 CMD_ERR 回應留到第4階；第2階先只處理成功路徑，
       失敗就不回應（PC 端會 timeout，照 runner.py 既有的重試機制處理）。 */
}

static void handle_set_time(const Frame *req)
{
    RtcDateTime dt;

    if (req->len != 7u)
    {
        send_error(req->src, req->seq, ERR_PAYLOAD_TOO_SHORT);
        return;   /* payload 長度不對，先靜默忽略，ERR_PAYLOAD_TOO_SHORT 留給第4階 */
    }

    dt.year   = (uint16_t)(((uint16_t)req->payload[0] << 8) | req->payload[1]);
    dt.month  = req->payload[2];
    dt.day    = req->payload[3];
    dt.hour   = req->payload[4];
    dt.minute = req->payload[5];
    dt.second = req->payload[6];

    if (rtc_set_time(&hi2c1, &dt) == HAL_OK)
    {
        send_frame(MY_DEVICE_ID, req->src, CMD_ACK, req->seq, NULL, 0u, 0u);
    }
    /* 寫入失敗不回應，CMD_ERR 留給第4階 */
}

static void handle_get_temp(const Frame *req)
{
    RtcDateTime dt;
    RtcTemperature temp;

    if ((rtc_get_time(&hi2c1, &dt) == HAL_OK) && (rtc_get_temp(&hi2c1, &temp) == HAL_OK))
    {
        uint8_t payload[9];
        payload[0] = (uint8_t)temp.temp_int;
        payload[1] = temp.temp_frac;
        payload[2] = (uint8_t)(dt.year >> 8);
        payload[3] = (uint8_t)(dt.year & 0xFFu);
        payload[4] = dt.month;
        payload[5] = dt.day;
        payload[6] = dt.hour;
        payload[7] = dt.minute;
        payload[8] = dt.second;
        send_frame(MY_DEVICE_ID, req->src, CMD_DATA_TEMP, req->seq, payload, 9u, 0u);
    }
}

static void handle_get_id(const Frame *req)
{
    uint8_t payload[1];
    payload[0] = MY_DEVICE_ID;
    send_frame(MY_DEVICE_ID, req->src, CMD_DATA_ID, req->seq, payload, 1u, 0u);
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_I2C1_Init();
  /* USER CODE BEGIN 2 */

  /* USER CODE END 2 */

  /* Initialize leds */
  BSP_LED_Init(LED_GREEN);

  /* Initialize USER push-button, will be used to trigger an interrupt each time it's pressed.*/
  BSP_PB_Init(BUTTON_USER, BUTTON_MODE_EXTI);

  /* Initialize COM1 port (115200, 8 bits (7-bit data + 1 stop bit), no parity */
  BspCOMInit.BaudRate   = 115200;
  BspCOMInit.WordLength = COM_WORDLENGTH_8B;
  BspCOMInit.StopBits   = COM_STOPBITS_1;
  BspCOMInit.Parity     = COM_PARITY_NONE;
  BspCOMInit.HwFlowCtl  = COM_HWCONTROL_NONE;
  if (BSP_COM_Init(COM1, &BspCOMInit) != BSP_ERROR_NONE)
  {
    Error_Handler();
  }

  /* USER CODE BEGIN BSP */

  /* -- Sample board code to send message over COM1 port ---- */
  printf("Welcome to STM32 world !\n\r");

  /* -- Sample board code to switch on leds ---- */
  BSP_LED_On(LED_GREEN);
  printf("\r\n--- I2C Scan Start ---\r\n");
  for (uint16_t addr = 1; addr < 128; addr++)
  {
    if (HAL_I2C_IsDeviceReady(&hi2c1, (addr << 1), 1, 10) == HAL_OK)
    {
      printf("Found device at address 0x%02X\r\n", addr);
    }
  }
  printf("--- Scan End ---\r\n\r\n");

  /* 進入下面的 dispatch 迴圈之後就不能再用 printf 了（理由見
     handle_get_time() 上面的註解），這是最後一次能安全印出偵錯文字
     的地方。 */
  printf("Entering protocol dispatch loop (device id 0x%02X)...\r\n", MY_DEVICE_ID);

  /* USER CODE END BSP */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    uint8_t rx_buf[FRAME_MAX_LEN];
    uint16_t rx_len;
    Frame req;

    rx_len = recv_frame(rx_buf, sizeof(rx_buf));
    if (rx_len == 0u)
    {
      /* HAL 讀取失敗（例如 USB 瞬斷），跳過這輪，回去等下一次 SOF。
         要不要加重連/重置邏輯是之後的事，第2階先不處理。 */
      continue;
    }

    if (frame_parse(rx_buf, rx_len, &req) != FRAME_OK)
    {
      /* SOF/VER/CRC/LEN 任一項不符，直接丟棄不回應，回去等下一包。
         完整的 FLAG_IS_ERROR / CMD_ERR 回應是第4階的範圍，這裡先對齊
         第2階 MVP：只求收得到、解得對、回得對。 */
      continue;
    }

    switch (req.cmd)
    {
      case CMD_GET_TIME:
        handle_get_time(&req);
        BSP_LED_Toggle(LED_GREEN);   /* 用「處理過一次請求」取代原本定時的心跳閃爍 */
        break;
      case CMD_SET_TIME:
        handle_set_time(&req);
        BSP_LED_Toggle(LED_GREEN);
        break;

      case CMD_GET_TEMP:
        handle_get_temp(&req);
        BSP_LED_Toggle(LED_GREEN);
        break;

      case CMD_GET_ID:
        handle_get_id(&req);
        BSP_LED_Toggle(LED_GREEN);
        break;
      default:
        send_error(req.src, req.seq, ERR_UNKNOWN_CMD);
        break;
    }

    /* -- Sample board code for User push-button in interrupt mode ---- */
    if (BspButtonState == BUTTON_PRESSED)
    {
      /* Update button state */
      BspButtonState = BUTTON_RELEASED;
      /* -- Sample board code to toggle leds ---- */
      BSP_LED_Toggle(LED_GREEN);

      /* ..... Perform your action ..... */
    }
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV4;
  RCC_OscInitStruct.PLL.PLLN = 85;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief I2C1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C1_Init(void)
{

  /* USER CODE BEGIN I2C1_Init 0 */

  /* USER CODE END I2C1_Init 0 */

  /* USER CODE BEGIN I2C1_Init 1 */

  /* USER CODE END I2C1_Init 1 */
  hi2c1.Instance = I2C1;
  hi2c1.Init.Timing = 0x40B285C2;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.OwnAddress2Masks = I2C_OA2_NOMASK;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Analogue filter
  */
  if (HAL_I2CEx_ConfigAnalogFilter(&hi2c1, I2C_ANALOGFILTER_ENABLE) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Digital filter
  */
  if (HAL_I2CEx_ConfigDigitalFilter(&hi2c1, 0) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C1_Init 2 */

  /* USER CODE END I2C1_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
#ifdef __GNUC__
int __io_putchar(int ch)
#else
int fputc(int ch, FILE *f)
#endif
{
  HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t *)&ch, 1, HAL_MAX_DELAY);
  return ch;
}
/* USER CODE END 4 */

/**
  * @brief  BSP Push Button callback
  * @param  Button Specifies the pressed button
  * @retval None
  */
void BSP_PB_Callback(Button_TypeDef Button)
{
  if (Button == BUTTON_USER)
  {
    BspButtonState = BUTTON_PRESSED;
  }
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
