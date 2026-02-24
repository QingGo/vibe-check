#!/usr/bin/env python3
import json
import os
import urllib.request
from pathlib import Path


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _load_dotenv(path=ENV_PATH):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("\"")
        if key and key not in os.environ:
            os.environ[key] = val


def _env(key, default=""):
    return os.environ.get(key, default)


def chat_complete(messages, model=None, temperature=0.2, max_tokens=2048):
    _load_dotenv()
    api_key = _env("API_KEY")
    api_base = _env("API_BASE", "https://api.deepseek.com")
    model_name = model or _env("MODEL_NAME", "deepseek-reasoner")

    if not api_key:
        raise RuntimeError("API_KEY is not set")

    url = api_base.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    result = json.loads(body)
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("no choices returned")
    return choices[0].get("message", {}).get("content", "")
