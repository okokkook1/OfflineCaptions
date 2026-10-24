# 驗證紀錄

日期：2026-10-25。現行版本：0.2.1（SenseVoice Small INT8）。以下為本機測試結果，並非所有電腦的效能保證。

## 0.2.1 中文資料夾修正

- 已將 0.2.0 完整發佈 ZIP 解壓至 `build/中文 路徑測試/即時字幕/`，重現 SentencePiece 載入 `source.spm` 時的 `Illegal byte sequence Error #42`。SenseVoice 與翻譯權重已能載入，失敗點是翻譯詞彙模型的原生檔案路徑處理。
- 改由 Python `Path.read_bytes()` 讀入 source／target 兩個詞彙模型，再以 SentencePiece `model_proto` 初始化，避開 Windows 原生 filename loader 的編碼問題；模型內容與辨識引擎不變。
- 修正後的 0.2.1 程式、Python 執行環境及全部模型位於同一個中文＋空白資料夾；測試沒有設定模型或 Python 路徑覆寫，確實使用該位置的完整程式。
- 中文路徑的英文／普通話桌面具名管道測試都通過；輸入音檔及輸出 SRT／JSON 的路徑也含中文與空白。
- 該位置的 WPF 視窗、原生 DLL 列舉與匯出自測退出碼 0；實際播放合成英文 → 程序 loopback → SenseVoice → 翻譯 → 字幕／SRT 流程也通過，得到兩段完成字幕，退出碼 0。
- 新增實際 SentencePiece 讀取中文路徑的回歸測試，以及中文 ZIP 檔名／模型匯入匯出測試；全部 26 項自動測試通過。

重現與修復後的桌面測試資料保存在 `build/中文 路徑測試/`。這些測試素材不包含使用者會議錄音，也不打包發佈。

## 0.2.0 切換驗證

- 語音辨識已改為 sherpa-onnx／SenseVoice Small INT8，暫定字幕每秒更新。英翻中仍採 OPUS-MT，繁中仍採 OpenCC；Silero VAD 沿用原流程。
- 發佈版 WPF 自足程式編譯成功；畫面已確認顯示 SenseVoice Small INT8，視窗、穿透與 SRT 自測正常關閉，退出碼 0。
- 內附 Python 能載入 sherpa-onnx 2.0.0；在禁止 Python socket 連線的測試中，中英實際模型推論都成功。英文約 0.22 秒、普通話約 0.13 秒，僅為這次音檔的單次量測。
- 桌面到 Python 的中英文具名管道測試均通過，實際 ready 事件為 `engine=sensevoice`、`partial_interval_s=1`。C# 會拒絕不相符的舊背景程序。
- 手動指定中文模型語言已通過；自動辨識中英通過；完整收音測試使用手動英文。
- 實際「本程式播放合成英文 → 指定程序 loopback → SenseVoice → 英翻中 → 畫面／歷史／SRT」通過，得到一段完成字幕，退出碼 0。這是流程驗證，不是翻譯品質人工驗收。
- 模型管理改為 SenseVoice 格式 2，舊 Whisper 模型包會清楚拒絕。核心、介面合約、模型包與封裝篩選測試共 24 項通過。
- 新的封裝腳本只納入 SenseVoice 與 OPUS-MT 模型資料夾，排除增量建置殘留的 Whisper 權重；舊權重可留在開發工作區供歷史比較。

0.2.0 桌面測試證據在 `build/qa-sensevoice/`，模型比較原始資料在 `build/benchmark/`。本機檔案回放測試中，SenseVoice 一秒更新組首字幕約 1 秒；不包含 Windows 收音及畫面繪製，也不是一般筆電或真實會議的保證。完整比較見 `benchmarks/RESULTS.md`。

## 0.1.0 歷史測試紀錄（Whisper Base）

下表保留先前版本的測試結果，不能當作新版 SenseVoice 的延遲或品質數據。

### 已通過

| 項目 | 結果 |
|---|---|
| 原生 C++ 收音 DLL | MSVC v143 / Windows SDK 編譯成功 |
| WPF 桌面程式 | .NET 8，Windows x64 自足版編譯成功，0 警告、0 錯誤 |
| 核心自動測試 | 14 項全過：靜音、停頓、長音訊分段、暫定轉完成、過載佇列、時間戳、混語翻譯路徑、模型 ZIP 往返與篡改／路徑穿越防護 |
| WPF 視窗測試 | 控制面板、來源列舉、字幕視窗、滑鼠穿透切換、SRT 匯出；正常關閉，退出碼 0 |
| 原生程序收音 | 真實擷取本測試程序的 440 Hz 合成音，24,000 個樣本；不是模擬收音 |
| 兩程序隔離 | 同時播放 440 Hz 與 880 Hz，指定 440 Hz 程序；擷取中的頻譜幅度比約 2901:1，另一程序聲音未顯著混入 |
| 真實英文模型推論 | 約 7.9 秒合成英文語音 → 原文與繁中譯文；單次約 0.65 秒，RTF 0.083 |
| 真實中文模型推論 | 約 5.6 秒公開普通話測試語音 → 繁中；單次約 0.62 秒，RTF 0.111 |
| 離線推論檢查 | 模型推論測試中封鎖 Python socket 連線；中英文推論仍成功 |
| 桌面到 Python 通訊 | 使用發佈包內附 Python、具名管道、即時送入測試音訊；3 次暫定更新後輸出同 ID 完成字幕，無重複完成字幕，SRT 正確產生 |
| 完整收音到字幕 | WPF 播放合成英文 → 指定本程序 loopback → 具名管道 → 離線辨識與翻譯 → 畫面與歷史 → SRT；得到 2 段完成繁中字幕，退出碼 0 |

RTF = 模型處理秒數 / 音訊秒數；小於 1 表示這次模型處理快於音訊長度。它不等於使用者感受到的總延遲，也未代表多人會議或長時間負載下的結果。

測試證據保存在原始碼工作區的 `build/qa/`：視窗 PNG、`model-smoke.json`、`pipeline-test.json`、`pipeline.srt`、`capture-test.json`、`capture-test.srt`、`isolation-test.json`。這些測試資料不包含使用者會議音訊，也不放入安裝包。

英文測試音由本機 Windows 語音合成產生。中文測試音僅供驗證，來源：https://huggingface.co/csukuangfj/sherpa-onnx-zh-wenet-aishell2/resolve/main/test_wavs/0.wav ，不隨程式發佈。

此工作區的受限執行權限會阻止 Python 開啟 Windows 具名管道；通訊及完整桌面測試是在正常 Windows 使用者執行環境中通過，仍保留僅限目前使用者的管道存取控制。

## 尚待真實環境驗收

- Zoom、Teams、Chrome／Edge 真正會議的逐一相容性，尤其各自版本的程序樹及瀏覽器多分頁。
- 中文／英文來回切換、混語、專有名詞、口音、背景音樂與多人重疊發言的品質評估。
- 耳機切換、熱拔除、休眠恢復、不同 DPI 多螢幕及快捷鍵衝突的完整實機矩陣。
- 一小時持續會議的記憶體、CPU、字幕遺漏率及延遲分布。
- 在沒有開發工具的另一台乾淨 Windows 11 電腦，執行安裝、更新與移除。

上述情境未經實際測試，不宣稱已通過。程式已提供對應錯誤處理與手動驗收方式。
