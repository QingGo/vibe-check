#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from case_bank import load_schema, validate_case
from adapter_llm import _env_with_filters
from deepseek_client import chat_complete


def _load_categories(path: str) -> List[Dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _render_prompt(template_path: str, category: Dict[str, Any]) -> str:
    env = _env_with_filters()
    tmpl = env.from_string(Path(template_path).read_text(encoding="utf-8"))
    return tmpl.render(**category)


def _parse_json_strict(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _load_existing(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
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


def _case_id_for(category_id: str) -> str:
    return f"VCFCST-{category_id}-001"


def main():
    ap = argparse.ArgumentParser(description="Generate Top50 cases (one per category) via DeepSeek")
    ap.add_argument("--categories", default="benchmark/categories_top50.json")
    ap.add_argument("--template", default="benchmark/prompts/case_prompt_template.md")
    ap.add_argument("--out-jsonl", default="datasets/case_bank.jsonl")
    ap.add_argument("--out-parquet", default="datasets/case_bank.parquet")
    ap.add_argument("--model", default="", help="Override MODEL_NAME in .env")
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--sleep-sec", type=float, default=1.0)
    args = ap.parse_args()

    schema = load_schema()
    categories = _load_categories(args.categories)

    jsonl_path = Path(args.out_jsonl)
    items = _load_existing(jsonl_path)

    # Index existing by case_id for replace
    by_id = {item.get("case_id"): i for i, item in enumerate(items)}

    for category in categories:
        case_id = _case_id_for(category["level3_id"])
        prompt = _render_prompt(args.template, category)
        last_err = ""
        case = None
        for _ in range(args.max_retries):
            try:
                text = chat_complete(
                    [
                        {
                            "role": "system",
                            "content": "Output ONLY strict JSON. No extra text.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    model=args.model or None,
                )
                if not (text or "").strip():
                    last_err = "empty_response"
                    case = None
                    raise ValueError(last_err)
                case = _parse_json_strict(text)
                case["case_id"] = case_id
                errs = validate_case(case, schema)
                if not errs:
                    break
                last_err = "; ".join(errs)
                case = None
            except Exception as exc:
                last_err = str(exc)
                case = None
            time.sleep(args.sleep_sec)
        if case is None:
            raise SystemExit(f"failed to generate {case_id}: {last_err}")

        if case_id in by_id:
            items[by_id[case_id]] = case
        else:
            items.append(case)
            by_id[case_id] = len(items) - 1

        print("ok", case_id)

        # Persist after each successful case to avoid losing progress.
        _write_jsonl(jsonl_path, items)
        _write_parquet(Path(args.out_parquet), items)

    _write_jsonl(jsonl_path, items)
    _write_parquet(Path(args.out_parquet), items)


if __name__ == "__main__":
    raise SystemExit(main())
