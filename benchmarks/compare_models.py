"""Reproducible CPU-only comparison. Candidate engines do not change the shipped app.

Batch: one warm-up then 3 timed runs. Streaming: wall-clock-paced PCM packets,
the production Worker for offline ASR, and actual incremental decoding for Paraformer.
All engines share the production OPUS-MT and OpenCC translation path.
"""
import argparse
import base64
from collections import deque
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import queue
import re
import socket
import statistics
import sys
import threading
import time
import unicodedata
import wave

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import numpy as np
from core import translate_text
from worker import Worker
from faster_whisper.vad import get_vad_model, get_speech_timestamps, VadOptions
from opencc import OpenCC

def deny_network(*args,**kwargs):
    raise AssertionError("Benchmark inference attempted network access")
socket.socket.connect=deny_network
socket.create_connection=deny_network

def read_wave(path):
    with wave.open(str(path),"rb") as f:
        if (f.getframerate(),f.getnchannels(),f.getsampwidth())!=(16000,1,2):
            raise ValueError(f"Expected mono PCM16 16 kHz: {path}")
        return np.frombuffer(f.readframes(f.getnframes()),dtype="<i2").astype(np.float32)/32768

def corpus():
    items=[
        ("en-synthetic",ROOT/"build/qa/en.wav","en","Hello everyone. Today we will discuss the project schedule. The meeting starts at nine tomorrow morning."),
        ("zh-synthetic",ROOT/"build/benchmark/zh-synthetic.wav","zh",None),
        ("mixed-synthetic",ROOT/"build/benchmark/mixed-synthetic.wav","mixed",None),
        ("zh-natural",ROOT/"build/qa/zh.wav","zh",None),
    ]
    result=[]
    for name,path,language,reference in items:
        if not path.exists():raise FileNotFoundError(path)
        if name.endswith("synthetic") and reference is None:
            reference=path.with_suffix(".txt").read_text(encoding="utf-8-sig")
        audio=read_wave(path)
        spans=get_speech_timestamps(audio,VadOptions(min_speech_duration_ms=80,min_silence_duration_ms=200,speech_pad_ms=0))
        if not spans:raise ValueError(f"No speech in {path}")
        result.append(dict(id=name,path=str(path.relative_to(ROOT)),language=language,reference=reference,
            audio=audio,duration_s=len(audio)/16000,speech_start_s=spans[0]["start"]/16000,
            speech_end_s=spans[-1]["end"]/16000,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return result

CONVERT_SIMPLE=OpenCC("t2s").convert
DIGITS={"zero":"0","one":"1","two":"2","three":"3","four":"4","five":"5","six":"6","seven":"7","eight":"8","nine":"9","ten":"10"}
def normalize(text):
    text=CONVERT_SIMPLE(unicodedata.normalize("NFKC",text).lower())
    text=re.sub(r"\b("+"|".join(DIGITS)+r")\b",lambda m:DIGITS[m.group()],text)
    text=text.replace("九点","9点").replace("九时","9时")
    return "".join(c if not unicodedata.category(c).startswith(("P","S")) else " " for c in text)

def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]

def accuracy(reference,text,language):
    if reference is None:return None
    a=normalize(reference);b=normalize(text)
    ca="".join(a.split());cb="".join(b.split())
    out={"character_edits":distance(ca,cb),"reference_characters":len(ca),"cer":distance(ca,cb)/max(1,len(ca))}
    if language=="en":
        aw=a.split();bw=b.split()
        out.update(word_edits=distance(aw,bw),reference_words=len(aw),wer=distance(aw,bw)/max(1,len(aw)))
    return out

class Translation:
    def __init__(self,threads):
        import ctranslate2
        import sentencepiece as spm
        directory=ROOT/"models/opus-en-zh"
        self.mt=ctranslate2.Translator(str(directory),device="cpu",compute_type="int8",intra_threads=threads)
        self.source=spm.SentencePieceProcessor(model_proto=(directory/"source.spm").read_bytes())
        self.target=spm.SentencePieceProcessor(model_proto=(directory/"target.spm").read_bytes())
        self.convert=OpenCC("s2twp").convert
    def translate(self,text):
        result=self.mt.translate_batch([self.source.encode(text,out_type=str)+["</s>"]],beam_size=2,max_decoding_length=256)[0]
        return self.target.decode([t for t in result.hypotheses[0] if not t.startswith("<")])
    def __call__(self,text,language):
        return translate_text(text,language,self.translate,self.convert)

class Recognizer:
    def __init__(self,name,threads,translation,endpoint_silence=.64,max_segment=8.):
        self.name=name;self.translation=translation;self.vad=get_vad_model();self.timings=[]
        start=time.perf_counter()
        if name=="whisper":
            from faster_whisper import WhisperModel
            self.model=WhisperModel(str(ROOT/"models/whisper-base"),device="cpu",compute_type="int8",cpu_threads=threads,num_workers=1,local_files_only=True)
        else:
            import sherpa_onnx
            folder=ROOT/"build/bench-models"/name
            if name=="sensevoice":
                self.model=sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(folder/"model.int8.onnx"),tokens=str(folder/"tokens.txt"),num_threads=threads,provider="cpu",language="",use_itn=True)
            elif name=="paraformer":
                self.model=sherpa_onnx.OnlineRecognizer.from_paraformer(encoder=str(folder/"encoder.int8.onnx"),decoder=str(folder/"decoder.int8.onnx"),tokens=str(folder/"tokens.txt"),num_threads=threads,provider="cpu",enable_endpoint_detection=True,rule1_min_trailing_silence=2.4,rule2_min_trailing_silence=endpoint_silence,rule3_min_utterance_length=max_segment)
            else:raise ValueError(name)
        self.load_seconds=time.perf_counter()-start
    def transcribe(self,audio):
        if self.name=="whisper":
            segments,info=self.model.transcribe(audio,language=None,beam_size=1,condition_on_previous_text=False,vad_filter=False,temperature=0,initial_prompt="以下是中文普通話或 English 的會議內容。")
            text="".join(s.text for s in segments if s.no_speech_prob<.8 and s.avg_logprob>-1.2).strip()
            return text,info.language
        stream=self.model.create_stream()
        stream.accept_waveform(16000,audio)
        if self.name=="sensevoice":
            self.model.decode_stream(stream)
            text=re.sub(r"<\|.*?\|>","",stream.result.text).strip()
            return text,"zh" if re.search(r"[\u3400-\u9fff]",text) else "en"
        stream.accept_waveform(16000,np.zeros(int(.66*16000),np.float32));stream.input_finished()
        while self.model.is_ready(stream):self.model.decode_stream(stream)
        text=self.model.get_result(stream)
        return text,"zh" if re.search(r"[\u3400-\u9fff]",text) else "en"
    def recognize(self,job):
        start=time.perf_counter();text,language=self.transcribe(job.audio);asr_end=time.perf_counter()
        translated=self.translation(text,language);end=time.perf_counter()
        self.timings.append(dict(id=job.id,final=job.final,end=job.end,asr_s=asr_end-start,translation_s=end-asr_end))
        return text,translated,language

def summary_stream(events,item,timings,finished_by_eof):
    captions=[e for e in events if e.get("type")=="caption" and e.get("text")]
    finals=[e for e in captions if e["final"]]
    text=" ".join(e["original"] for e in finals)
    return dict(first_caption_after_speech_start_s=(captions[0]["emitted_at_s"]-item["speech_start_s"]) if captions else None,
        last_final_after_speech_end_s=(finals[-1]["emitted_at_s"]-item["speech_end_s"]) if finals else None,
        first_caption_at_s=captions[0]["emitted_at_s"] if captions else None,
        final_captions=len(finals),draft_captions=sum(not e["final"] for e in captions),
        dropped=sum(e.get("type")=="dropped" for e in events),
        finalized_by_eof=finished_by_eof,original=text,accuracy=accuracy(item["reference"],text,item["language"]),
        asr_compute_s=sum(x["asr_s"] for x in timings),translation_compute_s=sum(x["translation_s"] for x in timings),
        events=events,timings=timings)

def offline_stream(rec,item,partial_seconds=2.0):
    rec.timings=[];worker=Worker(io.BytesIO(),rec);events=[];start=time.perf_counter()
    worker.segmenter.partial_seconds=partial_seconds
    def send(**event):
        event["emitted_at_s"]=time.perf_counter()-start
        events.append(event)
    worker.send=send
    thread=threading.Thread(target=worker.inference,daemon=True);thread.start()
    audio=np.concatenate([item["audio"],np.zeros(32000,np.float32)])
    for offset in range(0,len(audio),1600):
        block=audio[offset:offset+1600];available=(offset+len(block))/16000
        delay=start+available-time.perf_counter()
        if delay>0:time.sleep(delay)
        worker.ingest(dict(pcm=base64.b64encode((block*32768).astype("<i2").tobytes()).decode("ascii"),start=offset/16000))
    finalized_by_eof=bool(worker.segmenter.blocks)
    worker.flush_audio()
    with worker.condition:worker.stopping=True;worker.condition.notify_all()
    thread.join(timeout=60)
    if thread.is_alive():raise TimeoutError("Inference did not finish")
    errors=[e for e in events if e.get("type")=="error"]
    if errors:raise RuntimeError(errors)
    return summary_stream(events,item,rec.timings,finalized_by_eof)

def paraformer_stream(rec,item):
    frames=queue.Queue(maxsize=120);events=[];timings=[];errors=[];eof_final=[False];start=time.perf_counter()
    def decode():
        try:
            stream=rec.model.create_stream();last_text="";last_translate_at=-1.;segment_id=1
            def emit(text,final,available,trigger):
                nonlocal last_translate_at
                t=time.perf_counter();language="zh" if re.search(r"[\u3400-\u9fff]",text) else "en"
                translated=rec.translation(text,language);end=time.perf_counter()
                timings.append(dict(asr_s=0,translation_s=end-t))
                events.append(dict(type="caption",id=segment_id,original=text,text=translated,final=final,
                    audio_available_s=available,trigger=trigger,emitted_at_s=end-start))
                last_translate_at=available
            available=0.
            while True:
                packet=frames.get()
                if packet is None:break
                block,available=packet;t=time.perf_counter()
                stream.accept_waveform(16000,block)
                while rec.model.is_ready(stream):rec.model.decode_stream(stream)
                text=rec.model.get_result(stream);endpoint=rec.model.is_endpoint(stream)
                timings.append(dict(asr_s=time.perf_counter()-t,translation_s=0))
                if text and endpoint:
                    emit(text,True,available,"endpoint");rec.model.reset(stream);last_text="";segment_id+=1;last_translate_at=-1.
                elif text and text!=last_text and available-last_translate_at>=.5:
                    emit(text,False,available,"partial");last_text=text
            t=time.perf_counter();stream.input_finished()
            while rec.model.is_ready(stream):rec.model.decode_stream(stream)
            text=rec.model.get_result(stream);timings.append(dict(asr_s=time.perf_counter()-t,translation_s=0))
            if text:emit(text,True,available,"eof");eof_final[0]=True
        except Exception as exc:errors.append(repr(exc))
    thread=threading.Thread(target=decode,daemon=True);thread.start()
    audio=np.concatenate([item["audio"],np.zeros(32000,np.float32)])
    for offset in range(0,len(audio),1600):
        block=audio[offset:offset+1600];available=(offset+len(block))/16000
        delay=start+available-time.perf_counter()
        if delay>0:time.sleep(delay)
        frames.put((block,available),timeout=10)
    frames.put(None);thread.join(timeout=60)
    if thread.is_alive():raise TimeoutError("Paraformer did not finish")
    if errors:raise RuntimeError(errors)
    return summary_stream(events,item,timings,eof_final[0])

def environment(threads):
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
        cpu=winreg.QueryValueEx(key,"ProcessorNameString")[0].strip()
    return dict(cpu=cpu,logical_cpus=os.cpu_count(),threads=threads,platform=platform.platform(),python=sys.version,
        packages={x:importlib.metadata.version(x) for x in ("sherpa-onnx","sherpa-onnx-core","faster-whisper","ctranslate2","numpy")},
        inference_network="blocked by socket guard",recording="none; file fixtures only")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--models",nargs="+",choices=["whisper","sensevoice","paraformer"],default=["whisper","sensevoice"])
    p.add_argument("--mode",choices=["batch","stream"],default="batch")
    p.add_argument("--threads",type=int,default=4)
    p.add_argument("--repetitions",type=int,default=3)
    p.add_argument("--fixtures",nargs="+")
    p.add_argument("--partial-seconds",type=float,default=2.)
    p.add_argument("--tag",default="")
    p.add_argument("--endpoint-silence",type=float,default=.64)
    p.add_argument("--max-segment",type=float,default=8.)
    args=p.parse_args();items=corpus()
    if not .5<=args.partial_seconds<=4:p.error("--partial-seconds must be between 0.5 and 4")
    if args.tag and not re.fullmatch(r"[a-z0-9-]+",args.tag):p.error("--tag must be a lowercase slug")
    if not .2<=args.endpoint_silence<=2:p.error("--endpoint-silence must be between 0.2 and 2")
    if not 4<=args.max_segment<=30:p.error("--max-segment must be between 4 and 30")
    if args.fixtures:items=[i for i in items if i["id"] in args.fixtures]
    if not items:raise ValueError("No matching fixtures")
    output=ROOT/"build/benchmark";output.mkdir(parents=True,exist_ok=True)
    translator=Translation(args.threads)
    for name in args.models:
        rec=Recognizer(name,args.threads,translator,args.endpoint_silence,args.max_segment)
        report=dict(model=name,variant=args.tag,mode=args.mode,environment=environment(args.threads),load_seconds=rec.load_seconds,
            fixtures=[{k:v for k,v in i.items() if k!="audio"} for i in items],results=[],
            settings=dict(pcm_packet_ms=100,offline_partial_s=args.partial_seconds,offline_max_segment_s=8,offline_vad_pause_s=.64,
                paraformer_endpoint_pause_s=args.endpoint_silence,paraformer_max_segment_s=args.max_segment,paraformer_translation_throttle_s=.5,tail_silence_s=2),
            warmup="one full English clip, including translation; excluded from timings")
        text,language=rec.transcribe(items[0]["audio"]);translator(text,language)
        print(json.dumps(dict(model=name,mode=args.mode,status="warmup complete")),flush=True)
        for item in items:
            for repeat in range(args.repetitions):
                if args.mode=="batch":
                    t=time.perf_counter();text,language=rec.transcribe(item["audio"]);asr=time.perf_counter()-t
                    t=time.perf_counter();caption=translator(text,language);mt=time.perf_counter()-t
                    row=dict(fixture=item["id"],repeat=repeat+1,asr_s=asr,translation_s=mt,total_s=asr+mt,
                        rtf=asr/item["duration_s"],original=text,caption=caption,accuracy=accuracy(item["reference"],text,item["language"]))
                else:
                    result=paraformer_stream(rec,item) if name=="paraformer" else offline_stream(rec,item,args.partial_seconds)
                    row=dict(fixture=item["id"],repeat=repeat+1,**result)
                report["results"].append(row)
                key=name+("-"+args.tag if args.tag else "")
                (output/f"{key}-{args.mode}.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                brief={k:v for k,v in row.items() if k not in ("events","timings","original","caption")}
                print(json.dumps(dict(model=name,mode=args.mode,**brief),ensure_ascii=False),flush=True)
        del rec
    return 0

if __name__=="__main__":sys.exit(main())
