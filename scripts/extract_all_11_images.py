import os
import json
import time
from pathlib import Path
from google import genai
from google.genai import types
from PIL import Image

api_key = os.environ.get("GEMINI_API") or os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

img_dir = Path("dataset/evidence/images")
prompt_text = Path("code/prompts/vision_extract.md").read_text(encoding="utf-8")

results = {}

for p in sorted(img_dir.glob("*.png")):
    print(f"Extracting {p.name}...")
    img = Image.open(p)
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[prompt_text, img],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        dt = time.time() - t0
        data = json.loads(resp.text)
        results[p.name] = {
            "elapsed_s": round(dt, 2),
            "input_tokens": resp.usage_metadata.prompt_token_count,
            "output_tokens": resp.usage_metadata.candidates_token_count,
            "records": data
        }
        print(f"  Done in {dt:.2f}s: {len(data)} records extracted.")
    except Exception as e:
        print(f"  Error: {e}")

out_path = Path("dataset/evidence/images/vision_extractions_raw.json")
out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"Saved all 11 image extractions to {out_path}")
