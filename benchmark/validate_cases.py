#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from case_bank import load_schema, normalize_case, validate_case


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main():
    ap = argparse.ArgumentParser(description="Validate VC-FCST cases")
    ap.add_argument("--input", required=True, help="Input jsonl or parquet")
    ap.add_argument("--schema", default="benchmark/case_schema.json")
    args = ap.parse_args()

    schema = load_schema(args.schema)
    path = Path(args.input)
    cases: List[Dict[str, Any]] = []
    if path.suffix == ".jsonl":
        cases = list(_iter_jsonl(path))
    else:
        try:
            import pandas as pd  # type: ignore

            df = pd.read_parquet(path)
            cases = [normalize_case(row) for row in df.to_dict(orient="records")]
        except Exception as exc:
            raise SystemExit(f"failed to read parquet: {exc}") from exc

    total = len(cases)
    errors = 0
    for case in cases:
        errs = validate_case(case, schema)
        if errs:
            errors += 1
            print(f"{case.get('case_id', 'unknown')}: {errs}")
    print(f"total={total} invalid={errors}")


if __name__ == "__main__":
    raise SystemExit(main())
