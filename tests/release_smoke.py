"""Verify the delivered ZIP, not just the development model directory."""
from pathlib import Path
import hashlib
import json
import zipfile

root=Path(__file__).resolve().parents[1]
path=root/"dist/OfflineCaptions-Windows-x64.zip"
with zipfile.ZipFile(path) as z:
    names=set(z.namelist())
    required={"OfflineCaptions.exe","OfflineCapture.dll","runtime/python.exe","runtime/msvcp140.dll",
              "models/sensevoice-small-int8/model.int8.onnx","models/sensevoice-small-int8/tokens.txt",
              "models/opus-en-zh/model.bin","licenses/sensevoice-MODEL_LICENSE.txt","VALIDATION.md"}
    assert required<=names,required-names
    assert not any(n.startswith("models/whisper-") for n in names),"Legacy ASR weights included"
    assert any(n.startswith("runtime/Lib/site-packages/sherpa_onnx/") for n in names),"Missing sherpa-onnx runtime"
    assert z.read("backend/worker.py")== (root/"backend/worker.py").read_bytes(),"Worker differs from verified source"
    assert z.read("backend/models.py")== (root/"backend/models.py").read_bytes(),"Model manager differs from verified source"
    assert z.testzip() is None,"Archive CRC failure"
    model="models/sensevoice-small-int8/model.int8.onnx"
    with z.open(model) as f:
        h=hashlib.sha256()
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    provenance=json.loads((root/"build/bench-models/sensevoice/provenance.json").read_text(encoding="utf-8"))
    assert h.hexdigest()==provenance["files"]["model.int8.onnx"]["sha256"]
    report=dict(status="PASS",version="0.2.1",engine="sensevoice",files=len(names),archive_bytes=path.stat().st_size,
                model_revision=provenance["revision"],model_sha256=h.hexdigest(),legacy_whisper_weights=False)
out=root/"build/qa-sensevoice/release-test.json"
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report))
