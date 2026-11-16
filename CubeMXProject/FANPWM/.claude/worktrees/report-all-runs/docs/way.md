你列出的這些方法：

- PID
- LQR
- MPC
- Reinforcement Learning（強化學習，RL）
- End-to-End Learning（端到端學習）
- World Model（世界模型）
- Limitation（你可能是指 Linearization 線性化，或是 Limitation 限制，需要再區分）

其實涵蓋了現代控制工程（Control Engineering）、最適控制（Optimal Control）、機器學習（Machine Learning）與機器人自主控制（Autonomous Robotics）四個領域。

它們不是全部互相競爭的控制器。有些是控制演算法，有些是學習架構，有些是建模方法。

我用無人機（Quadrotor UAV）作為例子，從控制原理、數學模型、優缺點到彼此的關係整理。

# 1. 先建立整體分類

A. 傳統回授控制（Classical Control）

PID

PD

P / PI

根據目標值與實際輸出的誤差，計算控制輸入。

B. 最適控制（Optimal Control）

LQR

LQG

iLQR

DDP

透過數學最佳化，尋找符合成本函數的最佳控制策略。

C. 模型預測控制（Predictive Control）

MPC

NMPC

Tube MPC

Robust MPC

利用系統模型預測未來，反覆計算接下來的控制動作。

D. 學習式控制（Learning-based Control）

Reinforcement Learning

Imitation Learning

End-to-End

Adaptive Control

從資料、互動或經驗中學習控制策略。

E. 模型學習與預測（Learned Dynamics / World Models）

World Model

Neural Dynamics

Gaussian Process

Physics-Informed NN

學習或建立環境與系統的動態模型，供規劃或控制使用。

# 2. 各種方法是什麼？

## 2.1 PID — Proportional Integral Derivative

傳統回授控制

PID 是最常見的控制方法之一。

假設無人機希望維持高度 2 公尺：

- Target：2 m
- Actual：1.5 m
- Error：0.5 m

PID 根據誤差產生控制量。

數學公式：

\\[ u(t)=K_p e(t)+K_i\int_0^t e(\tau)d\tau+ K_d\frac{de(t)}{dt} \\]

三個部分：

| 參數 | 功能   | 直觀理解          |
| -- | ---- | ------------- |
| P  | 比例控制 | 現在誤差越大，修正越大   |
| I  | 積分控制 | 累積過去誤差，消除穩態誤差 |
| D  | 微分控制 | 預測誤差變化趨勢，增加阻尼 |

優點

- 容易實作。
- 運算量低。
- 不需要精確的系統數學模型。
- 適合 STM32 等微控制器。

缺點

- 多變數耦合系統較難調整。
- 不會主動預測未來。
- 飽和、延遲與非線性會讓控制變得困難。

例如：四軸無人機通常會使用 PID 控制 Roll、Pitch、Yaw 和高度。

## 2.2 LQR — Linear Quadratic Regulator

最適控制

LQR 和 PID 最大的差異是：

LQR 不只是根據當前誤差調整輸出，而是根據系統狀態與成本函數，計算最佳控制輸入。

首先需要建立線性系統模型：

\\[ \dot{x}=Ax+Bu \\]

其中：

- \\(x\\)：系統狀態，例如位置、速度、角度、角速度。
- \\(u\\)：控制輸入，例如馬達推力。
- \\(A\\)：系統動態矩陣。
- \\(B\\)：控制輸入矩陣。

LQR 最小化以下成本函數：

\\[ J=\int_0^\infty(x^TQx+u^TRu)dt \\]

其中：

- \\(Q\\)：懲罰狀態誤差。
- \\(R\\)：懲罰控制輸入。

最後得到：

\\[ u=-Kx \\]

\\(K\\) 是透過 Algebraic Riccati Equation（代數黎卡提方程式）求得的回授增益矩陣。

直觀理解：

假設無人機有以下狀態：

\\[ x= \begin{bmatrix} z\\\ \dot{z}\\\ \theta\\\ \dot{\theta} \end{bmatrix} \\]

LQR 會同時考慮高度、垂直速度、姿態角與角速度，而不是單獨控制某一個誤差。

優點

- 能處理多變數耦合。
- 有明確的數學最佳化基礎。
- 在模型符合假設時，具有良好的穩定性分析工具。

缺點

- 需要系統模型。
- 標準 LQR 假設線性系統。
- 標準形式不直接處理輸入及狀態限制。

## 2.3 MPC — Model Predictive Control

模型預測控制

MPC 的核心概念是：

先預測未來，再決定現在應該怎麼控制。

假設無人機要在 5 秒後抵達指定位置。

MPC 會：

1. 取得目前無人機狀態。
2. 使用數學模型預測未來數秒的運動。
3. 計算一系列可能的控制輸入。
4. 找出成本最低且滿足限制的控制序列。
5. 只執行第一個控制動作。
6. 下一個時間步重新取得狀態並計算。

這叫做 Receding Horizon Control（滾動時域控制）。

最佳化問題通常寫成：

\\[ \min\_{u_0,\ldots,u\_{N-1}} \sum\_{k=0}^{N-1} (x_k^TQx_k+u_k^TRu_k) +x_N^TQ_fx_N \\]

並且：

\\[ x\_{k+1}=f(x_k,u_k) \\]

可以加入限制：

\\[ u\_{\min}\leq u_k\leq u\_{\max} \\]

\\[ x\_{\min}\leq x_k\leq x\_{\max} \\]

優點

- 能預測未來行為。
- 可以直接加入控制輸入限制。
- 可以處理多變數控制。
- 適合軌跡追蹤與避障等問題。

缺點

- 需要模型。
- 每個控制週期都需要解最佳化問題。
- 計算量可能很大。
- 模型不準確會影響預測效果。

MPC 又分為：

- Linear MPC：使用線性模型。
- Nonlinear MPC（NMPC）：使用非線性模型。
- Robust MPC：考慮模型不確定性。
- Adaptive MPC：隨系統變化更新模型。

## 2.4 Reinforcement Learning（RL）— 強化學習

學習式控制

強化學習和 PID、LQR 最大的差異是：

RL 不一定需要事先寫出控制公式，而是透過與環境互動，學習如何做決策。

它通常包含：

- Agent：控制器。
- Environment：無人機與環境。
- State：目前狀態。
- Action：控制動作。
- Reward：獎勵。

例如無人機懸停：

| 行為      | Reward |
| ------- | ------ |
| 維持在目標位置 | +10    |
| 偏離目標位置  | -5     |
| 馬達輸出過大  | -2     |
| 無人機墜落   | -100   |

RL 希望學到一個 Policy：

\\[ a_t=\pi(s_t) \\]

讓長期累積獎勵最大化：

\\[ J(\pi)= \mathbb{E}\left[ \sum\_{t=0}^{\infty}\gamma^t r_t \right] \\]

常見演算法：

- PPO
- SAC
- TD3
- DDPG
- DQN

優點

- 能學習複雜的非線性控制策略。
- 不需要手動設計所有控制規則。
- 可以從模擬環境學習複雜行為。

缺點

- 訓練需要大量資料或環境互動。
- Reward 設計很重要。
- 訓練穩定性與泛化能力是挑戰。
- Sim-to-Real（模擬到真實世界）存在落差。
- 安全性難以直接保證。

## 2.5 End-to-End Learning（端到端學習）

學習架構

End-to-End 並不是一種特定的控制演算法，而是一種系統設計方式。

傳統控制可能是：

\\[ \text{Sensor} \rightarrow \text{State Estimation} \rightarrow \text{Controller} \rightarrow \text{Motor} \\]

每一個階段都由工程師設計。

End-to-End 則可能直接學習：

\\[ \text{Camera Image} \rightarrow \text{Neural Network} \rightarrow \text{Motor Commands} \\]

例如：

無人機攝影機看到前方障礙物，神經網路直接輸出四個馬達的控制指令。

[Model-Free Guidance Method for Drones in Complex Environments Using Direct Policy Exploration and Optimization | MDPI](https://images.openai.com/static-rsc-4/Ms7cgpptWMtF6Bu2daHkjNYhd1FKtCzmzeqlhBijtRUOyDhweq8rGqaxiOkbBYVDgvGSdwgaSgfUz0E1Usx5q4XceH_BBym9a5eFnc_Fsb2b33U1wVZ9od8ymGHoWuv4kmmElAxwunJFFlsz7CgJcNo517zblczDKlg6JavqWN8?purpose=inline)

[mdpi.com](https://www.mdpi.com/2504-446X/7/8/514?utm_source=chatgpt.com)

常見方式：

- Image-to-Action：影像直接轉成動作。
- State-to-Action：狀態直接轉成動作。
- Sensor-to-Control：感測器資料直接轉成控制訊號。

優點

- 可以整合感測、特徵提取與控制。
- 能學習傳統方法難以手動設計的複雜映射。
- 有機會減少人工設計的中間處理步驟。

缺點

- 不容易解釋為什麼做出某個控制決策。
- 需要大量且具代表性的訓練資料。
- Debug 困難。
- 不容易保證安全性。

注意：End-to-End 和 RL 並不衝突。

例如：

- End-to-End + RL：透過獎勵直接學習影像到控制動作。
- End-to-End + Imitation Learning：模仿專家控制器。
- End-to-End + Supervised Learning：利用標記資料訓練。

## 2.6 World Model（世界模型）

環境與動態建模

這是近年機器人、自主駕駛及 AI 領域非常重要的概念。

World Model 的概念是：

讓 AI 在內部建立一個可以預測環境未來狀態的模型。

例如無人機飛行時，模型需要理解：

- 無人機目前的位置。
- 目前速度。
- 馬達輸入會造成什麼變化。
- 風力會造成什麼影響。
- 障礙物的位置。
- 接下來可能發生什麼事情。

它可以學習：

\\[ s\_{t+1}=f\_\theta(s_t,a_t) \\]

其中 \\(f\_\theta\\) 是學習出來的環境動態模型。

實際上，World Model 也可能使用 Latent State（潛在狀態），而不是直接預測所有原始感測器資料。

[World Models: Learning to Dream for Efficient Reinforcement Learning - FeynmanWiki](https://images.openai.com/static-rsc-4/r6a8Ucqf-H1d1PquXj2TU2Pyzxd45jBQsW_g8JzUGfMcOPeo-T372th8jPckpZfCsMJp4bKhmCTJ1YwG92OA2Xyf4EB7TFEX0tTxebeWFEcHkqoDxGR9FAPVTGFQKiXVPoXOH0l3QzHRmT-qEKLsevHidgf5K7zlZbq_aPShFc4?purpose=inline)

[feynmanwiki.com](https://www.feynmanwiki.com/library/world-models-dc29?utm_source=chatgpt.com)

它通常包含三個部分：

1. Representation Model：把觀測資料轉換成內部狀態表示。
2. Dynamics Model：預測採取動作後會發生什麼事情。
3. Prediction Model：預測未來的狀態、獎勵或觀測。

World Model 和 MPC 的關係：

MPC 需要一個模型來預測未來。

這個模型可以是：

- 物理數學模型。
- 系統辨識建立的模型。
- 神經網路學習的模型。
- World Model。

所以可以組合：

\\[ \boxed{\text{World Model}+\text{MPC}} \\]

也可以組合：

\\[ \boxed{\text{World Model}+\text{RL}} \\]

這就是 Model-Based Reinforcement Learning 的重要方向。

例如 Dreamer 系列演算法，就是利用學習到的世界模型，在模型內部進行想像式訓練（Imagination）。

# 3. 你提到的 Limitation 是什麼？

Limitation 本身是英文「限制」，不是一種控制演算法。

如果你是想問控制工程中另一種方法，可能是以下其中一個：

- Linearization（線性化）：將非線性系統在工作點附近近似為線性模型。
- Lyapunov-based Control（李雅普諾夫控制）：利用 Lyapunov 函數分析或設計系統穩定性。

這兩個都非常值得學習。

## 3.1 Linearization（線性化）

以四軸無人機為例，真實系統是非線性的：

\\[ \dot{x}=f(x,u) \\]

在某個平衡點 \\((x_0,u_0)\\) 附近做 Taylor 展開：

\\[ \Delta\dot{x}\approx A\Delta x+B\Delta u \\]

其中：

\\[ A=\left.\frac{\partial f}{\partial x}\right|\_{x_0,u_0} \\]

\\[ B=\left.\frac{\partial f}{\partial u}\right|\_{x_0,u_0} \\]

這樣就可以將非線性系統近似成線性系統。

它本身不是 PID 或 LQR 的替代品，而是建立控制模型的重要工具。

例如：

\\[ \text{Nonlinear UAV Model} \rightarrow \text{Linearization} \rightarrow \text{LQR} \\]

## 3.2 Lyapunov Control（李雅普諾夫控制）

Lyapunov 理論主要用來研究系統穩定性。

假設存在一個函數：

\\[ V(x)>0 \\]

並且：

\\[ \dot V(x)<0 \\]

在適當的條件下，可以證明系統狀態會趨向平衡點。

它常用於：

- 非線性控制。
- 穩定性證明。
- Adaptive Control。
- Backstepping。
- Sliding Mode Control。

# 4. 還有哪些重要的控制方法？

如果你要研究 UAV、機器人或自主控制，下面這些方法也很值得認識。

## 4.1 控制工程類

[自动驾驶控制算法——滑模控制（SMC）原理与建模_smc算法-CSDN博客](https://images.openai.com/static-rsc-4/RUoGGLyggMBEQUWAkIAXF8HjOeZsTaqVWRhdcqUQ0il_ABRzAQ5rd0kYEgVru6Wj3OH5vpmCGQ6WH3fH39nrFswrERmgfOkIEXilgbGLjgn1Q4_XsqZ-UEfzzxg4WJhQjwOV4PR7O72AnpXwd79CIyRTkJp84lHncL3pCl0N3zU?purpose=inline)

Sliding Mode Control（SMC，滑動模式控制）

利用設計的滑動面，使系統狀態快速進入並維持在指定的滑動面上。

特點：對某些模型不確定性及外部擾動具有良好魯棒性，但可能產生 Chattering（抖振）。

[Control Methods for Levitation System of EMS-Type Maglev Vehicles: An Overview](https://images.openai.com/static-rsc-4/hfZnknO3WF0Sdhlxik_Y-CTHw2L6rbwLWFgkWwG3NpJqCMXGqOilTSEDzQjZhgPQFtBWgIovMh1kH7BqI9LxlxyUSycjR8Y_JZKsEik99qLmeLfcL8Ucg4Wm_tPE-geoJsjhfTFGGYkz3I5JJmaF110ezFs965fVds1ckLTqft8?purpose=inline)

Adaptive Control（適應性控制）

控制器會根據系統參數變化，自動調整控制參數。

例如：無人機電池電壓下降、負載改變，控制器調整參數以維持性能。

[Hinfinity-optimal control – B(E)3M35ORR – Optimal and Robust Control](https://images.openai.com/static-rsc-4/PjuiEu90Sz61dcdOljlpdCB6tAul2FBZDU_pny21y5o7bg1NgXs0NxvajRgykLk8i-sHwG1nqNj4m305J-2jTBBDRaLXWWBTrn3jj2NB3lC_2Mv7IAkBwUyqhPTyySSyXWrarGZZkWP52TMujsAZ3thcALe0lAAGOr5WZKGSW5Y?purpose=inline)

H∞ Control（H-infinity 控制）

以最壞情況下的擾動抑制能力為設計目標。

特點：適合需要考慮模型不確定性與外部干擾的控制系統。

[Modeling and Adaptive Backstepping Control for Quadrotor Robots with Blade Flapping : Figure 3](https://images.openai.com/static-rsc-4/lRa_ZV1ezj0o5rOR6CheOI7Str0XyAI9_fwmo8jlRhZ3GLT07y35BntFeUQA6WbX7d-yi4C-T70AHUVIzb-m6TuRAdm2JOpmM7fVmksLAHDPAVo4fkDfS3r2NDhfrw_XHsCr-pzl_A4k8Y0W2TRe6pWwSl68xkKTGAbW7SrAM-M?purpose=inline)

Backstepping Control（反推控制）

一種非線性控制設計方法，逐層設計虛擬控制輸入，最後推導出實際控制輸入。

特點：適合具有 Strict-Feedback 結構的非線性系統。

[Active Disturbance Rejection-Based Performance Optimization and Control Strategy for Proton-Exchange Membrane Fuel Cell System](https://images.openai.com/static-rsc-4/lzqcSeNygRubD5SvAIBti0mQSjYTRTx7GXFqhFI9Y2ilzmtFuoGNPSgltqiEXdhoDw2689990Q2wNUzNr9jI0ld2KqSOA7BLfhyy8c_RPXC9_SUdkZwT5qYDDRxSZBERn5kSXkdvTe5YeHSktO0XPitJu6DY6mJKqTpvwWkAVeM?purpose=inline)

ADRC（主動擾動抑制控制）

利用 Extended State Observer（ESO）估測系統中的總擾動，再進行補償。

特點：不一定需要非常精確的系統模型。

[Robust Geometric Control for a Quadrotor UAV with Extended Kalman Filter Estimation](https://images.openai.com/static-rsc-4/X4KR15Xh8XUL1YsuvrWsu5QRt6F2PpW0PKEizANmg1age-sNQSLIBdE5HaMXOumJ4NI95pIhAA-vOI4dcJK1Ap5zkvvS-i-qJhSb9oiJKvi33-aki8asa0TSgJA-jUAtfxUVez3RDhp8Qr8lpgYoNLkla02MhNvkbtQ7wOqBG7c?purpose=inline)

Geometric Control（幾何控制）

在特殊幾何空間（例如 SO(3)、SE(3)）上直接設計控制器。

特點：特別適合四軸無人機的三維姿態與位置控制。

## 4.2 機器學習與 AI 類

| 方法                 | 核心概念                                                |
| ------------------ | --------------------------------------------------- |
| Imitation Learning | 模仿專家示範的控制行為                                         |
| Behavior Cloning   | 使用監督式學習模仿專家的 State-Action                           |
| Offline RL         | 使用事先收集的資料訓練 RL                                      |
| Model-Based RL     | 使用環境模型輔助強化學習                                        |
| Model-Free RL      | 不依賴顯式環境動態模型來學習策略                                    |
| Hierarchical RL    | 將複雜任務分解成多層決策                                        |
| GAIL               | 透過 Generative Adversarial Imitation Learning 學習專家行為 |
| Residual RL        | 在傳統控制器上學習額外的修正量                                     |
| Meta-RL            | 學習如何快速適應新任務                                         |

其中我特別推薦你認識 Residual RL。

它可以結合傳統控制與 AI：

\\[ u\_{\text{total}}= u\_{\text{PID}}+u\_{\text{RL}} \\]

例如：

- PID 負責基本穩定性。
- RL 負責學習 PID 不容易處理的非線性補償。
- 再透過輸出限制與安全機制控制風險。

這比一開始就讓 RL 完全控制四個馬達，更容易建立可控的實驗架構。

# 5. 這些方法之間有什麼關係？

這是最重要的部分。你必須理解它們不是完全獨立的技術，而是可以互相組合。

例如：

組合一：傳統最適控制

UAV Nonlinear Dynamics

Linearization

LQR Controller

Motor Control

組合二：AI + MPC

Sensor Data

Neural Network / World Model

MPC Optimization

Motor Control

組合三：傳統控制 + 強化學習

State Estimation

PID / LQR

Base Controller

RL

Residual Controller

Control Command = Base + Residual

# 6. 各種方法比較

| 方法          | 需要模型     | 預測未來  | 能處理限制  | 主要特點   |
| ----------- | -------- | ----- | ------ | ------ |
| PID         | 不一定      | 否     | 間接     | 簡單、快速  |
| LQR         | 是        | 間接    | 標準形式不行 | 最適回授   |
| MPC         | 是        | 是     | 可以     | 預測與最佳化 |
| SMC         | 通常需要     | 否     | 間接     | 魯棒性    |
| Adaptive    | 通常需要部分模型 | 否     | 間接     | 自動調整   |
| H∞          | 是        | 否     | 標準形式不行 | 擾動抑制   |
| RL          | 不一定      | 視方法而定 | 需要額外設計 | 從互動學習  |
| End-to-End  | 不一定      | 視架構而定 | 不直接保證  | 直接學習映射 |
| World Model | 學習或建立模型  | 是     | 本身不負責  | 預測環境   |

補充：MPC 可以處理限制，是因為它的最佳化問題可以明確加入 Constraint；並不是所有 MPC 實作都一定有完整的安全保證。

# 7. 如果以四軸無人機研究為目標，應該怎麼學？

我會建議分成三個階段。

第一階段

建立控制工程基礎

1. PID
2. System Identification（系統辨識）
3. State-Space Model（狀態空間模型）
4. Linearization
5. Lyapunov Stability
6. LQR

目標：能建立四軸無人機的數學模型，並設計穩定的回授控制器。

第二階段

進階控制與最佳化

1. MPC / NMPC
2. Sliding Mode Control
3. Adaptive Control
4. H∞ Control
5. Geometric Control
6. Trajectory Optimization

目標：處理非線性、外部擾動、控制限制與複雜軌跡。

第三階段

AI 與自主控制

1. Reinforcement Learning
2. PPO / SAC / TD3
3. Imitation Learning
4. World Model
5. Model-Based RL
6. Residual RL
7. End-to-End Control

目標：讓無人機能從經驗中學習控制策略，並適應不同環境。

## 8. 另外不要混淆：控制、規劃、狀態估測

研究自主無人機時，還有三個不同層次：

| 領域               | 問題       | 常見方法                      |
| ---------------- | -------- | ------------------------- |
| State Estimation | 我現在在哪裡？  | Kalman Filter、EKF、UKF、VIO |
| Path Planning    | 我應該走哪條路？ | A\*、Dijkstra、RRT、RRT\*    |
| Control          | 我如何實際移動？ | PID、LQR、MPC、RL            |

例如一架自主無人機：

1. EKF 估測目前位置、速度及姿態。
2. RRT\* 規劃避開障礙物的路徑。
3. MPC 計算下一步的控制輸入。
4. PID 在底層控制馬達轉速。

這些技術可以形成一套完整的 Autonomous UAV System。

# 9. 我想確認你接下來想研究的方向

這些方法的研究方向差異很大，我想先確認你的目標。

1\. 你的主要研究對象？

UAV 四軸無人機自主飛行

Drone Hovering 懸停控制

機器人運動控制

通用控制理論

2\. 你想研究什麼？

比較不同控制器的性能

結合 RL、World Model 與傳統控制

設計一套完整的自主控制系統

了解所有方法的數學理論

3\. 希望學習的深度？

概念、原理與應用

數學原理、公式與推導

數學推導、Python / MATLAB 實作與實驗比較

確認研究方向

我認為最值得深入研究的方向是 MPC、RL、World Model 與傳統控制的結合。這樣不只是學會控制器，也能進一步研究自主飛行、環境適應及 Sim-to-Real。

你的目標其實很明確：你要做的不是單純的 PWM 風扇控制，而是 Closed-Loop RPM Control（閉迴路轉速控制）。

你希望達成的是：

> 我透過 UART 輸入目標 RPM，例如 3000 RPM，STM32 自動調整 PWM Duty Cycle，讓風扇實際轉速穩定在 3000 RPM。當負載、供電或風扇特性改變，STM32 也能自動修正 PWM，盡可能維持目標 RPM。

這個方向是正確的，而且很適合使用你目前的 STM32G431RB、TIM1/TIM8、PWM、FG（Frequency Generator）轉速回授訊號來實作。

你現在已經有的「開機從 0% 到 100% Duty，觀察對應 RPM」非常重要。這其實是建立風扇的 PWM-to-RPM Characterization（PWM 與 RPM 特性分析），可以作為後續 PID 控制器的基礎。

我建議將整個專案分成兩個階段：

1. Open-Loop Characterization：開迴路 PWM 與 RPM 特性量測。
2. Closed-Loop RPM Control：閉迴路 RPM 控制。

# 1. 你的系統應該長什麼樣子？

## STM32 Fan RPM Closed-Loop Control

VSCode Serial Monitor

UART：輸入目標 RPM、讀取目前 RPM / PWM

STM32G431RB

UART Command Parser + RPM Controller

PID Controller

RPM Error → PWM Duty Adjustment

TIM1 / TIM8 PWM

3.3 V PWM → 2N3904 Level Shifter → 5 V PWM

4-Wire PWM Fan

PWM Duty → Fan Motor → Actual RPM

FG / Tachometer Feedback

Fan 回傳脈波 → STM32 Timer Input Capture → RPM Calculation

持續回授，修正 PWM

這是一個標準的閉迴路控制系統：

\\[ \text{Target RPM} \rightarrow \text{Controller} \rightarrow \text{PWM} \rightarrow \text{Fan} \rightarrow \text{Actual RPM} \\]

接著把 Actual RPM 回傳給 Controller。

控制器每隔一段時間比較目標轉速和實際轉速：

\\[ e(t)=RPM\_{\text{target}}-RPM\_{\text{actual}} \\]

如果：

\\[ RPM\_{\text{actual}}\<RPM\_{\text{target}} \\]

就增加 PWM Duty。

如果：

\\[ RPM\_{\text{actual}}>RPM\_{\text{target}} \\]

就降低 PWM Duty。

這就是你真正要實現的功能。

# 2. 首先要理解：PWM Duty 與 RPM 並不是線性關係

你現在開機執行 0～100% Duty Sweep，這個實驗很有價值。

假設你測量得到：

| PWM Duty | RPM  |
| -------- | ---- |
| 20%      | 0    |
| 30%      | 800  |
| 40%      | 1400 |
| 50%      | 2100 |
| 60%      | 2800 |
| 70%      | 3400 |
| 80%      | 3900 |
| 90%      | 4300 |
| 100%     | 4500 |

以上是示意數據，不是你的風扇實測結果。

你可以看到：

- 20% 可能無法啟動風扇。
- 30%～60% 可能有較大的 RPM 變化。
- 80%～100% 可能逐漸進入飽和區域。

因此：

\\[ RPM \neq K \times Duty \\]

不能直接假設 Duty 50% 就是最大 RPM 的一半。

這也是為什麼不能只使用固定 PWM 對應 RPM 的方式，來實現精準轉速控制。

你需要的是 RPM Feedback。

# 3. RPM 要如何測量？FG 訊號是整個系統的關鍵

你目前的風扇有四條線：

| 線路        | 功能     |
| --------- | ------ |
| 12 V      | 風扇電源   |
| GND       | 電源地    |
| PWM       | 外部控制轉速 |
| FG / Tach | 回傳轉速脈波 |

FG 是風扇回傳給 STM32 的轉速訊號。

例如風扇每轉一圈輸出 2 個 Pulse（很多四線風扇採用此規格，但必須確認你的風扇 Datasheet）。

假設：

- 每轉 2 個 Pulse。
- 一秒收到 100 個 Pulse。

那麼：

\\[ RPM=\frac{100}{2}\times60 \\]

\\[ \boxed{RPM=3000} \\]

一般化公式：

\\[ \boxed{RPM=\frac{f\_{FG}\times60}{PPR}} \\]

其中：

- \\(f\_{FG}\\)：FG 頻率，Hz。
- \\(PPR\\)：每轉輸出的脈波數（Pulses Per Revolution）。

## STM32 如何讀取 FG？

我建議你使用 TIM Input Capture（輸入捕獲），而不是單純使用 GPIO polling。

[STM32 Nucleo Timer Input Capture Mode Frequency Measurement](https://images.openai.com/static-rsc-4/jfRlhF0uz-GPZPzrHU7kuQGMPgr6Y1ntWalh7dqcafvq3ILspWo0OMaP745Sq7bqW5KR7xmCRlWITREttfMhsw08r6aU1sA2H1V-G5L9ZUBurqNUdkE_CGvpS8P7DBzQJOs78OYI4FiJ6RKWjaVKxmL6Kn0BI6TaH9Ku-nFPwnE?purpose=inline)

[microcontrollerslab.com](https://microcontrollerslab.com/stm32-nucleo-timer-input-capture-mode-frequency-measurement-example/?utm_source=chatgpt.com)

例如：

假設 TIM 計數器頻率是 1 MHz。

代表每個 Counter Count：

\\[ T\_{\text{tick}}=1\mu s \\]

兩次 FG Rising Edge 的捕獲值：

\\[ CCR_1=1000 \\]

\\[ CCR_2=11000 \\]

那麼：

\\[ \Delta CCR=11000-1000=10000 \\]

因此：

\\[ T\_{FG}=10000\times1\mu s=10ms \\]

\\[ f\_{FG}=\frac{1}{0.01}=100Hz \\]

如果 PPR = 2：

\\[ RPM=\frac{100\times60}{2} \\]

\\[ \boxed{RPM=3000} \\]

這種方式的優點是直接利用硬體捕獲時間，不需要 CPU 不斷輪詢 FG 腳位。

重要： FG 通常是 Open-Collector 輸出，必須依照風扇規格配置適當的 Pull-up。不能直接假設 FG 一定是 5 V 或 3.3 V。STM32G431 的 GPIO 不可承受超過規格的輸入電壓。

# 4. 你使用 2N3904 和 TIM_OCPOLARITY_LOW 是正確方向嗎？

這部分需要特別注意，因為你目前的 PWM 訊號經過 NPN 電晶體轉換。

你使用：

- STM32 TIM1 / TIM8 輸出 3.3 V PWM。
- 2N3904 NPN。
- 風扇 PWM 控制端需要 5 V 邏輯介面。

典型接法如下：

[pwm - 5V 4-pin Noctua A4X10 on Raspberry Pi - Electrical Engineering Stack Exchange](https://images.openai.com/static-rsc-4/ldHP3oXlrL4LB5pYUK5InA-gNOq6FLzr1TlJYb3_cPgVLrv1-IGy_uPQ6bLhioWGCaAPngn46hITS7rqW4MojQKWpm33wxi1ANVpn6WiYsGgrmM3pWbz9JA8gXVmoDdlh92Q9ZgT_uqW4nBvYyFEW9LPvxAChVq-C0NLEJ4W1Yg?purpose=inline)

[electronics.stackexchange.com](https://electronics.stackexchange.com/questions/446128/5v-4-pin-noctua-a4x10-on-raspberry-pi?utm_source=chatgpt.com)

其工作原理：

當 STM32 輸出 High（3.3 V）：

1. 2N3904 Base 有電流。
2. Transistor 導通。
3. Collector 被拉向 GND。
4. 風扇 PWM 接收到 Low。

當 STM32 輸出 Low（0 V）：

1. 2N3904 截止。
2. Collector 不再被拉低。
3. 風扇內部 Pull-up 將 PWM 拉高至約 5 V。

所以這是一個反相電路：

| STM32 輸出 | 2N3904 | 風扇 PWM |
| -------- | ------ | ------ |
| High     | ON     | Low    |
| Low      | OFF    | High   |

因此：

\\[ D\_{\text{fan}}=1-D\_{\text{STM32}} \\]

這也是你使用：

```
TIM_OCPOLARITY_LOW
```

時需要注意的地方。

但要特別區分：

- `TIM_OCPOLARITY_LOW` 是設定 STM32 Timer Output Compare 的輸出極性。
- 2N3904 會再造成一次反相。
- 最後真正的風扇 Duty 必須以示波器量測 Collector 端的波形為準。

不要只看 STM32 的 CCR 數值，就認定它等於風扇收到的 Duty。

另外，標準四線 PWM 風扇通常採用約 25 kHz PWM 控制，並要求開集極／開汲極驅動。你的 2N3904 接法要符合風扇的輸入電氣規格，不能把風扇 PWM 腳當成一般推挽式 5 V 輸入。

# 5. 真正控制 RPM：PID Controller

接下來才是你的核心研究。

你希望：

\\[ RPM\_{\text{target}}=3000 \\]

但是實際測量：

\\[ RPM\_{\text{actual}}=2500 \\]

因此：

\\[ e=3000-2500=500 \\]

PID 根據這個誤差計算 PWM 的調整量。

離散 PID 可以寫成：

\\[ u[k]=K_pe[k]+K_i\sum\_{i=0}^{k}e[i]T_s+ K_d\frac{e[k]-e[k-1]}{T_s} \\]

其中：

- \\(K_p\\)：比例增益。
- \\(K_i\\)：積分增益。
- \\(K_d\\)：微分增益。
- \\(T_s\\)：控制週期。

你的 PWM Duty 可以採用增量式更新：

\\[ D[k]=D[k-1]+u[k] \\]

並限制：

\\[ 0\leq D[k]\leq100\\% \\]

但在你的系統，我更建議先實作具有輸出限制、積分防飽和（Anti-windup）的 PID。

## 實際控制流程

假設：

## RPM = 3000 控制範例

Target RPM

# 3000

Actual RPM

# 2500

# Error = +500 RPM

PID Controller

計算 PWM 修正量

原 Duty

# 50%

新 Duty

# 55%

55% 僅為示意，實際修正量由 PID 增益決定。

假設下一次讀取：

\\[ RPM\_{\text{actual}}=2800 \\]

誤差變成：

\\[ e=3000-2800=200 \\]

PID 再繼續調整 PWM。

最後：

\\[ RPM\_{\text{actual}}\approx3000 \\]

這才是你想要的功能。

# 6. 我建議你的 STM32 軟體架構

不要把所有程式都塞在 `main.c`。建議把風扇控制拆成幾個獨立模組。

```
FANPWM/
│
├── Core/
│   ├── Inc/
│   │   ├── fan_control.h
│   │   ├── fan_pid.h
│   │   ├── fan_rpm.h
│   │   └── uart_command.h
│   │
│   └── Src/
│       ├── fan_control.c
│       ├── fan_pid.c
│       ├── fan_rpm.c
│       └── uart_command.c
│
└── Core/Src/main.c
```

各個模組負責：

| Module         | 工作                      |
| -------------- | ----------------------- |
| `fan_control`  | PWM 啟動、停止、Duty 設定       |
| `fan_pid`      | PID 計算                  |
| `fan_rpm`      | FG Input Capture、RPM 計算 |
| `uart_command` | UART 命令解析與資料輸出          |
| `main.c`       | 初始化及系統整合                |

## 6.1 控制週期

我建議第一版先使用：

| 項目                 | 建議初始值                |
| ------------------ | -------------------- |
| PWM Frequency      | 25 kHz               |
| RPM Measurement    | 100 ms 更新一次          |
| PID Control Period | 100 ms               |
| UART Baud Rate     | 115200               |
| UART Telemetry     | 100～200 ms           |
| PID Output         | 0～100%               |
| RPM Filter         | Moving Average / EMA |

這些是初始實驗參數，不是最終最佳值。特別是 RPM 更新頻率，要依風扇轉速、PPR 和低速時的脈波間隔調整。

## 6.2 UART 命令設計

我建議使用簡單的文字命令，這樣你在 VSCode Serial Monitor 就可以直接操作。

| UART Command         | 功能              |
| -------------------- | --------------- |
| `SET 3000`           | 設定目標 RPM        |
| `SET 4500`           | 設定目標 RPM 為 4500 |
| `STOP`               | 停止風扇            |
| `OPEN 50`            | 開迴路 PWM 50%     |
| `CLOSED`             | 啟用閉迴路 PID       |
| `STATUS`             | 顯示目前系統狀態        |
| `SWEEP`              | 執行 PWM Sweep    |
| `PID 0.1 0.02 0.001` | 設定 PID 參數       |

例如你在 Serial Monitor 輸入：

```
SET 3000
```

STM32 回傳：

```
[COMMAND] Target RPM = 3000

[CONTROL]
Target RPM : 3000
Actual RPM : 2500
Error      : 500
PWM Duty   : 55.0 %
PWM CCR    : 2200
Mode       : CLOSED_LOOP
```

當轉速穩定後：

```
[CONTROL]
Target RPM : 3000
Actual RPM : 2998
Error      : 2
PWM Duty   : 48.5 %
PWM CCR    : 1940
Mode       : CLOSED_LOOP
```

這些數字同樣是示意。

## 6.3 你應該收集哪些實驗數據？

這對你的研究非常重要。

我建議 UART 每 100～200 ms 輸出一筆 CSV：

```
timestamp,target_rpm,actual_rpm,error,pwm_duty,pwm_ccr
0,3000,0,3000,0,0
100,3000,1200,1800,35.0,1400
200,3000,2100,900,42.0,1680
300,3000,2600,400,48.0,1920
400,3000,2850,150,50.0,2000
500,3000,2998,2,48.5,1940
```

這樣你就可以用 Python 或 Excel 繪製：

圖表一：Target RPM vs Actual RPM

[Closed-Loop Speed Control of a DC Motor: New in Wolfram Language 12](https://images.openai.com/static-rsc-4/T2LFcacu3HwH5o3hgbtGHPKsxzfkVeMTinVum8QQaD_9UPT5Hd1O0F_RVl0j5naUsjjT5BI-xr8NAqFzbk17raPsKp6bf1eUt84s4MJ6HKXpgsdlNLxhGatUOtGrHqEYB1b3umAm_yBH2pM3AXhOi9zsaf9cb954aFSDDjjWZKQ?purpose=inline)

[wolfram.com](https://www.wolfram.com/language/12/microcontroller-kit/closed-loop-speed-control-of-a-dc-motor.html?utm_source=chatgpt.com)

用來觀察轉速追蹤能力、超越量、穩定時間。

圖表二：PWM Duty vs RPM

[ARCTIC S8038 - 10K - User Manual](https://images.openai.com/static-rsc-4/4hUqk8ZH6Ny6BwpMSCGCiUtQlS82N_T27xV2Qobdp0-Wat1YuqvrwV1t4MBb69YUgRd7aEKse4c7pTc8R9DUopSo_t73Mk_uirM0ac9Ha_W3TxHam3WBSzL29K9QwpvPOPM2P_EX6G2Zgb5dwQPdkJ5dVGUEGkjewCUhwa0wqQ8?purpose=inline)

[support.arctic.de](https://support.arctic.de/S8038-10K?utm_source=chatgpt.com)

用來分析風扇的非線性特性。

圖表三：RPM Error vs Time

[Optimal Fractional-Order Active Disturbance Rejection Controller Design for PMSM Speed Servo System | MDPI](https://images.openai.com/static-rsc-4/gnFh0Wirih88Jf_lmM_SV-B5zUeFdzbP6dnDgcTBFZ1gvvfBXOS88dFmu-xyPywozoajcic6eDsrxsW5SQcN7iX4Zt_CNmwHJ8Xw2S8nh71fKf-NYYYQqAUUHLsmj34ARU4YIYitVUGnXl3ahWdEYjYPbqSDDK8TDBebpRGOjWM?purpose=inline)

[mdpi.com](https://www.mdpi.com/1099-4300/23/3/262?utm_source=chatgpt.com)

用來觀察穩態誤差與控制器收斂速度。

# 7. 你目前的 PWM Sweep 程式還需要注意什麼？

你說開機會從 0～100% Duty，測試對應 RPM。

這個方式很好，但我建議你不要只記錄 Duty 和 RPM，還要考慮以下因素。

第一：啟動死區（Starting Threshold）

風扇可能在 20% Duty 無法啟動，但是在 40% 可以啟動。

而且啟動時需要的 Duty 可能比維持轉動時高。

因此要分別測試：

- 從停止狀態啟動所需的最低 Duty。
- 已經運轉時可以維持轉動的最低 Duty。

第二：RPM Hysteresis（遲滯現象）

例如：

- Duty 從 30% 上升到 50%，RPM 是 2000。
- Duty 從 70% 下降到 50%，RPM 卻是 2150。

這可能來自風扇的機械慣性、控制器內部特性或測量條件差異。

所以建議你做兩組實驗：

- UP Sweep：0% → 100%。
- DOWN Sweep：100% → 0%。

第三：啟動時的 Kick-start

如果風扇從停止狀態開始啟動，可以先給一段較高 Duty，持續一小段時間，再切換到目標 RPM 控制。

但 Kick-start 時間與 Duty 必須透過實驗決定，不能任意設定。

第四：RPM 不要直接使用未處理的原始數值

FG 可能存在脈波抖動，建議先計算 RPM，再使用 EMA：

\\[ RPM\_{filtered}[k] = \alpha RPM[k]+(1-\alpha)RPM\_{filtered}[k-1] \\]

這可以降低 RPM 讀值的波動。

但濾波太強會增加回授延遲，所以必須在穩定性與反應速度之間取捨。

# 8. 你最終可以研究哪些控制演算法？

你不必永遠只使用 PID。當第一版完成後，可以進行控制器比較。

| 控制器                    | 適合研究的問題                          |
| ---------------------- | -------------------------------- |
| Open-loop PWM          | PWM 與 RPM 的基本關係                  |
| PID                    | 基本閉迴路 RPM 控制                     |
| PI                     | RPM 控制是否不需要微分項                   |
| Gain Scheduling        | 不同 RPM 區間使用不同 PID 參數             |
| Feedforward + PID      | 利用 Duty-RPM 特性預先估計 PWM，再由 PID 修正 |
| Fuzzy PID              | 使用模糊邏輯調整 PID                     |
| Adaptive PID           | 根據風扇狀態調整控制增益                     |
| MPC                    | 在 PWM 限制下最佳化轉速響應                 |
| Reinforcement Learning | 讓模型學習 PWM 調整策略                   |

其中我最推薦你下一階段研究：

最推薦的進階方向

Feedforward + PID

單純 PID：

\\[ PWM=PID(Error) \\]

Feedforward + PID：

\\[ \boxed{PWM=PWM\_{feedforward}+PWM\_{PID}} \\]

先利用你 Sweep 得到的 Duty-RPM 對照資料，估算目標 RPM 所需的 Duty。

例如：

\\[ RPM\_{target}=3000 \\]

查表得到：

\\[ PWM\_{feedforward}=55\\% \\]

接著 PID 只需要補償實際誤差。

這樣通常比單純從很低的 Duty 開始讓 PID 慢慢調整，更容易得到快速且平穩的響應。

[Comparison among some well known control schemes with different tuning methods | Journal of Applied Research and Technology. JART](https://images.openai.com/static-rsc-4/QzkZcuBLr3DmBpm0TuumqWdlRS1uIDPPF1Zo9YAap43Y66wb2Hz5N1MA2PaOlmk5H5uuMFIjwVqPBH-VOBnQWdoLiIeRU_9xCvHb-8LTK_BHM6JhUz6JaAhFFiaMsNG83NK01vm0BU8r_kdYGIlULqOEegUJgbWKoYi_Eg14FHw?purpose=inline)

[elsevier.es](https://www.elsevier.es/en-revista-journal-applied-research-technology-jart-81-articulo-comparison-among-some-well-known-S1665642315000358?utm_source=chatgpt.com)

# 9. 我建議我們實際開發的順序

不要一開始就寫 PID。先確保每一個環節正確，否則 RPM 不穩定時，很難判斷是硬體、FG 測量還是控制器造成的。

1. Step 1：PWM Hardware Validation

   確認 TIM1/TIM8 的 25 kHz、2N3904 電路、輸出極性，以及風扇端實際 Duty。
2. Step 2：FG RPM Measurement

   使用 Timer Input Capture，確認 RPM 計算準確性，並與示波器量測比較。
3. Step 3：Open-loop Characterization

   執行 UP/DOWN Sweep，建立完整的 Duty-RPM 對照表，找出啟動門檻與最低穩定轉速。
4. Step 4：UART Monitoring

   完成目標 RPM、實際 RPM、PWM Duty、Error 的即時監控與 CSV 記錄。
5. Step 5：PI / PID Controller

   實作閉迴路，測試不同目標 RPM 的追蹤能力。
6. Step 6：Advanced Controller

   比較 PI、PID、Feedforward + PID、Gain Scheduling 等方法。

最後，你可以用以下指標評估控制品質：

- Steady-State Error：穩態轉速誤差。
- Overshoot：轉速超越量。
- Settling Time：穩定時間。
- Rise Time：上升時間。
- RPM Ripple：穩態 RPM 波動。
- Disturbance Rejection：外部擾動下的轉速維持能力。

## 10. 開始實作前，我需要確認三件事

我想先確認你的硬體和目前程式的實際狀況，這樣接下來才能直接針對 STM32G431RB 設計，而不是給你一份不符合硬體的通用 PID 程式。

1\. 你的風扇 FG 是幾個 Pulse / Revolution？

2 PPR

4 PPR

不確定，需要確認 Datasheet

2\. 你的風扇最大 RPM 大約多少？

3000 RPM

4500 RPM

6000 RPM

不確定，想先量測

3\. 目前 FG 測量進度？

已經可以讀取 FG 並計算 RPM

有 FG 訊號，但 RPM 計算還不準

還沒完成 FG Input Capture

提交硬體資訊，開始實作

另外，下一步最好提供目前的 `main.c`、`fan_control.c`、`fan_control.h` 和 CubeMX 的 TIM1/TIM8 設定。

我們可以直接在你現有的 FANPWM 專案上開發，保留目前的 2N3904、TIM1/TIM8、FG 和 UART 架構，不需要推翻重做。

這六個其實都在回答同一個問題：怎麼從量測到的狀態，算出該給執行器什麼指令。差別在於你願意假設多少關於系統的知識，以及把計算放在線上還是離線。你列的 limitation 我讀成「各方法的限制」，所以下表把每個方法是什麼、卡在哪裡，以及放進 MCU 要付出的代價放在一起：

| 方法 | 它是什麼 | 主要限制 | 放進 MCU 的成本 |
|---|---|---|---|
| PID | 用誤差的「現在、累積、變化率」加權：`u = Kp·e + Ki·∫e + Kd·ė`，不需要模型 | 本質是單輸入單輸出，多軸耦合只能拆成多個迴路硬做；執行器飽和時會積分飽和（windup）；微分項放大雜訊；一組增益只對一個工作點好；不處理限制條件，也不保證最佳 | 極低，每個週期只有幾個乘加，沒有 FPU 也能用定點數跑 |
| LQR | 對線性模型 `ẋ = Ax + Bu` 最小化 `∫(xᵀQx + uᵀRu)dt`，解 Riccati 方程得到最佳增益 `u = −Kx` | 只在線性化的工作點附近成立；需要全狀態，量不到就得加 Kalman filter（LQG），而 LQG 會失去 LQR 本來的穩定裕度保證；不處理輸入限幅；Q、R 仍要靠經驗調 | 低，K 離線算好，線上只是 m×n 次乘加 |
| MPC | 每個週期用模型預測未來 N 步，在限制條件下解最佳化，只執行第一步，下個週期重算 | 要線上解 QP 或 NLP，最壞求解時間必須小於取樣週期；吃模型準度與狀態估測；視窗、權重、終端條件都要設計 | 中到高。小型線性問題可用 OSQP、qpOASES、acados 產生的程式碼，或 TinyMPC 這類 MCU 專用求解器，在 Cortex-M4/M7 上做到數百 Hz 等級（視狀態數與視窗長度）；非線性 MPC 通常要更強的處理器 |
| RL | 在與環境互動中學出能最大化累積獎勵的策略 `π(a∣s)`（常見 PPO、SAC） | 需要大量互動，幾乎只能先在模擬器訓練；sim-to-real 落差；獎勵函數難設計且會被鑽漏洞；探索在真機上不安全；沒有穩定性保證，也難除錯 | 推論低、訓練高。策略多半是小型 MLP，量化後 Cortex-M 級 MCU 跑得動；訓練在 PC 或 GPU 上完成 |
| End-to-end（端到端） | 不切模組，直接從原始感測（影像、IMU、光達）映射到執行器指令，可用模仿學習或 RL 訓練 | 黑箱，難驗證與認證；要大量資料；遇到訓練分佈外的長尾情境會失效；很難硬性加入安全限制；出錯時分不出是哪一層的問題 | 影像輸入需要 GPU 或 NPU；只有 IMU 到馬達這類低維輸入的小模型才放得進 MCU |
| World model | 學一個預測 `s′ ∼ p(s′∣s, a)` 的模型（常在潛在空間），用來預演、規劃，或在「想像」裡訓練策略（如 Dreamer、MuZero） | 預演越長誤差越累積；策略會鑽模型的漏洞（model exploitation）；高維觀測難學、不確定性難估；訓練成本高 | 訓練高；拿來做線上規劃時，成本約等於 MPC 再加神經網路推論，多半要較強的運算平台 |

這幾個方法不是互相取代，而是一條連續的光譜：

- PID → LQR：都是回授，但 PID 只看誤差，LQR 看整個狀態向量，並用二次成本明確定義什麼叫「最佳」。
- LQR → MPC：MPC 可以看成「加上限制條件、每個週期重解一次的有限視窗 LQR」；沒有限制條件且視窗夠長時，它的解就等於 LQR。
- MPC → RL：兩者都在最佳化累積成本。MPC 每次都在線上用模型現算，RL 則是離線把這個計算「攤提」成一個策略網路，線上只剩一次前向傳播。
- World model：讓 MPC 或 RL 用的那個模型不必手寫，而是由資料學出來。拿它做線上規劃就是學習式 MPC，在它裡面「想像」訓練策略就是 model-based RL。
- End-to-end：這是架構選擇而不是演算法，意思是不切「感知、規劃、控制」模組；裡面那個網路用模仿學習或 RL 訓練都可以。

實務上的差距沒有看起來那麼大：多數量產的馬達驅動與飛控，底層仍是 PI/PID（例如 FOC 的電流迴路、PX4 的姿態與角速度迴路），但 2023 年發表在 Nature 的 Swift 系統，也已經用深度 RL 在無人機競速中贏過人類世界冠軍等級的飛手。

至於「還有什麼其他方法」，大致可以依它們在解決什麼問題來分：

| 類別 | 代表方法 | 在解決什麼 |
|---|---|---|
| 擴充 PID | 串級、前饋加回授、增益排程（gain scheduling）、Smith predictor、ADRC（自抗擾控制） | 多層迴路、已知擾動、工作點改變、時間延遲、未建模的擾動 |
| 非線性與強健 | Feedback linearization、NDI／INDI、Backstepping、Sliding mode（滑動模式控制）、H∞ | 系統非線性或模型有不確定時仍要穩定；滑動模式的代價是高頻抖振（chattering） |
| 適應 | MRAC、L1 adaptive、線上參數估測 | 負載、電池電壓、溫度造成的參數漂移 |
| 狀態估測 | Kalman filter／EKF／UKF、MHE、互補濾波 | 量不到的狀態要先估出來；`LQG = LQR + Kalman filter` |
| 軌跡與幾何 | Differential flatness 加 minimum-snap、SO(3) geometric control | 欠驅動系統（如四旋翼）的軌跡產生與姿態控制 |
| 馬達專用 | FOC（磁場導向控制）、DTC（直接轉矩控制）、PR／repetitive control | BLDC、PMSM 的電流與轉矩，以及週期性擾動（如轉矩漣波） |
| 示範學習 | Behavior cloning、DAgger、Diffusion Policy、VLA（視覺－語言－動作模型） | 有人類示範，但不想設計獎勵函數 |
| 傳統加學習 | Residual RL、GP 或神經網路 MPC、Koopman operator、CBF／Safe RL | 保留傳統控制的結構或安全保證，再用學習補模型不準的部分 |

最後留一個問題給你想：如果你的系統模型很難建，但手上有便宜又夠準的模擬器，而且輸出有嚴格限幅，你會選上面哪一類方法，為什麼？想好了告訴我你的判斷，我們再一起檢驗。要往下挖某一個方法，直接按圖下方的「深入」按鈕也可以。