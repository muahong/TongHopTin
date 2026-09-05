"""Materialize every published docs/index.html version from Git history.

The normal collector permanently retains new timestamped output. This utility
recovers older published HTML versions that predate that policy and records a
SHA-256 manifest. It is idempotent and never deletes or overwrites a different
historical file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path


def git(*args: str, binary: bool = False) -> bytes | str:
    """Run a read-only Git command and return its output."""
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=not binary,
        encoding=None if binary else "utf-8",
    )
    return result.stdout


def history_entries() -> list[tuple[str, str, str]]:
    """Return commit, ISO timestamp, and subject for every published digest."""
    output = git(
        "log",
        "--reverse",
        "--format=%H%x09%cI%x09%s",
        "--",
        "docs/index.html",
    )
    assert isinstance(output, str)
    return [tuple(line.split("\t", 2)) for line in output.splitlines() if line]


def archive_filename(commit: str, committed_at: str) -> str:
    """Build a chronological, collision-proof historical HTML filename."""
    stamp = datetime.fromisoformat(committed_at).strftime("%Y-%m-%d_%H%M%S")
    return f"tonghoptin_{stamp}_git-{commit[:10]}.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("output/history/html"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("output/history/manifest.jsonl"),
    )
    args = parser.parse_args()

    args.destination.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    entries = history_entries()
    manifest_rows: list[dict[str, object]] = []
    for index, (commit, committed_at, subject) in enumerate(entries, 1):
        content = git("show", f"{commit}:docs/index.html", binary=True)
        assert isinstance(content, bytes)
        digest = hashlib.sha256(content).hexdigest()
        filename = archive_filename(commit, committed_at)
        destination = args.destination / filename

        if destination.exists():
            existing_digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            if existing_digest != digest:
                raise FileExistsError(
                    f"Refusing to overwrite different historical file: {destination}"
                )
        else:
            destination.write_bytes(content)

        manifest_rows.append(
            {
                "commit": commit,
                "committed_at": committed_at,
                "subject": subject,
                "file": destination.as_posix(),
                "bytes": len(content),
                "sha256": digest,
            }
        )
        if index == 1 or index % 25 == 0 or index == len(entries):
            print(f"[{index}/{len(entries)}] {filename}", flush=True)

    args.manifest.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    print(
        f"Saved {len(entries)} historical HTML versions to {args.destination} "
        f"with manifest {args.manifest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
