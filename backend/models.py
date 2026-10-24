"""Explicit installation only. The live worker never invokes this module's CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

SPEECH_FOLDER = "sensevoice-small-int8"
SPEECH_REPO = "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
SPEECH_REVISION = "2365baeacb507f821a0c8120fcee3d484dba7a07"
MT_REPO = "Helsinki-NLP/opus-mt-en-zh"

def required(root):
    root = Path(root)
    return [root / SPEECH_FOLDER / x for x in ("model.int8.onnx", "tokens.txt")] + [
        root / "opus-en-zh" / x for x in ("model.bin", "config.json", "shared_vocabulary.json", "source.spm", "target.spm")]

def validate(root):
    missing = [str(p) for p in required(root) if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise FileNotFoundError("缺少 SenseVoice／英翻中離線模型，請先下載或匯入新版模型包：" + ", ".join(missing))

def download(root):
    from huggingface_hub import snapshot_download
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # A complete tree is staged before exposing it to the worker.
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        stage = Path(tmp)
        speech = snapshot_download(SPEECH_REPO, revision=SPEECH_REVISION, cache_dir=root / ".downloads",
                                   allow_patterns=["model.int8.onnx", "tokens.txt", "README.md", "LICENSE"])
        shutil.copytree(speech, stage / SPEECH_FOLDER)
        license_text=Path(__file__).resolve().parents[1]/"licenses"/"sensevoice-MODEL_LICENSE.txt"
        if license_text.is_file():shutil.copy2(license_text,stage / SPEECH_FOLDER / "MODEL_LICENSE")
        if not (root / "opus-en-zh" / "model.bin").exists():
            from ctranslate2.converters import TransformersConverter
            from transformers import MarianTokenizer
            source = Path(snapshot_download(MT_REPO, cache_dir=root / ".downloads",
                          allow_patterns=["*.json", "*.spm", "pytorch_model.bin", "*.safetensors", "README.md"]))
            target = stage / "opus-en-zh"
            TransformersConverter(str(source)).convert(str(target), quantization="int8")
            MarianTokenizer.from_pretrained(str(source), local_files_only=True).save_pretrained(str(target))
            for name in ("README.md",):
                if (source / name).exists(): shutil.copy2(source / name, target / name)
            promote(target, root / "opus-en-zh")
        promote(stage / SPEECH_FOLDER, root / SPEECH_FOLDER)
    validate(root)
    print("模型已準備完成。之後使用字幕不需連線。", flush=True)

def promote(source, destination):
    # Never replace a working installed model on a partial download.
    backup = destination.with_name(destination.name + ".previous")
    if backup.exists(): shutil.rmtree(backup)
    if destination.exists(): destination.rename(backup)
    try:
        shutil.move(str(source), str(destination))
    except Exception:
        if backup.exists(): backup.rename(destination)
        raise
    if backup.exists(): shutil.rmtree(backup)

def import_pack(archive, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        stage = Path(tmp)
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist()) > 8 * 1024**3:
                raise ValueError("模型包解壓後超過 8 GB")
            for item in z.infolist():
                path = (stage / item.filename).resolve()
                if not path.is_relative_to(stage.resolve()) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("模型包含有不安全路徑")
            z.extractall(stage)
        manifest = stage / "manifest.json"
        if not manifest.exists(): raise ValueError("模型包缺少 manifest.json 校驗清單")
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        if metadata.get("format") != 2 or metadata.get("engine") != "sensevoice":
            raise ValueError("此模型包不適用於 SenseVoice 版本，請匯入新版 SenseVoice Small INT8 模型包。")
        validate(stage)
        files = metadata["files"]
        actual = {p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file() and p != manifest}
        if set(files) != actual: raise ValueError("模型包檔案與校驗清單不一致")
        for name, digest in files.items():
            if sha(stage / name) != digest: raise ValueError("模型校驗失敗：" + name)
        for name in (SPEECH_FOLDER, "opus-en-zh"):
            promote(stage / name, root / name)
    print("離線模型包已匯入", flush=True)

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()

def export_pack(root, output):
    validate(root)
    root = Path(root)
    files = {}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as z:
        for folder in (SPEECH_FOLDER, "opus-en-zh"):
            for p in (root / folder).rglob("*"):
                if p.is_file() and ".cache" not in p.parts:
                    name = p.relative_to(root).as_posix()
                    files[name] = sha(p)
                    z.write(p, name)
        z.writestr("manifest.json", json.dumps({"format": 2, "engine": "sensevoice", "files": files}, indent=2))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["download", "import", "export", "check"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--file")
    args = parser.parse_args()
    if args.action == "download": download(args.root)
    elif args.action == "check": validate(args.root); print("SenseVoice Small INT8 與英翻中模型檔案完整")
    elif not args.file: parser.error("import/export 需要 --file")
    elif args.action == "import": import_pack(args.file, args.root)
    else: export_pack(args.root, args.file)

if __name__ == "__main__": main()
