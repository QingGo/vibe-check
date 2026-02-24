# VC-FCST Benchmark MVP

This folder implements the MVP benchmark pipeline described in `docs/tech_design_zh.md`.

## Files
- `case_schema.json`: Case schema v0.1
- `result_schema.json`: Result schema v0.1
- `categories_top50.json`: Top 50 categories for MVP case bank
- `prompts/case_prompt_template.md`: LLM prompt template for case generation
- `adapters/*.yaml`: Agent adapter templates
- `generate_cases.py`: Batch case generator (LLM-based)
- `validate_cases.py`: Case schema validator
- `orchestrator.py`: Benchmark orchestrator
- `leaderboard.py`: Streamlit leaderboard

## Quickstart
Generate stub cases (no LLM):
```bash
python benchmark/generate_cases.py --per-category 1 --dry-run \
  --out-jsonl datasets/case_bank.jsonl --out-parquet datasets/case_bank.parquet
```

Validate cases:
```bash
python benchmark/validate_cases.py --input datasets/case_bank.parquet
```

Run benchmark (CLI agent):
```bash
python benchmark/orchestrator.py \
  --case-bank datasets/case_bank.parquet \
  --agent-config benchmark/adapters/aider.yaml \
  --agent-cmd python runner/agent_echo.py \
  --limit 3
```

Run benchmark with real agents (CLI):
```bash
python benchmark/orchestrator.py \
  --case-bank datasets/case_bank.parquet \
  --agent-config benchmark/adapters/codex.yaml \
  --llm-adapt-input --llm-parse-output \
  --limit 3
```

```bash
python benchmark/orchestrator.py \
  --case-bank datasets/case_bank.parquet \
  --agent-config benchmark/adapters/gemini_cli.yaml \
  --llm-adapt-input --llm-parse-output \
  --limit 3
```

```bash
python benchmark/orchestrator.py \
  --case-bank datasets/case_bank.parquet \
  --agent-config benchmark/adapters/claude_code.yaml \
  --llm-adapt-input --llm-parse-output \
  --limit 3
```

Launch leaderboard:
```bash
streamlit run benchmark/leaderboard.py -- \
  --results runs/benchmark_results.parquet \
  --case-bank datasets/case_bank.parquet
```

## DeepSeek LLM config
The LLM adapter uses `.env` via `runner/deepseek_client.py`. Required keys:
- `API_KEY`
- `API_BASE` (default `https://api.deepseek.com`)
- `MODEL_NAME` (default `deepseek-reasoner`)
