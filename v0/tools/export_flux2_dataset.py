#!/usr/bin/env python3

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def export_split(entries, destination):
    destination.mkdir(parents=True, exist_ok=True)
    metadata = []
    exported = []
    expected_names = set()
    for number, entry in enumerate(entries, 1):
        source = Path(entry["source_path"])
        if not source.is_file():
            raise ValueError(f"Source file does not exist: {source}")
        if sha256(source) != entry["source_sha256"]:
            raise ValueError(f"Source hash changed: {source}")
        suffix = source.suffix.lower() or ".png"
        name = f"{number:03d}_{entry['asset_id']}{suffix}"
        target = destination / name
        shutil.copy2(source, target)
        expected_names.add(name)
        metadata.append({"file_name": name, "text": entry["caption"]})
        exported.append({
            "asset_id": entry["asset_id"],
            "file_name": name,
            "path": str(target),
            "sha256": sha256(target),
            "caption": entry["caption"],
            "provenance": entry["provenance"],
            "source_path": entry["source_path"],
            "source_sha256": entry["source_sha256"],
            "original_source_path": entry.get("original_source_path"),
            "original_source_sha256": entry.get("original_source_sha256")
        })
    for path in destination.iterdir():
        if path.name == "metadata.jsonl":
            continue
        if path.is_file() and path.name not in expected_names:
            path.unlink()
    metadata_path = destination / "metadata.jsonl"
    metadata_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in metadata),
        encoding="utf-8"
    )
    return exported


def main():
    parser = argparse.ArgumentParser(description="Export a reviewed SceneFactory dataset for FLUX.2 training.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()

    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    if not manifest.get("ready"):
        raise ValueError("Dataset manifest is not ready")
    if manifest.get("cross_split_exact_duplicates"):
        raise ValueError("Train and validation sets have duplicate hashes")

    train = export_split(manifest.get("train", []), arguments.output / "train")
    validation = export_split(manifest.get("validation", []), arguments.output / "validation")
    value = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(arguments.manifest.resolve()),
        "concept_id": manifest.get("concept_id"),
        "counts": {"train": len(train), "validation": len(validation)},
        "train": train,
        "validation": validation
    }
    output_manifest = arguments.output / "export_manifest.json"
    write_json(output_manifest, value)
    print(json.dumps({"export_manifest": str(output_manifest), "counts": value["counts"]}, indent=2))


if __name__ == "__main__":
    main()
