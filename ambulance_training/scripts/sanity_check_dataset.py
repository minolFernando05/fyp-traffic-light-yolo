from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "roboflow_export"

yaml_path = DATA_DIR / "data.yaml"
if not yaml_path.exists():
    raise SystemExit(f"Missing data.yaml at {yaml_path}")

cfg = yaml.safe_load(yaml_path.read_text())
print("Loaded data.yaml:", cfg)

# Try to find images/labels folders
candidates = [
    DATA_DIR / "train" / "images",
    DATA_DIR / "train" / "labels",
    DATA_DIR / "valid" / "images",
    DATA_DIR / "valid" / "labels",
    DATA_DIR / "val" / "images",
    DATA_DIR / "val" / "labels",
]

for p in candidates:
    print(f"{p}: {'OK' if p.exists() else 'MISSING'}")

# Count some images
img_dirs = [DATA_DIR / "train" / "images", DATA_DIR / "valid" / "images", DATA_DIR / "val" / "images"]
for d in img_dirs:
    if d.exists():
        imgs = list(d.glob("*.jpg")) + list(d.glob("*.png")) + list(d.glob("*.jpeg"))
        print(d, "image count =", len(imgs))
