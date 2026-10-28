"""Create .env from .env.example with random dev secrets. Never overwrites an existing .env."""

import base64
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
target = root / ".env"
if target.exists():
    print(".env already exists - left unchanged")
    sys.exit(0)

lines = []
for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
    if line.endswith("=__generate__"):
        line = line.replace("__generate__", secrets.token_urlsafe(24))
    elif line.endswith("=__generate_b64_32__"):
        line = line.replace("__generate_b64_32__", base64.b64encode(secrets.token_bytes(32)).decode())
    lines.append(line)
target.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(".env created with random dev secrets")
