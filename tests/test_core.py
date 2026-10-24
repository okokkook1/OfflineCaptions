import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import unittest
import tempfile
import json
import zipfile
from unittest.mock import patch
import numpy as np
from core import Segmenter, Job, JobBuffer, RATE, translate_text, srt_time
from models import export_pack, import_pack, validate, required

class SegmentationTests(unittest.TestCase):
    def block(self): return np.ones(4096, np.float32) * .1
    def test_partial_replaced_by_final_with_same_id(self):
        jobs=[]; s=Segmenter(jobs.append)
        for i in range(12): s.push(self.block(), i*.256, i<9)
        drafts=[j for j in jobs if not j.final]; finals=[j for j in jobs if j.final]
        self.assertTrue(drafts);self.assertEqual(len(finals),1)
        self.assertEqual(drafts[0].id,finals[0].id)
        self.assertAlmostEqual(finals[0].end,9*.256)
    def test_silence_never_creates_captions(self):
        jobs=[];s=Segmenter(jobs.append)
        for i in range(100):s.push(np.zeros(4096,np.float32),i*.256,False)
        s.finish();self.assertEqual(jobs,[])
    def test_hard_limit_bounds_memory_and_ids(self):
        jobs=[];s=Segmenter(jobs.append,max_seconds=2)
        for i in range(40):s.push(self.block(),i*.256,True)
        s.finish();finals=[x for x in jobs if x.final]
        self.assertEqual(len(finals),5)
        self.assertTrue(all(len(x.audio)<=RATE*2.1 for x in finals))
        self.assertEqual(len(set(x.id for x in finals)),5)
        self.assertTrue(all(a.end<=b.start for a,b in zip(finals,finals[1:])))
    def test_pause_or_device_gap_preserves_clock_and_separates_audio(self):
        jobs=[];s=Segmenter(jobs.append)
        s.push(self.block(),1,True);s.push(self.block(),8,True);s.finish()
        self.assertEqual([x.start for x in jobs],[1,8])
    def test_final_supersedes_drafts(self):
        q=JobBuffer();a=self.block()
        q.add(Job(1,0,2,a,False));q.add(Job(1,0,3,a,False));q.add(Job(1,0,4,a,True))
        self.assertEqual(len(q.items),1);self.assertTrue(q.pop().final)
    def test_overload_drops_oldest_final_and_never_exceeds_bound(self):
        q=JobBuffer(2);a=self.block()
        q.add(Job(1,0,2,a,True));q.add(Job(2,2,4,a,True))
        self.assertEqual(q.add(Job(3,4,6,a,False)),[])
        self.assertEqual(len(q.items),2)
        self.assertEqual(q.add(Job(3,4,6,a,True)),[1])
        self.assertEqual([x.id for x in q.items],[2,3])

class TranslationTests(unittest.TestCase):
    def test_english_goes_to_translation(self):
        self.assertEqual(translate_text("hello", "en", lambda x:"你好", lambda x:x),"你好")
    def test_chinese_skips_translation(self):
        self.assertEqual(translate_text("谢谢", "zh", lambda _:self.fail("翻譯不應被呼叫"), lambda _:"謝謝"),"謝謝")
    def test_mixed_language_keeps_chinese_and_translates_english(self):
        text=translate_text("今天討論 next steps，使用 API", "zh", lambda _:"下一步",lambda x:x)
        self.assertIn("今天討論",text);self.assertIn("下一步",text);self.assertIn("API",text)
    def test_empty_does_not_hallucinate(self):self.assertEqual(translate_text(" ","zh",lambda _:"bad",lambda x:x),"")
    def test_time_rounding_and_large_hours(self):
        self.assertEqual(srt_time(59.9996),"00:01:00,000")
        self.assertEqual(srt_time(-1),"00:00:00,000")
        self.assertEqual(srt_time(360000),"100:00:00,000")

class ModelPackTests(unittest.TestCase):
    def make_models(self,root):
        for p in required(root):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b"model fixture")
    def test_roundtrip_and_checksums(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.make_models(root/"a");archive=root/"models.zip"
            export_pack(root/"a",archive);import_pack(archive,root/"b");validate(root/"b")
    def test_tampering_is_rejected_without_touching_existing_models(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.make_models(root/"a");self.make_models(root/"b");archive=root/"models.zip"
            export_pack(root/"a",archive)
            with zipfile.ZipFile(archive,"a") as z:z.writestr("extra.txt","unlisted")
            with self.assertRaises(ValueError):import_pack(archive,root/"b")
            self.assertEqual((root/"b/sensevoice-small-int8/model.int8.onnx").read_bytes(),b"model fixture")
    def test_zip_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            archive=Path(t)/"bad.zip"
            with zipfile.ZipFile(archive,"w") as z:z.writestr("../escape","bad")
            with self.assertRaises(ValueError):import_pack(archive,Path(t)/"models")
            self.assertFalse((Path(t)/"escape").exists())
    def test_legacy_whisper_pack_is_rejected_with_clear_message(self):
        with tempfile.TemporaryDirectory() as t:
            archive=Path(t)/"old.zip"
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr("manifest.json",json.dumps({"format":1,"files":{}}))
            with self.assertRaisesRegex(ValueError,"SenseVoice"):
                import_pack(archive,Path(t)/"models")

if __name__=="__main__":unittest.main()
