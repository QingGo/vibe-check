#!/usr/bin/env python3
import argparse
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List

from case_bank import load_schema, validate_case


def _require_jinja():
    try:
        from jinja2 import Template  # type: ignore

        return Template
    except Exception as exc:
        raise SystemExit("jinja2 is required: pip install jinja2") from exc


def _require_litellm():
    try:
        import litellm  # type: ignore

        return litellm
    except Exception as exc:
        raise SystemExit("litellm is required: pip install litellm") from exc


def _load_categories(path: str) -> List[Dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _render_prompt(template_path: str, category: Dict[str, Any]) -> str:
    Template = _require_jinja()
    tmpl = Template(Path(template_path).read_text(encoding="utf-8"))
    return tmpl.render(**category)


def _call_llm(model: str, prompt: str, temperature: float, max_tokens: int) -> str:
    litellm = _require_litellm()
    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp["choices"][0]["message"]["content"]


def _parse_json_strict(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        # Try to extract the first JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _make_stub_case(category: Dict[str, Any], idx: int) -> Dict[str, Any]:
    case_id = f"VCFCST-{category['level3_id']}-{idx:03d}"
    return {
        "case_id": case_id,
        "vcfcst_category": {
            "level1": category["level1"],
            "level2": category["level2"],
            "level3_id": category["level3_id"],
            "level3_name": category["level3_name"],
            "defect_desc": category["defect_desc"],
        },
        "difficulty": random.choice(["Easy", "Medium", "Hard"]),
        "case_type": random.choice(["implement", "modify"]),
        "requirement": "写一个简单函数并通过测试用例。",
        "initial_code": {"src/main.py": "def main():\n    return 42\n"},
        "acceptance_criteria": {
            "test_code": {
                "tests/test_main.py": "from src.main import main\n\ndef test_main():\n    assert main() == 42\n"
            },
            "static_check_rules": [],
            "pass_condition": "pytest 通过率100%",
        },
        "expected_defect": category["defect_desc"],
        "env_config": {
            "base_image": "python:3.10-slim",
            "dependencies": ["pytest==8.0.0"],
            "expose_port": [],
            "network_disabled": True,
        },
    }


def main():
    ap = argparse.ArgumentParser(description="Generate VC-FCST cases with LLM")
    ap.add_argument("--categories", default="benchmark/categories_top50.json", help="Categories json")
    ap.add_argument("--template", default="benchmark/prompts/case_prompt_template.md", help="Prompt template")
    ap.add_argument("--per-category", type=int, default=1, help="Cases per category")
    ap.add_argument("--model", default="gpt-4o-mini", help="LLM model")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--out-jsonl", default="datasets/case_bank.jsonl")
    ap.add_argument("--out-parquet", default="datasets/case_bank.parquet")
    ap.add_argument("--dry-run", action="store_true", help="Generate stub cases without LLM")
    ap.add_argument("--max-retries", type=int, default=3)
    args = ap.parse_args()

    schema = load_schema()
    categories = _load_categories(args.categories)
    out_jsonl = Path(args.out_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    cases: List[Dict[str, Any]] = []
    with out_jsonl.open("w", encoding="utf-8") as f:
        for cat in categories:
            for i in range(1, args.per_category + 1):
                if args.dry_run:
                    case = _make_stub_case(cat, i)
                    cases.append(case)
                    f.write(json.dumps(case, ensure_ascii=False) + "\n")
                    continue

                prompt = _render_prompt(args.template, cat)
                last_err = ""
                case = None
                for _ in range(args.max_retries):
                    try:
                        text = _call_llm(args.model, prompt, args.temperature, args.max_tokens)
                        case = _parse_json_strict(text)
                        errs = validate_case(case, schema)
                        if not errs:
                            break
                        last_err = "; ".join(errs)
                        case = None
                    except Exception as exc:
                        last_err = str(exc)
                        case = None
                    time.sleep(0.5)
                if case is None:
                    raise SystemExit(f"failed to generate case for {cat['level3_id']}: {last_err}")
                cases.append(case)
                f.write(json.dumps(case, ensure_ascii=False) + "\n")

    try:
        import pandas as pd  # type: ignore

        df = pd.DataFrame(cases)
        Path(args.out_parquet).parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(args.out_parquet, index=False)
    except Exception as exc:
        raise SystemExit("pandas/pyarrow required for parquet output") from exc


if __name__ == "__main__":
    raise SystemExit(main())
