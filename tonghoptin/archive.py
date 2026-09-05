"""Append-only crawl records and portable, checksummed archive packs."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import os
import zipfile
import io
import re
from concurrent.futures import ThreadPoolExecutor
from collections import deque


@contextmanager
def collection_lock(output):
    """OS lock is released even after a crash; lock file itself is permanent."""
    path = Path(output) / ".collection.lock"
    with path.open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another collection is running") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def save_run(output, label, start, end, articles, results):
    folder = Path(output) / "runs"
    folder.mkdir(exist_ok=True)
    coverage = []
    for result in results:
        coverage.append({"site_name": result.site_name, "status": result.status.value,
                         "articles_count": len(result.articles), "stubs_discovered": result.stubs_discovered,
                         "errors_count": len(result.errors), "errors": result.errors,
                         "discovery": result.discovery, "outcomes": result.outcomes,
                         "duration_seconds": result.duration_seconds})
    report = {"schema_version": 1, "run_id": label, "timezone": "Asia/Ho_Chi_Minh",
              "start_date": start.isoformat(), "end_date": end.isoformat(),
              "captured_at": datetime.now(timezone.utc).isoformat(),
              "coverage_claim": "best_effort_not_exhaustive", "sources": coverage,
              "articles": [asdict(a) for a in articles],
              "parsed_articles": [asdict(a) for r in results for a in r.parsed_articles]}
    with (folder / (label + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, default=lambda value: value.isoformat())
    return coverage


def load_index(destination):
    destination = Path(destination)
    path = destination / "index.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 2:
        return data
    result = {}
    for shard in data["shards"]:
        if not re.fullmatch(r"[0-9a-f]{2}\.json", shard):
            raise ValueError("Unsafe index shard name")
        result.update(json.loads((destination / "index" / shard).read_text(encoding="utf-8")))
    return result


def backup(root, destination, exclude=()):
    """Back up output, published assets and crawl logs without private browser data.

    Packs contain <=32 MiB of uncompressed data and individual files can span
    packs. Earlier packs and manifests are never removed or rewritten.
    """
    root, destination = Path(root), Path(destination)
    packs = destination / "packs"
    packs.mkdir(parents=True, exist_ok=True)
    index_path = destination / "index.json"
    index = load_index(destination)
    content_records = {record["sha256"]: record for record in index.values()}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    pack = None
    pack_size = 0
    pack_number = 0
    updated = {}
    pack_hashes = {}
    def paths():
        for name in ("output", "docs"):
            for folder, directories, filenames in os.walk(root / name):
                directories.sort()
                for filename in sorted(filenames):
                    yield Path(folder) / filename
        for name in ("tonghoptin.log", "tonghoptin_runs.log"):
            if (root / name).exists():
                yield root / name

    def read_input(path):
        if path.is_symlink():
            return path, None, None
        stat = path.stat()
        rel = path.relative_to(root).as_posix()
        previous = index.get(rel)
        skip = rel in exclude or path.name.endswith((".lock", "-wal", "-shm", ".tmp"))
        unchanged = previous and previous["size"] == stat.st_size and previous["mtime_ns"] == stat.st_mtime_ns
        # Parallel read-ahead hides cold-file latency without buffering the dataset.
        data = path.read_bytes() if not skip and not unchanged and stat.st_size <= 1024 * 1024 else None
        return path, stat, data

    def inputs():
        iterator = iter(paths())
        with ThreadPoolExecutor(max_workers=32) as pool:
            pending = deque()
            for _ in range(96):
                path = next(iterator, None)
                if path is not None:
                    pending.append(pool.submit(read_input, path))
            while pending:
                yield pending.popleft().result()
                path = next(iterator, None)
                if path is not None:
                    pending.append(pool.submit(read_input, path))
    def close_pack():
        if pack:
            pack.close()
            pack_hashes[pack_path.name] = hashlib.sha256(pack_path.read_bytes()).hexdigest()
    try:
        for path, stat, prefetched in inputs():
            if stat is None:
                continue
            if path.name.endswith((".lock", "-wal", "-shm", ".tmp")):
                continue
            rel = path.relative_to(root).as_posix()
            if rel in exclude:
                continue
            previous = index.get(rel)
            if previous and previous["size"] == stat.st_size and previous["mtime_ns"] == stat.st_mtime_ns:
                continue
            if previous and previous["size"] == stat.st_size:
                with (io.BytesIO(prefetched) if prefetched is not None else path.open("rb")) as stream:
                    unchanged = hashlib.file_digest(stream, "sha256").hexdigest() == previous["sha256"]
                if unchanged:
                    previous["mtime_ns"] = stat.st_mtime_ns
                    continue
            if prefetched is not None:
                content_hash = hashlib.sha256(prefetched).hexdigest()
                shared = content_records.get(content_hash)
                if shared:
                    updated[rel] = {"size": len(prefetched), "mtime_ns": stat.st_mtime_ns,
                                    "sha256": content_hash, "parts": shared["parts"]}
                    if len(updated) % 10000 == 0:
                        print(f"Archived {len(updated)} files...", flush=True)
                    continue
            digest = hashlib.sha256()
            parts = []
            captured_size = 0
            with (io.BytesIO(prefetched) if prefetched is not None else path.open("rb")) as stream:
                while True:
                    chunk = stream.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    captured_size += len(chunk)
                    if pack is None or pack_size + len(chunk) > 32 * 1024 * 1024:
                        close_pack()
                        pack_number += 1
                        pack_path = packs / f"{stamp}-{pack_number:05}.zip"
                        pack = zipfile.ZipFile(pack_path, "x", zipfile.ZIP_DEFLATED, compresslevel=6)
                        pack_size = 0
                    member = f"{hashlib.sha256(rel.encode()).hexdigest()}/{len(parts):05}"
                    stored = path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".gz", ".zip", ".pdf")
                    pack.writestr(member, chunk, compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
                    parts.append({"pack": pack_path.name, "member": member})
                    pack_size += len(chunk)
            updated[rel] = {"size": captured_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest.hexdigest(), "parts": parts}
            content_records[updated[rel]["sha256"]] = updated[rel]
            if len(updated) % 10000 == 0:
                print(f"Archived {len(updated)} files...", flush=True)
        close_pack()
    except BaseException:
        if pack:
            pack.close()
        raise
    index.update(updated)
    manifests = destination / "manifests"
    manifests.mkdir(exist_ok=True)
    entries = list(updated.items())
    for offset in range(0, max(1, len(entries)), 10000):
        manifest = {"schema_version": 2, "captured_at": stamp, "files": dict(entries[offset:offset + 10000]), "packs": pack_hashes if offset == 0 else {}}
        (manifests / f"{stamp}-{offset // 10000:04}.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    shards = {}
    for path, record in index.items():
        shard = hashlib.sha256(path.encode()).hexdigest()[:2] + ".json"
        shards.setdefault(shard, {})[path] = record
    (destination / "index").mkdir(exist_ok=True)
    for shard, records in shards.items():
        shard_path = destination / "index" / shard
        data = json.dumps(records, ensure_ascii=False)
        if not shard_path.exists() or shard_path.read_text(encoding="utf-8") != data:
            temporary_shard = shard_path.with_suffix(".tmp")
            temporary_shard.write_text(data, encoding="utf-8")
            temporary_shard.replace(shard_path)
    temporary = index_path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"schema_version": 2, "total_paths": len(index), "shards": sorted(shards)}), encoding="utf-8")
    temporary.replace(index_path)
    return {"files_added_or_changed": len(updated), "total_paths": len(index), "packs_created": pack_number, "manifest": stamp}


def restore(destination, target, verify_only=False):
    """Validate every pack/file and optionally restore the latest path index."""
    destination, target = Path(destination), Path(target).resolve()
    index = load_index(destination)
    for manifest in (destination / "manifests").glob("*.json"):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for name, expected in data["packs"].items():
            if not re.fullmatch(r"[0-9TZ-]+\.zip", name):
                raise ValueError("Unsafe pack name")
            path = destination / "packs" / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Corrupt pack: {name}")
    from collections import OrderedDict
    opened = OrderedDict()
    verified_payloads = set()
    try:
        # Read adjacent packed payloads together instead of repeatedly reopening ZIPs.
        ordered = sorted(index.items(), key=lambda item: item[1]["parts"][0]["pack"] if item[1]["parts"] else "")
        for rel, record in ordered:
            # Verification does not extract anything: validate the portable path
            # lexically, avoiding hundreds of thousands of Windows realpath calls.
            if (not rel or rel.startswith(("/", "\\")) or "\\" in rel or ":" in rel
                    or ".." in PurePosixPath(rel).parts):
                raise ValueError("Archive path escaped destination")
            path = None if verify_only else (target / rel).resolve()
            if path is not None and not path.is_relative_to(target):
                raise ValueError("Archive path escaped destination")
            signature = (record["sha256"], record["size"], tuple((part["pack"], part["member"]) for part in record["parts"]))
            if verify_only and signature in verified_payloads:
                continue
            digest = hashlib.sha256()
            size = 0
            stream = None
            if not verify_only:
                path.parent.mkdir(parents=True, exist_ok=True)
                stream = path.open("xb")  # never overwrite an existing restore target
            try:
                for part in record["parts"]:
                    pack_name = part["pack"]
                    if not re.fullmatch(r"[0-9TZ-]+\.zip", pack_name):
                        raise ValueError("Unsafe pack name")
                    if pack_name not in opened:
                        if len(opened) >= 24:
                            _, old_pack = opened.popitem(last=False)
                            old_pack.close()
                        opened[pack_name] = zipfile.ZipFile(destination / "packs" / pack_name)
                    opened.move_to_end(pack_name)
                    chunk = opened[pack_name].read(part["member"])
                    digest.update(chunk)
                    size += len(chunk)
                    if stream:
                        stream.write(chunk)
            finally:
                if stream:
                    stream.close()
            if digest.hexdigest() != record["sha256"] or size != record["size"]:
                raise ValueError(f"Corrupt file: {rel}")
            verified_payloads.add(signature)
    finally:
        for pack in opened.values():
            pack.close()
    return len(index)
