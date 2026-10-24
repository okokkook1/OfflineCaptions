import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

script=Path(__file__).resolve().parents[1]/"scripts/archive_release.py"
spec=importlib.util.spec_from_file_location("archive_release",script)
release=importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

class ReleaseArchiveTests(unittest.TestCase):
    def test_incremental_release_excludes_old_asr_weights_and_keeps_sensevoice(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);root=base/"app"
            names=["OfflineCaptions.exe","models/sensevoice-small-int8/model.int8.onnx",
                   "models/opus-en-zh/model.bin","models/whisper-base/model.bin",
                   "models/.downloads/cache.bin","backend/__pycache__/worker.pyc"]
            for name in names:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b"fixture")
            release.archive(root,base/"app.zip")
            with zipfile.ZipFile(base/"app.zip") as z:
                self.assertEqual(set(z.namelist()),set(names[:3]))

if __name__=="__main__":unittest.main()
