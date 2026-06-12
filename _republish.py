"""Re-publish a specific output digest to docs/ (index + referenced assets)."""
import json
import re
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1])
out = Path("output")
docs = Path("docs")

html = src.read_text(encoding="utf-8")
m = re.search(r'<script type="application/json" id="articles-data">\s*(\{.*?\})\s*</script>', html, re.DOTALL)
meta = json.loads(m.group(1))

if docs.exists():
    shutil.rmtree(docs)
(docs / "images").mkdir(parents=True)
(docs / "articles").mkdir(parents=True)

shutil.copyfile(src, docs / "index.html")
copied_a = copied_i = 0
for aid, a in meta.items():
    f = out / "articles" / f"{aid}.json"
    if f.exists():
        shutil.copyfile(f, docs / "articles" / f.name)
        copied_a += 1
    if a.get("img"):
        img = out / a["img"]
        if img.exists():
            shutil.copyfile(img, docs / "images" / img.name)
            copied_i += 1

(docs / "CNAME").write_text("chuyenhay.com")
(docs / ".nojekyll").write_text("")
print(f"published {src.name}: {len(meta)} articles, {copied_a} content files, {copied_i} images")
