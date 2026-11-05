"""Interactive SSH launcher; passwords and private-key contents are never stored."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if not shutil.which("ssh"):
    raise SystemExit("OpenSSH client not found. Install/enable the OpenSSH client first.")
settings = root / "ssh_settings.json"
config = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
print("ISAS SSH input. No password is saved. Use your existing remote JSONL command.")
destination = input(f"SSH user@host or alias [{config.get('destination','')}]: ").strip() or config.get("destination", "")
command = input(f"Remote command [{config.get('command','')}]: ").strip() or config.get("command", "")
if not destination or not command:
    raise SystemExit("SSH address and remote command are required. Run again when these are known.")
if destination.startswith("-"):
    raise SystemExit("Invalid SSH destination")
settings.write_text(json.dumps({"destination":destination,"command":command},indent=2), encoding="utf-8")
raise SystemExit(subprocess.call([sys.executable,str(root/"server.py"),"--host","127.0.0.1","--ssh",destination,"--ssh-command",command],cwd=root))
