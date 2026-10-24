"""Exercise the result contract without downloading models in unit tests."""
import io
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from core import Job
from worker import Engine, Worker

class FakeAsr:
    def __init__(self,result):self.result=result
    def create_stream(self):
        return SimpleNamespace(result=self.result,accept_waveform=lambda rate,audio:None)
    def decode_stream(self,stream):pass

class SenseVoiceContractTests(unittest.TestCase):
    def engine(self,text,lang):
        engine=object.__new__(Engine)
        engine.asr=FakeAsr(SimpleNamespace(text=text,lang=lang))
        engine.translate=lambda text:"你好"
        engine.convert=lambda text:text
        return engine
    def test_rich_tags_are_removed_and_language_metadata_is_decoded(self):
        engine=self.engine("<|en|><|NEUTRAL|><|Speech|>Hello<|withitn|>","<|en|>")
        original,text,lang=engine.recognize(Job(1,0,1,np.zeros(16000,np.float32),True))
        self.assertEqual((original,text,lang),("Hello","你好","en"))
    def test_chinese_skips_machine_translation(self):
        engine=self.engine("你好","<|zh|>")
        engine.translate=lambda _:self.fail("Chinese should not use English MT")
        self.assertEqual(engine.recognize(Job(1,0,1,np.zeros(16000,np.float32),True)),("你好","你好","zh"))
    def test_other_languages_do_not_become_english_translation(self):
        engine=self.engine("こんにちは","<|ja|>")
        self.assertEqual(engine.recognize(Job(1,0,1,np.zeros(16000,np.float32),True)),("","","ja"))
    def test_live_worker_uses_one_second_partial_interval(self):
        worker=Worker(io.BytesIO(),SimpleNamespace())
        self.assertEqual(worker.segmenter.partial_seconds,1.0)

if __name__=="__main__":unittest.main()
