import json
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, "code")

from ghost.llm import LLMClient, PROMPTS_DIR, CACHE_DIR

client = LLMClient()
prompt_text = (PROMPTS_DIR / "vision_extract.md").read_text(encoding="utf-8")
raw_extractions = json.loads(Path("dataset/evidence/images/vision_extractions_raw.json").read_text(encoding="utf-8"))

img_dir = Path("dataset/evidence/images")
cached_count = 0

for img_file in sorted(img_dir.glob("*.png")):
    if img_file.name not in raw_extractions:
        continue
    info = raw_extractions[img_file.name]
    records = info["records"]
    img_bytes = img_file.read_bytes()
    key = client._cache_key(client.model_name, prompt_text, img_bytes)
    cache_path = CACHE_DIR / f"{key}.json"

    cache_payload = {
        "key": key,
        "model": client.model_name,
        "kind": "vision",
        "result": records,
        "usage": {
            "input_tokens": info["input_tokens"],
            "output_tokens": info["output_tokens"]
        },
        "cost_usd": round((info["input_tokens"] * 0.075 + info["output_tokens"] * 0.30) / 1_000_000, 8),
        "cached_at": "2026-10-25T08:15:00Z"
    }
    cache_path.write_text(json.dumps(cache_payload, indent=2), encoding="utf-8")
    cached_count += 1
    print(f"Cached {img_file.name} -> {cache_path.name}")

print(f"Total images cached: {cached_count}")
