"""Download only INT8 candidate weights, explicitly and separately from live inference."""
import argparse
import hashlib
import json
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download

MODELS = {
    "sensevoice": ("csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
                   ["model.int8.onnx", "tokens.txt", "README.md", "LICENSE", "test_wavs/en.wav", "test_wavs/zh.wav"]),
    "paraformer": ("csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en",
                   ["encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt", "README.md", "test_wavs/*"]),
}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("model", choices=MODELS)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1]/"build/bench-models")
    args = p.parse_args()
    repo, patterns = MODELS[args.model]
    revision = HfApi().model_info(repo).sha
    folder = args.root/args.model
    snapshot_download(repo, revision=revision, local_dir=folder, allow_patterns=patterns)
    files = {}
    for file in folder.rglob("*"):
        if file.is_file() and ".cache" not in file.parts and file.name != "provenance.json":
            h=hashlib.sha256()
            with file.open("rb") as f:
                for block in iter(lambda:f.read(1024*1024), b""):h.update(block)
            files[file.relative_to(folder).as_posix()]={"bytes":file.stat().st_size,"sha256":h.hexdigest()}
    (folder/"provenance.json").write_text(json.dumps({"repo":repo,"revision":revision,"files":files},indent=2),encoding="utf-8")
    print(json.dumps({"model":args.model,"revision":revision,"folder":str(folder)}),flush=True)

if __name__=="__main__":main()
