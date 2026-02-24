#!/usr/bin/env python3
import argparse
import json
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


def main():
    ap = argparse.ArgumentParser(description="Generate or replace a single VC-FCST case via DeepSeek")
    ap.add_argument("--categories", default="benchmark/categories_top50.json")
    ap.add_argument("--template", default="benchmark/prompts/case_prompt_template.md")
    ap.add_argument("--category-id", default="", help="Target level3_id; if empty, use first category")
    ap.add_argument("--case-id", default="", help="Optional explicit case_id")
    ap.add_argument("--out-jsonl", default="datasets/case_bank.jsonl")
    ap.add_argument("--out-parquet", default="datasets/case_bank.parquet")
    ap.add_argument("--model", default="", help="Override MODEL_NAME in .env")
    args = ap.parse_args()

    schema = load_schema()
    categories = _load_categories(args.categories)
    category = None
    if args.category_id:
        for c in categories:
            if c.get("level3_id") == args.category_id:
                category = c
                break
        if category is None:
            raise SystemExit(f"category not found: {args.category_id}")
    else:
        category = categories[0]

    prompt = _render_prompt(args.template, category)
    text = chat_complete([{"role": "user", "content": prompt}], model=args.model or None)
    case = _parse_json_strict(text)
    errs = validate_case(case, schema)
    if errs:
        raise SystemExit("invalid case: " + "; ".join(errs))

    if args.case_id:
        case["case_id"] = args.case_id

    jsonl_path = Path(args.out_jsonl)
    items = _load_existing(jsonl_path)

    replaced = False
    for i, item in enumerate(items):
        if item.get("case_id") == case.get("case_id"):
            items[i] = case
            replaced = True
            break

    if not replaced:
        items.append(case)

    _write_jsonl(jsonl_path, items)
    _write_parquet(Path(args.out_parquet), items)

    print("ok", case.get("case_id"))


if __name__ == "__main__":
    raise SystemExit(main())
