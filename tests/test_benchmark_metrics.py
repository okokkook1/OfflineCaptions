"""Guard benchmark scoring and latency definitions against misleading results."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"benchmarks"))
from compare_models import accuracy, distance, summary_stream

class BenchmarkMetricTests(unittest.TestCase):
    def test_punctuation_script_and_numeric_format_do_not_create_false_errors(self):
        self.assertEqual(accuracy("明天上午九點開會。","明天上午9点开会！","zh")["cer"],0)
        self.assertEqual(accuracy("at nine tomorrow", "At 9 tomorrow.","en")["wer"],0)
    def test_real_insertions_and_deletions_count(self):
        self.assertEqual(distance("abc","abxc"),1)
        self.assertEqual(accuracy("大家好","大家很好","zh")["character_edits"],1)
    def test_missing_reference_is_not_scored_as_perfect(self):
        self.assertIsNone(accuracy(None,"wrong","zh"))
    def test_latency_is_wall_clock_from_common_speech_bounds(self):
        item=dict(speech_start_s=.2,speech_end_s=5.,reference="你好",language="zh")
        events=[dict(type="caption",text="你",original="你",final=False,emitted_at_s=1.),
                dict(type="caption",text="你好",original="你好",final=True,emitted_at_s=5.8)]
        result=summary_stream(events,item,[],False)
        self.assertAlmostEqual(result["first_caption_after_speech_start_s"],.8)
        self.assertAlmostEqual(result["last_final_after_speech_end_s"],.8)
        self.assertEqual(result["accuracy"]["cer"],0)
        self.assertEqual(result["original"],"你好")

if __name__=="__main__":unittest.main()
