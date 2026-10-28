"""Create .env from .env.example with random dev secrets.

An existing .env is never rewritten: keys added to .env.example later are appended with fresh
random values, and nothing else is touched. Values are never printed.
"""

import base64
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
target = root / ".env"


def _fill(line: str) -> str:
    if line.endswith("=__generate__"):
        return line.replace("__generate__", secrets.token_urlsafe(24))
    if line.endswith("=__generate_b64_32__"):
        return line.replace(
            "__generate_b64_32__", base64.b64encode(secrets.token_bytes(32)).decode()
        )
    return line


def _key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0]


example = (root / ".env.example").read_text(encoding="utf-8").splitlines()

if not target.exists():
    target.write_text("\n".join(_fill(line) for line in example) + "\n", encoding="utf-8")
    print(".env created with random dev secrets")
    sys.exit(0)

present = {k for line in target.read_text(encoding="utf-8").splitlines() if (k := _key(line))}
missing = [line for line in example if (k := _key(line)) and k not in present]
if not missing:
    print(".env already complete - left unchanged")
    sys.exit(0)
with target.open("a", encoding="utf-8", newline="\n") as f:
    f.write("\n# added by just init\n" + "\n".join(_fill(line) for line in missing) + "\n")
print(f".env: added {', '.join(_key(line) or '' for line in missing)}")
