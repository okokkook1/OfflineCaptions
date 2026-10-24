"""Regression coverage for Windows non-ASCII model and archive paths."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import sentencepiece as spm

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from models import required, export_pack, import_pack, validate
from worker import Engine

class UnicodePathTests(unittest.TestCase):
    def test_engine_loads_both_sentencepiece_models_from_chinese_space_path(self):
        serialized=io.BytesIO()
        spm.SentencePieceTrainer.train(sentence_iterator=iter(["hello world", "中文路徑測試", "translation sample"]*10),
            model_writer=serialized,vocab_size=32,hard_vocab_limit=False,num_threads=1,minloglevel=2)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/"中文 資料夾"/"字幕 模型"
            for file in required(root):
                file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b"fixture")
            for name in ("source.spm","target.spm"):
                (root/"opus-en-zh"/name).write_bytes(serialized.getvalue())
            # The regression concerns real SentencePiece loading; ASR and MT
            # constructors are mocked so unit tests do not need large weights.
            with patch("sherpa_onnx.OfflineRecognizer.from_sense_voice"),patch("ctranslate2.Translator"),patch("faster_whisper.vad.get_vad_model"):
                engine=Engine(root,"auto")
            for processor in (engine.source,engine.target):
                self.assertEqual(processor.decode(processor.encode("hello world")),"hello world")

    def test_model_pack_import_export_supports_chinese_folders_and_filename(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)/"中文 模型包測試";source=base/"來源 模型";target=base/"匯入 模型"
            for file in required(source):
                file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b"fixture")
            archive=base/"離線 模型包.zip"
            export_pack(source,archive);import_pack(archive,target);validate(target)
            self.assertEqual((target/"opus-en-zh/source.spm").read_bytes(),b"fixture")

if __name__=="__main__":unittest.main()
