#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any, Dict


def _require_yaml():
    try:
        import yaml  # type: ignore

        return yaml
    except Exception as exc:
        raise SystemExit("PyYAML is required: pip install pyyaml") from exc


def _require_jinja():
    try:
        from jinja2 import Environment  # type: ignore

        return Environment
    except Exception as exc:
        raise SystemExit("jinja2 is required: pip install jinja2") from exc


def _require_deepseek():
    try:
        bench_dir = Path(__file__).resolve().parent
        if str(bench_dir) not in sys.path:
            sys.path.insert(0, str(bench_dir))
        from deepseek_client import chat_complete  # type: ignore

        return chat_complete
    except Exception as exc:
        raise SystemExit("deepseek client is required: check benchmark/deepseek_client.py") from exc


def load_adapter(path: str) -> Dict[str, Any]:
    yaml = _require_yaml()
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def _env_with_filters():
    Environment = _require_jinja()
    env = Environment(autoescape=False)
    env.filters["to_json"] = lambda v: json.dumps(v, ensure_ascii=False)
    return env


def render_input(adapter: Dict[str, Any], case: Dict[str, Any]) -> str:
    env = _env_with_filters()
    tmpl = env.from_string(adapter.get("input_prompt_template", ""))
    return tmpl.render(case=case)


def adapt_input_with_llm(adapter: Dict[str, Any], rendered_input: str, model: str = "") -> str:
    chat_complete = _require_deepseek()
    system = adapter.get(
        "input_llm_instruction",
        "You are a protocol adapter. Output the final agent input only, no extra text.",
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": rendered_input},
    ]
    text = chat_complete(messages, model=model or None, temperature=0.2, max_tokens=2048)
    if not (text or "").strip():
        return rendered_input
    return text


def parse_output_with_llm(
    adapter: Dict[str, Any], agent_raw_output: str, final_code: Dict[str, str], model: str = ""
) -> Dict[str, Any]:
    env = _env_with_filters()
    chat_complete = _require_deepseek()
    tmpl = env.from_string(adapter.get("output_parse_template", ""))
    prompt = tmpl.render(agent_raw_output=agent_raw_output, final_code=json.dumps(final_code, ensure_ascii=False))
    text = chat_complete(
        [{"role": "user", "content": prompt}],
        model=model or None,
        temperature=0,
        max_tokens=800,
    )
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise
