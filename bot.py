import zlib, base64
from pathlib import Path
parts = []
for i in range(4):
    parts.append(Path(f"_b{i}.txt").read_text().strip())
b64 = "".join(parts)
pad = (-len(b64)) % 4
if pad:
    b64 += "=" * pad
exec(zlib.decompress(base64.b64decode(b64)))
