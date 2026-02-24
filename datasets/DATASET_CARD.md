---
license: mit
tags:
  - vc-fcst
  - benchmark
  - testing
  - case-bank
---

# VC-FCST Benchmark Case Bank

This dataset contains schema-validated test cases for VC-FCST Benchmark MVP.

## Fields
- `case_id`: unique case id
- `vcfcst_category`: category metadata (level1/level2/level3)
- `difficulty`: Easy | Medium | Hard
- `case_type`: implement | modify
- `requirement`: natural language requirement for the agent
- `initial_code`: initial repository snapshot (path -> content)
- `acceptance_criteria`: tests + static rules + pass condition
- `expected_defect`: expected failure signature
- `env_config`: base image, dependencies, network policy
