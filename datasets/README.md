# Case Bank (MVP)

This folder stores VC-FCST Benchmark case bank artifacts.

## Files
- `case_bank.jsonl`: one-case-per-line JSON
- `case_bank.parquet`: columnar case bank for fast filtering
- `DATASET_CARD.md`: dataset description and fields

## Generate (stub)
```bash
python benchmark/generate_cases.py --per-category 1 --dry-run \
  --out-jsonl datasets/case_bank.jsonl --out-parquet datasets/case_bank.parquet
```

## Validate
```bash
python benchmark/validate_cases.py --input datasets/case_bank.parquet
```
