"""Real process-loopback smoke test; only a generated test tone is retained in memory."""
import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import threading
import time
import wave
import winsound
import numpy as np

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

capture=dll.oc_start(os.getpid(),None,callback,None)
try:
    assert ready.wait(20),"Capture activation timed out"
    assert not errors,errors
    samples=(np.sin(2*np.pi*440*np.arange(16000)/16000)*4000).astype("<i2")
    buffer=io.BytesIO()
    with wave.open(buffer,"wb") as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(samples.tobytes())
    winsound.PlaySound(buffer.getvalue(),winsound.SND_MEMORY|winsound.SND_NODEFAULT)
    time.sleep(.4)
finally:dll.oc_stop(capture)
audio=np.frombuffer(b"".join(frames),dtype="<i2").astype(float)
assert len(audio)>8000,f"Too little captured audio: {len(audio)} samples"
assert np.max(np.abs(audio))>100,"Captured only silence"
print(json.dumps({"status":"PASS","test":"native process loopback","captured_samples":len(audio),"peak":float(np.max(np.abs(audio))),"errors":errors}))
