from pathlib import Path
parts = sorted(Path(__file__).parent.glob("_bot_part*.txt"))
if not parts:
    raise SystemExit("missing _bot_part*.txt")
src = "".join(p.read_text(encoding="utf-8") for p in parts)
exec(compile(src, "bot.py", "exec"), globals())
