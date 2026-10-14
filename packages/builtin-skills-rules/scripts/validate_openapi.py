"""Validate that a file is an OpenAPI 3.x document. Implements: REQ-015."""

import argparse
import json
import sys
from pathlib import Path

import yaml


def load_document(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check an OpenAPI 3.x document")
    parser.add_argument("--file", required=True, dest="file_path")
    args = parser.parse_args()
    path = Path(args.file_path)
    if not path.is_file():
        print(json.dumps({"valid": False, "error": "file not found"}, ensure_ascii=False))
        return 2
    document = load_document(path)
    if not isinstance(document, dict) or "openapi" not in document:
        print(json.dumps({"valid": False, "error": "missing openapi field"}, ensure_ascii=False))
        return 2
    version = str(document["openapi"])
    if not version.startswith("3."):
        print(json.dumps({"valid": False, "error": "openapi version must be 3.x"}, ensure_ascii=False))
        return 2
    print(json.dumps({"valid": True, "openapi": version}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
