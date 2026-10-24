# 離線語音模型比較：本機實測

測試日期：2026-10-25。CPU：AMD Ryzen 5 7600X3D 6-Core Processor；CPU 推論固定 4 執行緒，沒有使用 GPU。

本報告記錄切換前的 Whisper Base 基準與候選引擎比較。0.2.0 已依結果切換為 SenseVoice Small INT8、一秒暫定字幕更新；本報告的原始量測資料保留不變。

## 測試方式

- 四段相同音檔：英文合成、臺灣普通話合成、中英混用合成、自然普通話。前三段有獨立的合成文字標準稿；自然語音不計錯誤率。
- 整段辨識：各模型暖機後每段重複 3 次。表格列中位數，翻譯與辨識分開計時。
- 串流回放：每 100 毫秒按真實牆鐘送入音訊，每段重複 2 次。Whisper/SenseVoice 使用現有 Worker、Silero VAD、2 秒暫定更新及 8 秒最長分段；Paraformer 使用原生串流解碼，翻譯更新最多每 0.5 秒一次。
- 共用相同 OPUS-MT CPU INT8 與 OpenCC。兩種路徑停頓門檻均設定為 0.64 秒，但端點演算法不同；每段尾端送入 2 秒靜音。
- 額外探索組將 SenseVoice 的暫定更新間隔由 2 秒縮為 1 秒，其餘流程相同；獨立保留結果，不覆寫原先的對照組。
- Paraformer 另測原生預設端點參數：語音後靜音 1.2 秒、最長語句 20 秒（開啟端點偵測）。此組獨立保留，用來檢查過早切段的影響。
- 首字幕延遲＝第一則非空繁中字幕送出時間減共同 VAD 推估的語音開始；句末延遲＝最後一則完成字幕送出時間減共同 VAD 推估的最後語音結束。不是單字逐字時間對齊。
- 時間涵蓋辨識、等待分段與翻譯，不含原生收音、具名管道與 WPF 繪製；這是候選引擎的即時回放測試，不是新引擎的桌面整合驗收。
- 推論期間以 socket guard 禁止 Python 連線；下載模型另行執行。所有候選均使用本機檔案。

## 整段辨識時間

| 模型 | 音檔 | 音檔長度（秒） | 辨識（秒） | 翻譯／繁中轉換（秒） | 辨識 RTF |
|---|---|---:|---:|---:|---:|
| Whisper Base INT8 | 英文合成語音 | 7.82 | 0.600 | 0.027 | 0.077 |
| Whisper Base INT8 | 臺灣普通話合成語音 | 9.52 | 0.616 | 0.000 | 0.065 |
| Whisper Base INT8 | 中英混用合成語音 | 8.07 | 0.625 | 0.025 | 0.077 |
| Whisper Base INT8 | 自然普通話（無標準稿） | 5.61 | 0.618 | 0.000 | 0.110 |
| SenseVoice Small INT8 | 英文合成語音 | 7.82 | 0.176 | 0.027 | 0.022 |
| SenseVoice Small INT8 | 臺灣普通話合成語音 | 9.52 | 0.192 | 0.000 | 0.020 |
| SenseVoice Small INT8 | 中英混用合成語音 | 8.07 | 0.181 | 0.026 | 0.022 |
| SenseVoice Small INT8 | 自然普通話（無標準稿） | 5.61 | 0.119 | 0.000 | 0.021 |
| Streaming Paraformer INT8（0.64 秒端點） | 英文合成語音 | 7.82 | 0.366 | 0.040 | 0.047 |
| Streaming Paraformer INT8（0.64 秒端點） | 臺灣普通話合成語音 | 9.52 | 0.421 | 0.000 | 0.044 |
| Streaming Paraformer INT8（0.64 秒端點） | 中英混用合成語音 | 8.07 | 0.374 | 0.041 | 0.046 |
| Streaming Paraformer INT8（0.64 秒端點） | 自然普通話（無標準稿） | 5.61 | 0.260 | 0.000 | 0.046 |

RTF＝辨識耗時／音檔長度；低於 1 表示整段辨識快於音訊長度，不能直接當成字幕延遲。

## 即時回放字幕延遲

| 模型 | 音檔 | 首字幕延遲（秒） | 最後句末延遲（秒） | EOF 才完成的次數 |
|---|---|---:|---:|---:|
| Whisper Base INT8 | 英文合成語音 | 2.477 | 1.614 | 0/2 |
| Whisper Base INT8 | 臺灣普通話合成語音 | 2.668 | 2.075 | 0/2 |
| Whisper Base INT8 | 中英混用合成語音 | 2.647 | 1.579 | 0/2 |
| Whisper Base INT8 | 自然普通話（無標準稿） | 2.416 | 1.532 | 0/2 |
| SenseVoice Small INT8 | 英文合成語音 | 2.022 | 1.189 | 0/2 |
| SenseVoice Small INT8 | 臺灣普通話合成語音 | 2.029 | 0.980 | 0/2 |
| SenseVoice Small INT8 | 中英混用合成語音 | 2.061 | 1.069 | 0/2 |
| SenseVoice Small INT8 | 自然普通話（無標準稿） | 1.846 | 1.043 | 0/2 |
| SenseVoice Small INT8（1 秒更新，探索組） | 英文合成語音 | 1.004 | 1.173 | 0/2 |
| SenseVoice Small INT8（1 秒更新，探索組） | 臺灣普通話合成語音 | 1.014 | 0.992 | 0/2 |
| SenseVoice Small INT8（1 秒更新，探索組） | 中英混用合成語音 | 1.014 | 1.072 | 0/2 |
| Streaming Paraformer INT8（0.64 秒端點） | 英文合成語音 | 0.702 | 1.466 | 0/2 |
| Streaming Paraformer INT8（0.64 秒端點） | 臺灣普通話合成語音 | 0.600 | 0.859 | 0/2 |
| Streaming Paraformer INT8（0.64 秒端點） | 中英混用合成語音 | 0.599 | 1.165 | 0/2 |
| Streaming Paraformer INT8（0.64 秒端點） | 自然普通話（無標準稿） | 0.407 | 1.100 | 0/2 |
| Streaming Paraformer INT8（原生預設端點，探索組） | 英文合成語音 | 0.656 | 1.489 | 0/2 |
| Streaming Paraformer INT8（原生預設端點，探索組） | 臺灣普通話合成語音 | 0.599 | 1.459 | 0/2 |
| Streaming Paraformer INT8（原生預設端點，探索組） | 中英混用合成語音 | 0.599 | 3.618 | 0/2 |

EOF 欄表示送完 2 秒尾端靜音後仍需明確結束輸入才能完成最後片段；這種完成時間包含測試的結束策略。

## 標準稿比對

| 模型 | 模式 | 英文 WER | 中文 CER | 中英混用 CER |
|---|---|---:|---:|---:|
| Whisper Base INT8 | 整段 | 0.00% | 0.00% | 0.00% |
| Whisper Base INT8 | 串流回放 | 0.00% | 696.88% | 0.00% |
| SenseVoice Small INT8 | 整段 | 0.00% | 0.00% | 1.79% |
| SenseVoice Small INT8 | 串流回放 | 0.00% | 3.12% | 7.14% |
| SenseVoice Small INT8（1 秒更新，探索組） | 串流回放 | 0.00% | 3.12% | 7.14% |
| Streaming Paraformer INT8（0.64 秒端點） | 整段 | 12.50% | 0.00% | 8.93% |
| Streaming Paraformer INT8（0.64 秒端點） | 串流回放 | 6.25% | 3.12% | 8.93% |
| Streaming Paraformer INT8（原生預設端點，探索組） | 串流回放 | 12.50% | 0.00% | 8.93% |

比對先統一大小寫、繁簡、標點及範例中的 nine／9、九點／9點格式。CER 包含插入、刪除及替換，因此大量重複輸出可超過 100%。中英混用 CER 以去除空白後的字元計算，不等同跨語言詞錯誤率。

## 辨識內容（每個條件的第一次）

### Whisper Base INT8／batch

**英文合成語音**

Hello everyone. Today we will discuss the project schedule. The meeting starts at 9 tomorrow morning.

**臺灣普通話合成語音**

大家好,今天我們討論專案進度。明天上午九點開會,請準備測試報告,謝謝大家。

**中英混用合成語音**

今天的會議討論 Project Schedule,請在 Tomorrow morning 準備好 Test Report,謝謝大家。

**自然普通話（無標準稿）**

對我做了介紹,我想說的是,大家如果對我的研究感興趣呢。

### Whisper Base INT8／stream

**英文合成語音**

Hello everyone. Today we will discuss the project schedule. The meeting starts at 9 tomorrow morning.

**臺灣普通話合成語音**

大家好,今天我們討論專案進度。 請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下,請問一下

**中英混用合成語音**

今天的會議討論 Project Schedule,請在 Tomorrow morning 準備好 Test Report,謝謝大家。

**自然普通話（無標準稿）**

對我做了介紹,我想說的是,大家如果對我的研究感興趣呢。

### SenseVoice Small INT8／batch

**英文合成語音**

Hello everyone Today we will discuss the project schedule The meeting starts at nine tomorrow morning.

**臺灣普通話合成語音**

大家好，今天我们讨论专案进度，明天上午9点开会，请准备测试报告，谢谢大家。

**中英混用合成語音**

今天的会议讨论project schedule，请在tmorrow morning准备好 test report，谢谢大家。

**自然普通話（無標準稿）**

对我做了介绍啊，那么我想说的是呢，大家如果对我的研究感兴趣呢嗯。

### SenseVoice Small INT8／stream

**英文合成語音**

Hello everyone Today we will discuss the project schedule The meeting starts at nine tomorrow morning.

**臺灣普通話合成語音**

大家好，今天我们讨论专案进度，明天上午9点开会，请准备测试报告，谢谢。 谢大家。

**中英混用合成語音**

今天的会议讨论project scheduleule，请在tmorrow morning准备好 test report，谢谢大家。

**自然普通話（無標準稿）**

对我做了介绍啊，那么我想说的是呢，大家如果对我的研究感兴趣呢。

### SenseVoice Small INT8（1 秒更新，探索組）／stream

**英文合成語音**

Hello everyone Today we will discuss the project schedule The meeting starts at nine tomorrow morning.

**臺灣普通話合成語音**

大家好，今天我们讨论专案进度，明天上午9点开会，请准备测试报告，谢谢。 谢大家。

**中英混用合成語音**

今天的会议讨论project scheduleule，请在tmorrow morning准备好 test report，谢谢大家。

### Streaming Paraformer INT8（0.64 秒端點）／batch

**英文合成語音**

hello everyone today we will discuss the project schedule the meeting starts said nine tomorrow mor

**臺灣普通話合成語音**

大家好今天我们讨论专案进度明天上午九点开会请准备测试报告谢谢大家

**中英混用合成語音**

今天的会议讨论 project skedudule 请在 tomorrow morning 准备好 test report 谢谢大

**自然普通話（無標準稿）**

对我做了介绍啊那么我想说的是呢大家如果对我的研究感兴趣呢

### Streaming Paraformer INT8（0.64 秒端點）／stream

**英文合成語音**

hello everyone today we will discuss the project schedu the meeting starts at nine tomorrow morning

**臺灣普通話合成語音**

大家好今天我们讨论专案进 明天上午九点开会请准备测试报告谢谢大家

**中英混用合成語音**

今天的会议讨论 project skedudule 请在 tomorrow morning 准备好 test report 谢谢大

**自然普通話（無標準稿）**

对我做了介绍啊那么我想说的是呢大家如果对我的研究感兴趣呢

### Streaming Paraformer INT8（原生預設端點，探索組）／stream

**英文合成語音**

hello everyone today we will discuss the project schedule the meeting starts said nine tomorrow mor

**臺灣普通話合成語音**

大家好今天我们讨论专案进度明天上午九点开会请准备测试报告谢谢大家

**中英混用合成語音**

今天的会议讨论 project skedudule 请在 tomorrow morning 准备好 test report 谢谢大

## 本次觀察與採用建議

- SenseVoice 的整段 CPU 辨識明顯比 Whisper Base 快；英文、中文合成稿均正確，中英混用有字元錯誤。因此有速度優勢，但這些樣本不能證明它在所有情境更準。
- 原生串流 Paraformer 的首字幕較早；0.64 秒停頓／8 秒最長分段組有英文及中英混用錯誤。改用原生預設端點後，本次中文樣本不再漏字，但英文仍有 2/16 個詞錯誤，中英混用仍有 5/56 個字元錯誤；不能將所有錯誤歸因於切段。
- SenseVoice 改成 1 秒暫定更新後，首字幕約 1 秒，三段標準稿的完成字幕錯誤率與 2 秒更新組相同。這組設定已用於 0.2.0，桌面整合驗證另見 VALIDATION.md。
- Paraformer 原生端點組的中英混用，兩次句末完成延遲分別約 1.77 與 5.47 秒。第二次最後一則翻譯呼叫耗時約 3.73 秒，與第一輪的約 0.04 秒不同。這筆尖峰完整保留；目前無足夠證據判定是翻譯推論或系統排程所致，不能直接歸因於 Paraformer 辨識模型。只測兩次的中位數不代表穩定延遲。
- 現有 Whisper 路徑在 9.52 秒中文合成音檔的 8.192 秒切段後，末尾短片段出現大量「請問一下」重複；整段辨識同一音檔沒有這個錯誤。這是實際觀察到的產品分段與解碼風險，原始事件保留在 JSON，未以清理規則刪除。
- 建議先以 SenseVoice 作為下一版平衡模式候選，調整暫定更新間隔並補上短尾段與重複輸出處理；Paraformer 可作為優先低延遲的候選。也應避免讓翻譯阻塞串流辨識，並重用相同原文的已完成譯文。兩者均需再通過真實中英會議測試。

## 限制與採用條件

- 本機是 Ryzen 桌上型 CPU，不能將時間直接套用到一般筆電；合成音檔也不代表真實會議的口音、噪音或多人重疊發言。
- 重複執行同一音檔只衡量時間穩定性，不是增加獨立的準確度樣本。沒有統計顯著性或廣泛準確度排名。
- 整段與串流的差異可能來自切段長度、端點與解碼策略；若短片段產生重複／漏字，必須同時檢查分段策略，不能全部歸因於模型。
- 翻譯品質沒有人工評分；辨識較快不代表英文翻繁中必然較準。
- 要更換正式版本前，仍需用真實中英會議語音、專有名詞及較弱 CPU，完成桌面收音／管道／字幕整合測試。

## 模型來源與重現

- SenseVoice INT8：https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html
- 串流 Paraformer：https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-paraformer/paraformer-models.html
- 每個候選的 Hugging Face revision 與模型 SHA-256 見 `build/bench-models/*/provenance.json`。
- 原始時間戳、每次逐字稿及字幕事件見 `build/benchmark/*-batch.json` 與 `*-stream.json`。
- 環境：{"cpu": "AMD Ryzen 5 7600X3D 6-Core Processor", "logical_cpus": 12, "threads": 4, "platform": "Windows-10-10.0.26300-SP0", "python": "3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]", "packages": {"sherpa-onnx": "2.0.0", "sherpa-onnx-core": "2.0.0", "faster-whisper": "1.2.1", "ctranslate2": "4.8.3", "numpy": "2.4.6"}, "inference_network": "blocked by socket guard", "recording": "none; file fixtures only"}
