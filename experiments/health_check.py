"""ตัวอย่างสคริปต์ทดลองที่ปลอดภัย: ตรวจไฟล์สำคัญของ Hermes"""

from pathlib import Path


root = Path(__file__).resolve().parents[1]
required = ["bot.py", ".env", "Modelfile"]
missing = [name for name in required if not (root / name).exists()]

if missing:
    print("MISSING:", ", ".join(missing))
    raise SystemExit(1)

print("Hermes health check: OK")
print("Required files:", ", ".join(required))
