"""Runs actual bundled models offline against synthetic speech fixtures."""
import json
import os
from pathlib import Path
import sys
import time
import wave
import socket
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from worker import Engine
from core import Job

root=Path(__file__).resolve().parents[1]
def deny_network(*args, **kwargs): raise AssertionError("Offline inference attempted a network connection")
socket.socket.connect = deny_network
socket.create_connection = deny_network
model_root=Path(sys.argv[1]) if len(sys.argv)>1 else root/"models"
engine=Engine(model_root,"auto")
report=[]
for language in ("en","zh"):
    fixture=root/f"build/qa/{language}.wav"
    if not fixture.exists():continue
    with wave.open(str(fixture),"rb") as w:
        assert w.getframerate()==16000 and w.getnchannels()==1
        audio=np.frombuffer(w.readframes(w.getnframes()),dtype="<i2").astype(np.float32)/32768
    start=time.perf_counter();original,text,detected=engine.recognize(Job(1,0,len(audio)/16000,audio,True));elapsed=time.perf_counter()-start
    assert original and text,(language,"empty caption")
    assert detected==language,(language,detected)
    assert any('\u3400'<=c<='\u9fff' for c in text),text
    report.append(dict(engine="sensevoice",language=language,original=original,text=text,seconds=round(elapsed,2),rtf=round(elapsed/(len(audio)/16000),3)))
assert report,"No synthetic fixtures available"
output=Path(os.environ.get("OFFLINE_CAPTIONS_TEST_OUTPUT",root/"build/qa-sensevoice"))
output.mkdir(parents=True,exist_ok=True)
out=output/"model-smoke.json";out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(out.read_text(encoding="utf-8"))
