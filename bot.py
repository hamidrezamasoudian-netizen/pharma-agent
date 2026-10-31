import zlib, base64
from pathlib import Path
b64 = "".join(Path(f"_b{i}.txt").read_text() for i in range(4))
exec(zlib.decompress(base64.b64decode(b64)))
