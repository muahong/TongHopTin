"""Recover completed packs from an interrupted initial backup without rereading source bodies.

Only complete files matching the current source length are indexed. mtime=0
forces the next backup to recheck source hashes before reusing those records.
Incomplete ZIP files are moved to a local quarantine, never uploaded.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile
from datetime import datetime, timezone


def recover(root, archive):
    root, archive = Path(root).resolve(), Path(archive).resolve()
    lookup = {}
    for name in ("output", "docs"):
        for folder, _, files in os.walk(root / name):
            for filename in files:
                path = Path(folder) / filename
                rel = path.relative_to(root).as_posix()
                lookup[hashlib.sha256(rel.encode()).hexdigest()] = rel
    for name in ("tonghoptin.log", "tonghoptin_runs.log"):
        lookup[hashlib.sha256(name.encode()).hexdigest()] = name
    records, pack_hashes = {}, {}
    quarantine = root / ".audit" / "incomplete-packs"
    quarantine.mkdir(parents=True, exist_ok=True)
    for number, path in enumerate(sorted((archive / "packs").glob("*.zip")), 1):
        try:
            pack = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            path.rename(quarantine / path.name)
            continue
        with pack:
            for member in pack.infolist():
                key, part = member.filename.split("/")
                if key not in lookup:
                    continue
                rel = lookup[key]
                record = records.setdefault(rel, {"size": 0, "digest": hashlib.sha256(), "parts": [], "complete": True})
                if int(part) != len(record["parts"]):
                    record["complete"] = False
                data = pack.read(member)
                record["digest"].update(data)
                record["size"] += len(data)
                record["parts"].append({"pack": path.name, "member": member.filename})
        with path.open("rb") as stream:
            pack_hashes[path.name] = hashlib.file_digest(stream, "sha256").hexdigest()
        print(f"Recovered pack {number}: {len(records)} paths", flush=True)
    index = {}
    for rel, record in records.items():
        if record["complete"] and (root / rel).stat().st_size == record["size"]:
            index[rel] = {"size": record["size"], "mtime_ns": 0,
                          "sha256": record["digest"].hexdigest(), "parts": record["parts"]}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (archive / "manifests").mkdir(exist_ok=True)
    entries = list(index.items())
    for offset in range(0, max(1, len(entries)), 10000):
        manifest = {"schema_version": 2, "captured_at": stamp, "recovered_after_interruption": True,
                    "files": dict(entries[offset:offset + 10000]), "packs": pack_hashes if offset == 0 else {}}
        (archive / "manifests" / f"{stamp}-{offset // 10000:04}.json").write_text(json.dumps(manifest), encoding="utf-8")
    shards = {}
    for rel, record in index.items():
        shards.setdefault(hashlib.sha256(rel.encode()).hexdigest()[:2] + ".json", {})[rel] = record
    (archive / "index").mkdir(exist_ok=True)
    for shard, values in shards.items():
        (archive / "index" / shard).write_text(json.dumps(values), encoding="utf-8")
    (archive / "index.json").write_text(json.dumps({"schema_version": 2, "total_paths": len(index), "shards": sorted(shards)}), encoding="utf-8")
    print(json.dumps({"recovered_paths": len(index), "completed_packs": len(pack_hashes)}), flush=True)


if __name__ == "__main__":
    recover(Path.cwd(), Path("archive"))
