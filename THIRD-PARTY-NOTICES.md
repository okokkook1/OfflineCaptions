# 第三方元件

本專案自行實作 Windows 收音介面，API 使用方式參考 Microsoft ApplicationLoopback 範例：
https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/ApplicationLoopback

發佈包使用下列元件，授權仍屬各自作者；Python 套件完整授權與版本資訊保留在 runtime/Lib/site-packages 的 dist-info 目錄。

| 元件 | 授權 / 來源 |
|---|---|
| .NET / WPF | MIT；Microsoft，https://github.com/dotnet/wpf |
| Python 3.11 | PSF License；https://www.python.org/ |
| Microsoft Visual C++ Runtime | Microsoft 可轉散佈執行階段（VC143 CRT）；https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files |
| sherpa-onnx / sherpa-onnx-core | Apache-2.0；https://github.com/k2-fsa/sherpa-onnx |
| SenseVoice Small INT8 語音模型 | 模型授權依上游 FunASR Model License；完整文字見 licenses/sensevoice-MODEL_LICENSE.txt，模型來源及授權指引附在 models/sensevoice-small-int8/；https://github.com/modelscope/FunASR#license |
| faster-whisper（僅用於 Silero VAD） | MIT；https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | MIT；https://github.com/OpenNMT/CTranslate2 |
| OPUS-MT en-zh | Apache-2.0（模型卡）；https://huggingface.co/Helsinki-NLP/opus-mt-en-zh |
| SentencePiece | Apache-2.0；https://github.com/google/sentencepiece |
| OpenCC Python reimplementation | Apache-2.0；https://github.com/yichen0831/opencc-python |
| Silero VAD | MIT；https://github.com/snakers4/silero-vad |
| NumPy | BSD-3-Clause；https://numpy.org/ |
| ONNX Runtime | MIT；https://github.com/microsoft/onnxruntime |
| PyAV / FFmpeg | PyAV BSD；FFmpeg 授權依 wheel 內的元件而定，請參閱套件附帶 LICENSE。https://github.com/PyAV-Org/PyAV |
| Hugging Face Hub / Tokenizers | Apache-2.0；https://github.com/huggingface |

模型包保留模型來源說明；未經重新確認授權，不應移除原始套件授權或將其宣稱為本專案所有。
