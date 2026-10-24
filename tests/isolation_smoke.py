"""Two independent playback processes; capture only one process tree."""
import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import wave
import winsound
import numpy as np

def tone(frequency):
    samples=(np.sin(2*np.pi*frequency*np.arange(32000)/16000)*3000).astype("<i2")
    buffer=io.BytesIO()
    with wave.open(buffer,"wb") as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(samples.tobytes())
    return buffer.getvalue()

if len(sys.argv)>1 and sys.argv[1]=="--player":
    time.sleep(2)
    winsound.PlaySound(tone(int(sys.argv[2])),winsound.SND_MEMORY|winsound.SND_NODEFAULT)
    time.sleep(1)
    sys.exit(0)

root=Path(__file__).resolve().parents[1]
dll=ctypes.CDLL(str(root/"build/native/OfflineCapture.dll"))
CB=ctypes.CFUNCTYPE(None,ctypes.c_int,ctypes.c_void_p,ctypes.c_int,ctypes.c_double,ctypes.c_int,ctypes.c_void_p)
dll.oc_start.argtypes=[wintypes.DWORD,ctypes.c_wchar_p,CB,ctypes.c_void_p];dll.oc_start.restype=ctypes.c_void_p
dll.oc_stop.argtypes=[ctypes.c_void_p]
ready=threading.Event();frames=[];errors=[]
@CB
def callback(kind,data,count,start,error,context):
    if kind==2:ready.set()
    elif kind==1:errors.append(f"0x{error & 0xffffffff:08X}");ready.set()
    elif kind==0:frames.append(ctypes.string_at(data,count))

target=subprocess.Popen([sys.executable,__file__,"--player","440"],creationflags=subprocess.CREATE_NO_WINDOW)
other=subprocess.Popen([sys.executable,__file__,"--player","880"],creationflags=subprocess.CREATE_NO_WINDOW)
capture=dll.oc_start(target.pid,None,callback,None)
try:
    assert ready.wait(20),"Capture activation timed out"
    assert not errors,errors
    time.sleep(4.5)
finally:
    dll.oc_stop(capture)
    for process in (target,other):
        if process.poll() is None: process.terminate()
        process.wait(timeout=5)
audio=np.frombuffer(b"".join(frames),dtype="<i2").astype(float)
assert len(audio)>16000 and max(abs(audio))>100,"Missing target audio"
frequency=np.fft.rfftfreq(len(audio),1/16000);spectrum=abs(np.fft.rfft(audio))
def energy(center):return float(np.max(spectrum[(frequency>center-5)&(frequency<center+5)]))
selected,unselected=energy(440),energy(880)
assert selected>unselected*10,(selected,unselected)
report={"status":"PASS","test":"two-process audio isolation","selected_440hz":round(selected),"excluded_880hz":round(unselected),"ratio":round(selected/max(1,unselected),2)}
(root/"build/qa/isolation-test.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report))
