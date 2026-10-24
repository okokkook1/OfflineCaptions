# 離線即時繁中字幕 · Windows 11 x64

選擇一個正在發聲的軟體，將其中文普通話或英文語音轉成浮動繁中字幕。所有辨識及翻譯在本機 CPU 運行；不需要 API 金鑰。

## 開始使用

1. 從 [Releases](https://github.com/okokkook1/OfflineCaptions/releases/latest) 下載 `OfflineCaptions-Setup.exe`，按「安裝並開啟」。或將自行建置的 `OfflineCaptions-Windows-x64.zip` 完整解壓後開啟 `OfflineCaptions.exe`。
2. 先讓 Zoom、Teams、瀏覽器會議或播放器發出聲音，再按「重新整理」。
3. 選擇應用程式與來源語言，按「開始字幕」。辨識引擎為 SenseVoice Small INT8。
4. 按「暫停／繼續」控制收音；「結束」會完成剩餘片段。文字歷史可手動匯出 TXT 或 SRT。

0.2.1 完整發佈包內附 .NET、Python、SenseVoice Small INT8 語音模型與 OPUS-MT 英翻中模型，解壓完成後即可斷網使用。暫定字幕每秒更新一次。可在模型管理中重新下載，或在有網路的電腦匯出模型 ZIP，再於離線電腦匯入。模型 ZIP 內有 SHA-256 清單，匯入會驗證檔案完整性；這不是發布者簽章。

0.2.1 修正放在中文及空白資料夾時，SentencePiece 載入翻譯詞彙模型出現 `Illegal byte sequence` 的問題。中文路徑可正常使用，不需要改成英文資料夾。

從 0.1.0 更新時，請先結束並關閉舊程式，再執行新版安裝程式。新版模型包使用 format 2／sensevoice 標記，舊版 Whisper 模型包無法匯入，也不會自動改用 Whisper。

安裝位置：`%LOCALAPPDATA%\Programs\OfflineCaptions`，開始功能表有「離線即時字幕」捷徑。不需系統管理員權限。移除時先關閉程式，再刪除這個資料夾及開始功能表捷徑即可；更新時可能保留帶 `.previous-日期` 的舊版本資料夾供還原。

## 字幕操作

- 拖曳字幕移動；控制面板可調字體、背景濃度、寬度及顯示螢幕。
- `Ctrl+Alt+S` 切換滑鼠穿透；`Ctrl+Alt+H` 顯示／隱藏字幕。快捷鍵若被占用，介面會提示，並停用穿透按鈕，避免無法操作。
- 暫定字幕以較淡文字顯示，預設每秒更新；辨識完成後更新同一段。歷史與匯出只包含完成字幕。
- 「10 秒效能測試」會使用目前選定來源，請讓來源持續播放語音。測試會開始新的一次紀錄，結束後顯示處理速度比；低於 1 代表處理速度快於音訊長度。
- 新一次成功開始後會清空上一次紀錄，請先匯出需要保留的內容。

## 收音範圍與限制

- 指定程序模式使用 Windows Application Loopback，包含該程序的子程序，排除麥克風。
- 選 Chrome／Edge 可能收到同一瀏覽器其他分頁或視窗的聲音。這一版不隔離單一分頁。
- 多程序應用程式可能將音訊交給其他程序；若沒有聲音，重新整理後選正確程序，或**手動**切換至「整個播放裝置」。整個裝置模式會收到該裝置所有軟體的聲音。
- 音源關閉、耳機拔除、裝置失效或休眠時會停止並提示。恢復後重新選擇來源開始；不暗中擴大收音範圍。
- 以中文普通話及英文為範圍。混語、專有名詞、口音、多人同時說話及音樂會影響辨識與翻譯品質。短大寫縮寫保留原樣。
- 浮動字幕支援一般桌面及無邊框全螢幕；獨佔全螢幕不保證覆蓋。字幕若超過兩行會截斷，完整完成內容仍會出現在歷史。
- 字幕延遲取決於語音停頓、CPU 負載與翻譯耗時；每秒更新不等於保證一秒內完成翻譯。工作佇列有上限，過期片段會略過並提示，避免字幕持續落後。
- 不辨識說話者姓名、不配音、不傳送字幕給其他與會者。

## 隱私與資料

- 不錄音，不自動保存字幕或會議文字；音訊緩衝與歷史只存在記憶體。
- 只有手動匯出才會寫入文字檔。關閉程式後，未匯出內容不保留。
- 推論程序強制使用本機模型及離線模式，沒有雲端備援、網路服務或遙測。
- 模型管理中的「下載模型」是明確的連網操作，不會上傳會議資料；執行字幕期間不允許模型下載或更換。

## 原始碼與建置

需求：Windows 11 x64、Visual Studio 2022 C++ Build Tools（v143、Windows 11 SDK）、.NET 8 SDK、Python 3.11 x64。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
# 模型轉換僅在開發環境執行，發佈包不需要 PyTorch。
.\.venv\Scripts\python.exe -m pip install transformers==4.57.1 torch==2.6.0
.\.venv\Scripts\python.exe backend\models.py download --root models
.\scripts\build.ps1 -SelfContained
.\scripts\prepare-runtime.ps1 -HostPython .\.venv\Scripts\python.exe
.\scripts\package.ps1 -SkipBuild
```

`prepare-runtime.ps1` 使用 Python 3.11.9 官方嵌入式執行環境，請以 Python 3.11 x64 作為 HostPython。完整套件已附英翻中模型；重新下載 SenseVoice 不需 PyTorch。若自行建置不附模型的套件，可加 `-IncludeConverter` 準備 OPUS-MT 轉換工具，代價是套件體積增加。

辨識模型使用 sherpa-onnx 2.0.0 的 SenseVoice Small INT8 ONNX。Silero VAD 沿用 faster-whisper 隨附的本機 ONNX 資產；執行字幕時不載入 Whisper 辨識模型。模型位置為 `models/sensevoice-small-int8/model.int8.onnx` 與 `tokens.txt`，語言選項會傳入 SenseVoice 的自動／英文／中文設定。

開發時可設定 `OFFLINE_CAPTIONS_PYTHON` 為虛擬環境 `python.exe` 完整路徑、`OFFLINE_CAPTIONS_MODELS` 為模型資料夾完整路徑。發佈包優先使用旁邊的 `runtime` 與 `models`，沒有內附模型時才使用 `%LOCALAPPDATA%\OfflineCaptions\models`。

桌面／原生收音使用 PCM16 單聲道 16 kHz；桌面與 Python 使用僅限目前 Windows 使用者的隨機名稱雙向具名管道，傳遞有時間戳的音訊與 JSON 字幕事件，不使用 TCP。事件包含片段 ID、起訖時間、原文、來源語言、繁中內容及完成狀態。

## 驗證

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests\native_smoke.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\make-test-audio.ps1
.\.venv\Scripts\python.exe tests\model_smoke.py
# 視窗建構、來源列舉、穿透切換與匯出測試；不擷取使用者音訊。
dist\OfflineCaptions\OfflineCaptions.exe --self-test
```

測試證據與尚未驗證項目見 `VALIDATION.md`。自動測試不能取代 Zoom／Teams／瀏覽器真實會議、不同音訊裝置與一小時穩定性驗收。

## 授權

本專案原始碼採用 [MIT License](LICENSE)。語音模型、推論函式庫與其他第三方元件仍依各自授權使用，詳見 `THIRD-PARTY-NOTICES.md` 與 `licenses/`；SenseVoice Small INT8 模型依 FunASR Model License，模型檔不包含在原始碼儲存庫中。發佈包內附的模型與執行環境同樣受這些第三方條款約束。
