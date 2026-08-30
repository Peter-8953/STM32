/* ============================================================
 * main_stm32g431rb.c
 * NUCLEO-G431RB
 *
 * LED  → PB10（低態驅動：LOW = 亮）
 * 馬達 → PB4 （低態驅動：LOW = 轉）
 * 馬達按鈕 → PA10（低態觸發，內部上拉）
 * LED 按鈕  → PB3 （低態觸發，內部上拉）
 *
 * PWM 週期 10ms，3段：0% / 40% / 100%
 * ============================================================ */

#include "main.h"

/* ── 腳位 ── */
#define MOTOR_PORT   GPIOB
#define MOTOR_PIN    GPIO_PIN_4   // PB4，馬達

#define LED_PORT     GPIOB
#define LED_PIN      GPIO_PIN_10    // PB10，LED

#define BTN_M_PORT   GPIOA
#define BTN_M_PIN    GPIO_PIN_10   /* PA10，馬達按鈕 */

#define BTN_L_PORT   GPIOB
#define BTN_L_PIN    GPIO_PIN_3    /* PB3，LED 按鈕 */

/* ── PWM 段落 ── */
typedef struct { uint8_t duty; uint8_t pct; } PWMLevel;

static const PWMLevel motor_levels[3] = {
    {  0,   0 },
    {  4,  40 },
    { 10, 100 },
};
static const PWMLevel led_levels[3] = {
    {  0,   0 },
    {  4,  40 },
    { 10, 100 },
};

/* ── 按鈕狀態 ── */
typedef struct {
    uint8_t  last;// 上一次讀到的腳位狀態
    uint32_t debounce;// 上次觸發的時間點(ms)
} BtnState;

void SystemClock_Config(void);
static void MX_GPIO_Init(void);

int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();

    uint8_t  motor_mode = 0;
    uint8_t  led_mode   = 0;
    uint8_t  motor_duty = 0;
    uint8_t  led_duty   = 0;
//btnM 就是專門負責「記住馬達按鈕上一秒在幹嘛」的小本子，btnL 同理負責 LED 按鈕。
/*  BtnState btnM;
    btnM.last     = HAL_GPIO_ReadPin(BTN_M_PORT, BTN_M_PIN);  讀腳位現在的狀態（0或1）   ==> uint8_t  last;
    btnM.debounce = 0;                                         上次觸發時間，初始為0     ==> uint32_t debounce;*/
    BtnState btnM = { (uint8_t)HAL_GPIO_ReadPin(BTN_M_PORT, BTN_M_PIN), 0 };
    BtnState btnL = { (uint8_t)HAL_GPIO_ReadPin(BTN_L_PORT, BTN_L_PIN), 0 };

    for (;;)
    {
        uint32_t now     = HAL_GetTick();// 系統時間(ms)，SysTick 自動累加
        uint32_t elapsed = now % 10UL;   /* 0~9，週期 10ms */

        /* ── 軟體 PWM（低態驅動）── */
        HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_PIN,
            (elapsed < motor_duty) ? GPIO_PIN_RESET : GPIO_PIN_SET); // GPIO_PIN_RESET（LOW = 亮），GPIO_PIN_SET（HIGH = 滅）

        HAL_GPIO_WritePin(LED_PORT, LED_PIN,
            (elapsed < led_duty) ? GPIO_PIN_RESET : GPIO_PIN_SET);

        /* ── 馬達按鈕 PA10：Falling edge 1→0 ── */
        uint8_t nowM = (uint8_t)HAL_GPIO_ReadPin(BTN_M_PORT, BTN_M_PIN);//nowM 存的是這一瞬間 PA10 腳位的電壓狀態，只有兩種值：1==>HIGH按鈕沒有按下；0==>LOW按鈕按下中
        if (btnM.last == 1 && nowM == 0)
        {
            if ((now - btnM.debounce) >= 300UL)
            {
                motor_mode    = (motor_mode + 1) % 3;
                motor_duty    = motor_levels[motor_mode].duty;
                btnM.debounce = now;
            }
        }
        btnM.last = nowM;

        /* ── LED 按鈕 PB3：Falling edge 1→0 ── */
        uint8_t nowL = (uint8_t)HAL_GPIO_ReadPin(BTN_L_PORT, BTN_L_PIN);//nowL 存的是這一瞬間 PB3 腳位的電壓狀態，只有兩種值：1==>HIGH按鈕沒有按下；0==>LOW按鈕按下中
        if (btnL.last == 1 && nowL == 0)
        {
            if ((now - btnL.debounce) >= 300UL)
            {
                led_mode      = (led_mode + 1) % 3;
                led_duty      = led_levels[led_mode].duty;
                btnL.debounce = now;
            }
        }
        btnL.last = nowL;
    }
}

void SystemClock_Config(void)//讓 CPU 從預設的低速變成 170 MHz 高速運行。
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};//建立兩個設定用的結構，{0} 是全部清零，避免裡面有垃圾值。
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);//跑 170 MHz 需要較高的核心電壓，這行先把電壓調高，否則 CPU 跑不到那麼快。

    RCC_OscInitStruct.OscillatorType      = RCC_OSCILLATORTYPE_HSI;// 使用內部 16MHz 振盪器
    RCC_OscInitStruct.HSIState            = RCC_HSI_ON;
    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState        = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource       = RCC_PLLSOURCE_HSI;// PLL 輸入來源是 HSI
    RCC_OscInitStruct.PLL.PLLM            = RCC_PLLM_DIV4;// 16MHz ÷ 4 = 4MHz
    RCC_OscInitStruct.PLL.PLLN            = 85;// 4MHz × 85 = 340MHz
    RCC_OscInitStruct.PLL.PLLP            = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLQ            = RCC_PLLQ_DIV2;
    RCC_OscInitStruct.PLL.PLLR            = RCC_PLLR_DIV2;// 340MHz ÷ 2 = 170MHz
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) Error_Handler();

    RCC_ClkInitStruct.ClockType      = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                     | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource   = RCC_SYSCLKSOURCE_PLLCLK; // CPU 時脈來源用 PLL
    RCC_ClkInitStruct.AHBCLKDivider  = RCC_SYSCLK_DIV1;// AHB  = 170MHz ÷ 1 = 170MHz
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;// AHB1  = 170MHz ÷ 1 = 170MHz
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;// AHB2  = 170MHz ÷ 1 = 170MHz
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK) Error_Handler();
}

static void MX_GPIO_Init(void)//STM32 預設所有周邊時脈是關閉的（省電），要用 GPIOA、GPIOB 之前必須先開啟時脈，否則寫入設定完全無效。
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    /* PB10：LED，先 Init 再 WritePin */
    GPIO_InitStruct.Pin   = LED_PIN;
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;// 推挽輸出（可主動輸出 HIGH/LOW）
    GPIO_InitStruct.Pull  = GPIO_NOPULL;// 不加上/下拉電阻
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;// 低速輸出（省電，PWM 10ms 夠用）
    HAL_GPIO_Init(LED_PORT, &GPIO_InitStruct);// 套用設定到 PB10
    HAL_GPIO_WritePin(LED_PORT, LED_PIN, GPIO_PIN_SET);   /* HIGH = 熄滅 */

    /* PB4：馬達，先 Init 再 WritePin */
    GPIO_InitStruct.Pin = MOTOR_PIN;
    HAL_GPIO_Init(MOTOR_PORT, &GPIO_InitStruct);
    HAL_GPIO_WritePin(MOTOR_PORT, MOTOR_PIN, GPIO_PIN_SET); /* HIGH = 停止 */

    //輸出腳位（LED、馬達）設定流程都一樣：先 Init 設模式，再 WritePin 設初始電位。
    /* PA10：馬達按鈕，內部上拉 */
    GPIO_InitStruct.Pin  = BTN_M_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;// 輸入模式（只能讀，不能寫）
    GPIO_InitStruct.Pull = GPIO_PULLUP;// 內部上拉：沒按時腳位保持 HIGH
    HAL_GPIO_Init(BTN_M_PORT, &GPIO_InitStruct);

    /* PB3：LED 按鈕，內部上拉 */
    GPIO_InitStruct.Pin  = BTN_L_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(BTN_L_PORT, &GPIO_InitStruct);
}

void Error_Handler(void)//當任何初始化失敗時呼叫，讓程式停在這裡不繼續跑，方便 debug 時發現問題。正常執行時永遠不會跑到這裡。
{
    __disable_irq();// 關閉所有中斷，防止繼續執行任何程式
    while (1) {}// 無限迴圈卡死在這裡
}