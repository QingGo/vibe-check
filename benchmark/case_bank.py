#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_pandas():
    try:
        import pandas as pd  # type: ignore

        return pd
    except Exception as exc:  # pragma: no cover
        raise SystemExit("pandas is required: pip install pandas pyarrow") from exc


def _validate_with_jsonschema(case: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    try:
        import jsonschema  # type: ignore
    except Exception:
        return _validate_minimal(case, schema)
    try:
        jsonschema.validate(instance=case, schema=schema)
        return []
    except Exception as exc:
        return [str(exc)]


def _validate_minimal(case: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for key in schema.get("required", []):
        if key not in case:
            errors.append(f"missing field: {key}")
    return errors


def load_schema(schema_path: str = "benchmark/case_schema.json") -> Dict[str, Any]:
    return _load_json(Path(schema_path))


def _drop_none_in_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_none_in_mapping(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none_in_mapping(v) for v in value]
    return value


def _listify(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if hasattr(value, "tolist"):
        try:
            return list(value.tolist())
        except Exception:
            return list(value)
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def normalize_case(case: Dict[str, Any]) -> Dict[str, Any]:
    case = dict(case)
    case["initial_code"] = _drop_none_in_mapping(case.get("initial_code") or {})
    acceptance = dict(case.get("acceptance_criteria") or {})
    acceptance["test_code"] = _drop_none_in_mapping(acceptance.get("test_code") or {})
    acceptance["static_check_rules"] = _listify(acceptance.get("static_check_rules"))
    case["acceptance_criteria"] = acceptance
    env = dict(case.get("env_config") or {})
    env["expose_port"] = _listify(env.get("expose_port"))
    env["dependencies"] = _listify(env.get("dependencies"))
    case["env_config"] = env
    return case


def validate_case(case: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> List[str]:
    if schema is None:
        schema = load_schema()
    case = normalize_case(case)
    return _validate_with_jsonschema(case, schema)


def load_case_bank(path: str):
    pd = _require_pandas()
    suffix = Path(path).suffix.lower()
    if suffix in {".jsonl", ".json"}:
        df = pd.read_json(path, lines=suffix == ".jsonl")
    else:
        df = pd.read_parquet(path)
    if "initial_code" in df.columns:
        df["initial_code"] = df["initial_code"].apply(lambda v: _drop_none_in_mapping(v or {}))
    if "acceptance_criteria" in df.columns:
        def _fix_acceptance(v):
            v = v or {}
            v["test_code"] = _drop_none_in_mapping(v.get("test_code") or {})
            v["static_check_rules"] = _listify(v.get("static_check_rules"))
            return v
        df["acceptance_criteria"] = df["acceptance_criteria"].apply(_fix_acceptance)
    return df


def save_case_bank(df, path: str) -> None:
    pd = _require_pandas()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def filter_cases(df, category_id: str = "", difficulty: str = "", case_ids: Optional[List[str]] = None):
    filtered = df
    if category_id:
        filtered = filtered[filtered["vcfcst_category"].apply(lambda c: c.get("level3_id") == category_id)]
    if difficulty:
        filtered = filtered[filtered["difficulty"] == difficulty]
    if case_ids:
        filtered = filtered[filtered["case_id"].isin(case_ids)]
    return filtered


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="VC-FCST case bank utilities")
    ap.add_argument("--input", required=True, help="Case bank parquet path")
    ap.add_argument("--category-id", default="", help="Filter by category id")
    ap.add_argument("--difficulty", default="", help="Filter by difficulty")
    ap.add_argument("--case-id", action="append", default=[], help="Filter by case id")
    ap.add_argument("--out", default="", help="Write filtered parquet")
    args = ap.parse_args()

    df = load_case_bank(args.input)
    df = filter_cases(df, args.category_id, args.difficulty, args.case_id or None)
    if args.out:
        save_case_bank(df, args.out)
    else:
        print(df.head())
