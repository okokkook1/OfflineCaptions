import argparse
import base64
import json
import io
import os
import re
from pathlib import Path
import sys
import threading
import time
from collections import deque

# Set before any model imports: inference must never download models or send telemetry.
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
import numpy as np
from core import RATE, Segmenter, JobBuffer, translate_text
from models import validate

class Engine:
    def __init__(self, root, language="auto"):
        validate(root)
        import sherpa_onnx
        from faster_whisper.vad import get_vad_model
        from opencc import OpenCC
        import ctranslate2
        import sentencepiece as spm
        threads = max(1, min(4, (os.cpu_count() or 4) // 2))
        self.asr = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(root / "sensevoice-small-int8" / "model.int8.onnx"),
            tokens=str(root / "sensevoice-small-int8" / "tokens.txt"),
            num_threads=threads, provider="cpu", language="" if language=="auto" else language,
            use_itn=True)
        self.mt = ctranslate2.Translator(str(root / "opus-en-zh"), device="cpu", compute_type="int8", intra_threads=threads)
        # Python opens Unicode paths correctly on Windows; SentencePiece's native
        # filename loader can reject them under the system code page (errno 42).
        self.source = spm.SentencePieceProcessor(model_proto=(root / "opus-en-zh" / "source.spm").read_bytes())
        self.target = spm.SentencePieceProcessor(model_proto=(root / "opus-en-zh" / "target.spm").read_bytes())
        self.convert = OpenCC("s2twp").convert
        self.vad = get_vad_model()
        self.language = language

    def translate(self, text):
        tokens = self.source.encode(text, out_type=str) + ["</s>"]
        result = self.mt.translate_batch([tokens], beam_size=2, max_decoding_length=256)[0]
        return self.target.decode([t for t in result.hypotheses[0] if not t.startswith("<")])

    def recognize(self, job):
        stream=self.asr.create_stream()
        stream.accept_waveform(RATE, job.audio)
        self.asr.decode_stream(stream)
        result=stream.result
        language=result.lang.removeprefix("<|").removesuffix("|>")
        if language not in ("zh", "en"):
            return "", "", language
        text=re.sub(r"<\|.*?\|>", "", result.text).strip()
        return text, translate_text(text, language, self.translate, self.convert), language

class Worker:
    def __init__(self, pipe, engine):
        self.pipe, self.engine = pipe, engine
        self.reader = io.BufferedReader(pipe, buffer_size=65536)
        self.write_lock = threading.Lock()
        self.condition = threading.Condition()
        self.jobs = JobBuffer()
        self.stopping = False
        self.segmenter = Segmenter(self.enqueue, partial_seconds=1.0)
        self.pending = np.zeros(0, np.float32)
        self.vad_context = np.zeros(0, np.float32)
        self.pending_start = None
        self.latest_audio = 0.0
        self.generation = 0
        self.final_ids = set()
        self.metrics = deque(maxlen=20)

    def send(self, **event):
        payload = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        with self.write_lock:
            self.pipe.write(payload)
            self.pipe.flush()

    def enqueue(self, job):
        with self.condition:
            if job.final: self.final_ids.add(job.id)
            for dropped in self.jobs.add(job):
                self.final_ids.discard(dropped)
                self.send(type="dropped", id=dropped, message="處理速度不足，已略過過期片段；請關閉其他耗能程式。")
            self.condition.notify()

    def ingest(self, msg):
        data = np.frombuffer(base64.b64decode(msg["pcm"], validate=True), dtype="<i2").astype(np.float32) / 32768
        if len(data) > RATE * 2: raise ValueError("音訊封包過大")
        stamp = float(msg["start"])
        expected = None if self.pending_start is None else self.pending_start + len(self.pending) / RATE
        if expected is not None and abs(stamp - expected) > 0.2:
            self.flush_audio()
        if self.pending_start is None: self.pending_start = stamp
        self.pending = np.concatenate([self.pending, data])
        self.latest_audio = stamp + len(data) / RATE
        while len(self.pending) >= 4096:
            block, self.pending = self.pending[:4096], self.pending[4096:]
            self.vad_context = np.concatenate([self.vad_context, block])[-16384:]
            probability = self.engine.vad(self.vad_context)
            speech = float(np.max(probability[-8:])) >= 0.5
            self.segmenter.push(block, self.pending_start, speech)
            self.pending_start += len(block) / RATE

    def flush_audio(self):
        if len(self.pending):
            block = self.pending
            pad = np.pad(block, (0, (-len(block)) % 512))
            speech = float(np.max(self.engine.vad(pad))) >= 0.5
            self.segmenter.push(block, self.pending_start, speech)
        self.pending = np.zeros(0, np.float32)
        self.pending_start = None
        self.vad_context = np.zeros(0, np.float32)
        self.segmenter.finish()

    def inference(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.jobs.items or self.stopping)
                    job = self.jobs.pop()
                    generation = self.generation
                    if job is None:
                        if self.stopping: return
                        continue
                if self.latest_audio - job.end > 12:
                    self.final_ids.discard(job.id)
                    if job.final: self.send(type="dropped", id=job.id, message="處理速度不足，已略過過期字幕。")
                    continue
                start = time.perf_counter()
                original, translated, language = self.engine.recognize(job)
                elapsed = time.perf_counter() - start
                self.metrics.append(elapsed / max(0.1, job.end - job.start))
                with self.condition:
                    if generation != self.generation or (not job.final and job.id in self.final_ids): continue
                    if job.final: self.final_ids.discard(job.id)
                    self.send(type="caption", id=job.id, start=job.start, end=job.end, language=language,
                              original=original, text=translated, final=job.final,
                              latency=round(elapsed + max(0, self.latest_audio - job.end), 2),
                              rtf=round(sum(self.metrics) / len(self.metrics), 2))
        except Exception as exc:
            self.send(type="error", message="辨識程序失敗：" + str(exc))
            self.stopping = True

    def run(self):
        thread = threading.Thread(target=self.inference, daemon=True)
        thread.start()
        self.send(type="ready", engine="sensevoice", model="SenseVoice Small INT8",
                  provider="cpu", partial_interval_s=1.0, message="SenseVoice Small INT8 離線模型就緒")
        while True:
            line = self.reader.readline(512 * 1024)
            if not line: break
            if not line.endswith(b"\n"): raise ValueError("封包超過上限")
            msg = json.loads(line)
            action = msg.get("type")
            if action == "audio": self.ingest(msg)
            elif action in ("pause", "idle"): self.flush_audio()
            elif action == "reset":
                with self.condition:
                    self.generation += 1
                    self.jobs.items.clear()
                    self.final_ids.clear()
                    self.segmenter.reset()
                    self.pending = np.zeros(0, np.float32)
                    self.pending_start = None
                    self.vad_context = np.zeros(0, np.float32)
            elif action == "stop":
                self.flush_audio()
                break
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        thread.join(timeout=30)
        self.send(type="stopped")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipe", required=True)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--language", default="auto", choices=["auto", "en", "zh"])
    args = parser.parse_args()
    if not args.pipe.startswith("OfflineCaptions-"): raise ValueError("無效的管道名稱")
    with open("\\\\.\\pipe\\" + args.pipe, "r+b", buffering=0) as pipe:
        try:
            engine = Engine(args.models, args.language)
            Worker(pipe, engine).run()
        except Exception as exc:
            pipe.write((json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n").encode("utf-8"))
            pipe.flush()
            return 1
    return 0

if __name__ == "__main__": sys.exit(main())
