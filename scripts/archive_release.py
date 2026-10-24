"""Archive the release tree, excluding legacy ASR weights from incremental builds."""
from pathlib import Path
import sys
import zipfile

def archive(root, destination):
    root=Path(root)
    allowed_models={"sensevoice-small-int8", "opus-en-zh"}
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for file in sorted(root.rglob("*")):
            if not file.is_file():continue
            relative=file.relative_to(root)
            if any(part in (".cache","__pycache__") for part in relative.parts):continue
            if relative.parts[0]=="models" and (len(relative.parts)<2 or relative.parts[1] not in allowed_models):continue
            z.write(file,relative.as_posix())

if __name__=="__main__":archive(sys.argv[1],sys.argv[2])
