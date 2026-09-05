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

(docs / "images").mkdir(parents=True, exist_ok=True)
(docs / "articles").mkdir(parents=True, exist_ok=True)

shutil.copyfile(src, docs / "index.html")
copied_a = copied_s = copied_i = 0
for aid, a in meta.items():
    content_base = Path(a.get("content", f"articles/{aid}"))
    if content_base.is_absolute() or content_base.drive or ".." in content_base.parts or content_base.parts[0] != "articles":
        raise ValueError("Unsafe archive content path")
    f = out / content_base.with_suffix(".json")
    if f.exists():
        destination = docs / content_base.with_suffix(".json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, destination)
        copied_a += 1
    script = out / content_base.with_suffix(".js")
    if script.exists():
        destination = docs / content_base.with_suffix(".js")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(script, destination)
        copied_s += 1
    if a.get("img"):
        relative_image = Path(a["img"])
        if relative_image.is_absolute() or relative_image.drive or ".." in relative_image.parts or relative_image.parts[0] != "images":
            raise ValueError("Unsafe archive image path")
        img = out / relative_image
        if img.exists():
            shutil.copyfile(img, docs / "images" / img.name)
            copied_i += 1

(docs / "CNAME").write_text("chuyenhay.com")
(docs / ".nojekyll").write_text("")
print(
    f"published {src.name}: {len(meta)} articles, "
    f"{copied_a} JSON + {copied_s} JS content files, {copied_i} images"
)
