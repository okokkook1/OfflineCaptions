# SenseVoice / Streaming Paraformer 比較

這個目錄只新增可重現的模型實測，不會改寫目前發佈的桌面程式或安裝包。

使用 Python 3.11 x64、固定 CPU 四執行緒。先依主專案說明準備 Whisper Base 與 OPUS-MT，再於獨立虛擬環境安裝本目錄的 requirements。`build/qa/en.wav` 為既有英文合成測試音；`build/qa/zh.wav` 為既有公開中文樣本，來源見 VALIDATION.md。

```powershell
.\.venv\Scripts\python.exe -m pip install -r benchmarks\requirements.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File benchmarks\make_zh_fixture.ps1
.\.venv\Scripts\python.exe benchmarks\prepare_models.py sensevoice
.\.venv\Scripts\python.exe benchmarks\compare_models.py --models whisper sensevoice --mode batch --repetitions 3
.\.venv\Scripts\python.exe benchmarks\compare_models.py --models whisper sensevoice --mode stream --repetitions 2
.\.venv\Scripts\python.exe benchmarks\prepare_models.py paraformer
.\.venv\Scripts\python.exe benchmarks\compare_models.py --models paraformer --mode batch --repetitions 3
.\.venv\Scripts\python.exe benchmarks\compare_models.py --models paraformer --mode stream --repetitions 2
.\.venv\Scripts\python.exe benchmarks\compare_models.py --models sensevoice --mode stream --partial-seconds 1 --tag 1s --repetitions 2 --fixtures en-synthetic zh-synthetic mixed-synthetic
.\.venv\Scripts\python.exe benchmarks\compare_models.py --models paraformer --mode stream --endpoint-silence 1.2 --max-segment 20 --tag native --repetitions 2 --fixtures en-synthetic zh-synthetic mixed-synthetic
.\.venv\Scripts\python.exe benchmarks\render_report.py
```

`make_zh_fixture.ps1` 直接使用已安裝的 Windows Yating 語音建立有已知標準稿的中文與中英混用音檔，不修改登錄檔、不安裝語音。若沒有該語音，需另提供同名 PCM16／16 kHz 單聲道音檔及 UTF-8 `.txt` 標準稿。不同聲音會影響辨識結果；每次報告均保留 WAV 的 SHA-256。

兩種字幕路徑都是按牆鐘逐步送入檔案音訊，並計算字幕事件送出的時間，尚未接到 Windows 桌面畫面。完整方法、限制、逐字稿與量測結果見 RESULTS.md。
