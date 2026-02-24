# VC-FCST Benchmark MVP

VC-FCST Benchmark 是基于 VC-FCST 失效分类体系的 Code Agent 评测基准。
MVP 聚焦三项交付物：
- Case Bank（可复现、可校验的测试用例库）
- Simple Orchestrator（单 Case 自动执行与客观验收）
- Leaderboard（Streamlit + Plotly 可视化榜单）

## 目录结构
- `benchmark/`：MVP 核心代码（用例生成、编排器、评估、排行榜）
- `datasets/`：Case Bank 数据（jsonl/parquet）与数据集说明
- `docs/`：VC-FCST 分类体系与技术方案
- `runs/`：跑批结果与日志（已被 gitignore）

## 已实现内容
- Case Bank 工具链：Schema 校验、JSONL/Parquet 读写、字段归一化
- DeepSeek 生成：Top50 每类 1 条（共 50 条）
- Orchestrator MVP：调用 Agent、收集代码、运行 pytest、写入结果 parquet
- Codex CLI（podman 容器运行）：`benchmark/run_codex_podman.sh`
- Streamlit 排行榜：总榜 + 顶层雷达 + 分类柱状图 + Case 明细

## 使用方法
生成示例用例（不调用 LLM）：
```bash
.venv/bin/python benchmark/generate_cases.py --per-category 1 --dry-run \
  --out-jsonl datasets/case_bank.jsonl --out-parquet datasets/case_bank.parquet
```

校验用例：
```bash
.venv/bin/python benchmark/validate_cases.py --input datasets/case_bank.jsonl
```

生成 Top50（DeepSeek，每类 1 条）：
```bash
.venv/bin/python benchmark/generate_top50_one_each.py \
  --out-jsonl datasets/case_bank.jsonl
```

跑基准（Codex + podman，5 条）：
```bash
.venv/bin/python benchmark/orchestrator.py \
  --case-bank datasets/case_bank.jsonl \
  --agent-config benchmark/adapters/codex_podman.yaml \
  --limit 5
```

启动排行榜：
```bash
.venv/bin/streamlit run benchmark/leaderboard.py
```

## DeepSeek 配置
LLM 适配通过 `.env` 配置（`benchmark/deepseek_client.py`）：
- `API_KEY`
- `API_BASE`（默认 `https://api.deepseek.com`）
- `MODEL_NAME`（默认 `deepseek-reasoner`）

## 未实现内容（对齐 `docs/tech_design_zh.md` 的缺口）
- Case Bank 规模：2500 条、难度/类型分布、基准 Agent 过滤、10% 人工抽检
- 测试全容器隔离：pytest/semgrep 仍在宿主机执行
- Docker SDK 的单 Case 生命周期 + 网络禁用
- LiteLLM 统一适配（目前是 DeepSeek 客制 client）
- 失败重试与更严格的 pass_condition 解析
- 排行榜导出与更多指标（缺陷逃逸率、Token 成本、PDF/Excel）

## 设计文档
详细技术方案见 `docs/tech_design_zh.md`。
