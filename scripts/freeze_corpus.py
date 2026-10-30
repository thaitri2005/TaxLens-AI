"""Freeze the corpus for an experiment, or check that it has not changed since.

    python scripts/freeze_corpus.py --label corpus-v1 --output data/evaluation/corpus/corpus-v1.json
    python scripts/freeze_corpus.py --check data/evaluation/corpus/corpus-v1.json
"""

import argparse
import json
import sys
from pathlib import Path

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.evaluation.corpus_manifest import (
    build_corpus_manifest,
    code_version,
    compare_manifests,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path, help="Write a new manifest to this file")
    action.add_argument("--check", type=Path, help="Compare the corpus with this manifest")
    parser.add_argument("--label", help="Name of the frozen corpus, e.g. corpus-v1")
    arguments = parser.parse_args()

    settings = get_settings()
    with SessionLocal() as session:
        manifest = build_corpus_manifest(
            session,
            settings.embedding_model_id,
            settings.embedding_model_revision,
            label=arguments.label,
            code_version=code_version(),
        )

    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(json.dumps(_summary(manifest), ensure_ascii=False, indent=2))
        return

    frozen = json.loads(arguments.check.read_text(encoding="utf-8"))
    difference = compare_manifests(frozen, manifest)
    print(
        json.dumps(
            {
                "frozen": _summary(frozen),
                "current": _summary(manifest),
                **difference,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not difference["unchanged"]:
        sys.exit(1)


def _summary(manifest: dict) -> dict:
    return {
        key: manifest.get(key)
        for key in (
            "label",
            "created_at",
            "fingerprint",
            "document_count",
            "version_count",
            "chunk_count",
            "embedded_chunk_count",
        )
    }


if __name__ == "__main__":
    main()
