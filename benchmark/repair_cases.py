#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from case_bank import load_schema, validate_case
from adapter_llm import _env_with_filters
from deepseek_client import chat_complete


def _load_items(path: Path) -> List[Dict[str, Any]]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))
    return items


def _write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _write_parquet(path: Path, items: List[Dict[str, Any]]) -> None:
    import pandas as pd  # type: ignore

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(items).to_parquet(path, index=False)


def _render_fix_prompt(case: Dict[str, Any]) -> str:
    env = _env_with_filters()
    template = env.from_string(
        """
You are fixing a VC-FCST case. The case has invalid fields (null values) and must be corrected.

Requirements:
1) Output ONLY valid JSON for the full case, no extra text.
2) Preserve all existing fields and values unless they are null or invalid.
3) For any file content that is null, replace it with a valid string that matches the requirement.
4) Keep schema exactly as provided.

Case JSON:
{{ case_json }}
"""
    )
    return template.render(case_json=json.dumps(case, ensure_ascii=False))


def _parse_json_strict(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _has_null_initial_code(case: Dict[str, Any]) -> bool:
    init = case.get("initial_code", {})
    for _, v in (init or {}).items():
        if v is None:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description="Repair invalid cases via DeepSeek")
    ap.add_argument("--input", default="datasets/case_bank.jsonl")
    ap.add_argument("--out-jsonl", default="datasets/case_bank.jsonl")
    ap.add_argument("--out-parquet", default="datasets/case_bank.parquet")
    ap.add_argument("--model", default="", help="Override MODEL_NAME in .env")
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--sleep-sec", type=float, default=1.0)
    args = ap.parse_args()

    schema = load_schema()
    items = _load_items(Path(args.input))

    repaired = 0
    for i, case in enumerate(items):
        if not _has_null_initial_code(case):
            continue

        prompt = _render_fix_prompt(case)
        last_err = ""
        fixed = None
        for _ in range(args.max_retries):
            try:
                text = chat_complete(
                    [
                        {"role": "system", "content": "Output ONLY strict JSON. No extra text."},
                        {"role": "user", "content": prompt},
                    ],
                    model=args.model or None,
                )
                if not (text or "").strip():
                    raise ValueError("empty_response")
                fixed = _parse_json_strict(text)
                errs = validate_case(fixed, schema)
                if not errs:
                    break
                last_err = "; ".join(errs)
                fixed = None
            except Exception as exc:
                last_err = str(exc)
                fixed = None
            import time

            time.sleep(args.sleep_sec)

        if fixed is None:
            raise SystemExit(f"failed to repair {case.get('case_id')}: {last_err}")

        items[i] = fixed
        repaired += 1
        print("repaired", fixed.get("case_id"))

        _write_jsonl(Path(args.out_jsonl), items)
        _write_parquet(Path(args.out_parquet), items)

    print("done", repaired)


if __name__ == "__main__":
    raise SystemExit(main())
