"""Create a clean portable ZIP without logs, caches, or local experiment data."""

import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent
output = Path(sys.argv[1]) if len(sys.argv) > 1 else root.parent / "ISAS_wireless_portable.zip"
output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
    for file in sorted(root.rglob("*")):
        relative = file.relative_to(root)
        if not file.is_file() or any(part in relative.parts for part in ("logs", "pi_logs", "__pycache__")):
            continue
        if file.suffix in (".jsonl", ".zip", ".pyc", ".log"):
            continue
        if file.name == "ssh_settings.json":
            continue
        entry = Path("ISAS_wireless") / relative
        if file.suffix == ".sh":
            # ZIP consumers on Linux must not receive Windows CRLF shebangs.
            package.writestr(str(entry).replace("\\", "/"), file.read_text(encoding="utf-8"))
        else:
            package.write(file, entry)
print(output)
