#!/usr/bin/env python3
import argparse
import json
import subprocess
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from adapter_llm import adapt_input_with_llm, load_adapter, parse_output_with_llm, render_input
from case_bank import filter_cases, load_case_bank
from evaluator import evaluate_pass_condition, run_pytest, run_semgrep


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_files(base: Path, files: Dict[str, str]) -> None:
    for rel_path, content in files.items():
        path = base / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _collect_final_code(base: Path) -> Dict[str, str]:
    final_code: Dict[str, str] = {}
    for path in base.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            rel = str(path.relative_to(base))
            try:
                final_code[rel] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Skip binary or non-utf8 artifacts produced during execution.
                continue
    return final_code


def _changed_files(initial: Dict[str, str], final: Dict[str, str]) -> List[str]:
    changed = []
    for path, content in final.items():
        if initial.get(path) != content:
            changed.append(path)
    return sorted(changed)


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


def _run_agent(agent_cmd: List[str], prompt: str, cwd: str, stdout_path: Path, stderr_path: Path, timeout: int) -> int:
    proc = subprocess.run(
        agent_cmd,
        input=prompt,
        text=True,
        cwd=cwd,
        stdout=stdout_path.open("w", encoding="utf-8"),
        stderr=stderr_path.open("w", encoding="utf-8"),
        timeout=timeout,
    )
    return proc.returncode


def _run_in_docker(image: str, workspace: Path, cmd: str, stdout_path: Path, stderr_path: Path, timeout: int) -> int:
    try:
        import docker  # type: ignore

        client = docker.from_env()
        with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
            container = client.containers.run(
                image=image,
                command=["/bin/bash", "-lc", cmd],
                working_dir="/workspace",
                volumes={str(workspace): {"bind": "/workspace", "mode": "rw"}},
                network_disabled=True,
                mem_limit="2g",
                nano_cpus=1_000_000_000,
                detach=True,
            )
            try:
                result = container.wait(timeout=timeout)
                logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="ignore")
                out.write(logs)
                return int(result.get("StatusCode", 1))
            finally:
                container.remove(force=True)
    except Exception:
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{workspace}:/workspace",
            "-w",
            "/workspace",
            "--network",
            "none",
            "--cpus",
            "1",
            "--memory",
            "2g",
            image,
            "/bin/bash",
            "-lc",
            cmd,
        ]
        proc = subprocess.run(
            docker_cmd,
            stdout=stdout_path.open("w", encoding="utf-8"),
            stderr=stderr_path.open("w", encoding="utf-8"),
            timeout=timeout,
        )
        return proc.returncode


def _ensure_requirements(workspace: Path, deps: List[str]) -> None:
    req_path = workspace / "requirements.txt"
    existing = ""
    if req_path.exists():
        existing = req_path.read_text(encoding="utf-8")
    merged = existing.strip().splitlines() if existing.strip() else []
    for dep in deps:
        if dep not in merged:
            merged.append(dep)
    if merged:
        req_path.write_text("\n".join(merged) + "\n", encoding="utf-8")


def _write_rules(workspace: Path, rules: List[str]) -> Path:
    rules_path = workspace / "semgrep_rules.txt"
    rules_path.write_text("\n".join(rules), encoding="utf-8")
    return rules_path


def main():
    ap = argparse.ArgumentParser(description="VC-FCST Benchmark Orchestrator (MVP)")
    ap.add_argument("--case-bank", required=True, help="Case bank parquet path")
    ap.add_argument("--agent-config", required=True, help="Agent adapter config yaml")
    ap.add_argument("--agent-cmd", nargs="+", default=[], help="Agent command (CLI mode)")
    ap.add_argument("--out", default="runs/benchmark_results.parquet", help="Result parquet")
    ap.add_argument("--run-dir", default="runs", help="Run artifacts root")
    ap.add_argument("--category-id", default="", help="Filter by category id")
    ap.add_argument("--difficulty", default="", help="Filter by difficulty")
    ap.add_argument("--case-id", action="append", default=[], help="Filter by case id")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of cases")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--use-docker", action="store_true", help="Run tests in Docker")
    ap.add_argument("--llm-adapt-input", action="store_true")
    ap.add_argument("--llm-parse-output", action="store_true")
    ap.add_argument("--llm-model", default="")
    args = ap.parse_args()

    adapter = load_adapter(args.agent_config)
    if not args.agent_cmd:
        cmd = (adapter.get("call_config") or {}).get("cmd", "")
        if cmd:
            args.agent_cmd = cmd.split()
    if not args.agent_cmd:
        raise SystemExit("agent command is required (use --agent-cmd or set call_config.cmd)")
    repo_root = Path(__file__).resolve().parents[1]
    resolved_cmd = []
    for part in args.agent_cmd:
        if not os.path.isabs(part):
            candidate = repo_root / part
            if candidate.exists():
                resolved_cmd.append(str(candidate))
                continue
        resolved_cmd.append(part)
    args.agent_cmd = resolved_cmd
    df = load_case_bank(args.case_bank)
    df = filter_cases(df, args.category_id, args.difficulty, args.case_id or None)
    if args.limit > 0:
        df = df.head(args.limit)

    run_root = Path(args.run_dir)
    run_root.mkdir(parents=True, exist_ok=True)
    batch_dir = run_root / f"benchmark-{time.strftime('%Y%m%d-%H%M%S')}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        case = row.to_dict()
        case_id = case["case_id"]
        case_dir = batch_dir / case_id
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        _write_files(workspace, case["initial_code"])
        _write_files(workspace, case["acceptance_criteria"]["test_code"])
        _ensure_requirements(workspace, case["env_config"]["dependencies"])

        started_at = _utc_now()
        t0 = time.time()

        agent_stdout = case_dir / "agent.stdout.log"
        agent_stderr = case_dir / "agent.stderr.log"
        prompt = render_input(adapter, case)
        if args.llm_adapt_input:
            prompt = adapt_input_with_llm(adapter, prompt, model=args.llm_model)
        agent_code = _run_agent(args.agent_cmd, prompt, str(workspace), agent_stdout, agent_stderr, args.timeout)

        final_code = _collect_final_code(workspace)
        changed_files = _changed_files(case["initial_code"], final_code)
        parse_result = {}
        if args.llm_parse_output:
            try:
                parse_result = parse_output_with_llm(
                    adapter,
                    agent_stdout.read_text(encoding="utf-8"),
                    final_code,
                    args.llm_model,
                )
            except Exception:
                parse_result = {}

        pytest_stdout = case_dir / "pytest.stdout.log"
        pytest_stderr = case_dir / "pytest.stderr.log"
        semgrep_stdout = case_dir / "semgrep.stdout.log"
        semgrep_stderr = case_dir / "semgrep.stderr.log"

        pytest_code = 1
        pytest_failed = None
        semgrep_code = None
        semgrep_findings = None

        if args.use_docker:
            image = case["env_config"]["base_image"]
            install = "pip install -r requirements.txt"
            pytest_cmd = f"{install} && pytest -q"
            pytest_code = _run_in_docker(image, workspace, pytest_cmd, pytest_stdout, pytest_stderr, args.timeout)
            pytest_failed = None
            rules = _listify(case["acceptance_criteria"].get("static_check_rules"))
            if len(rules) > 0:
                _write_rules(workspace, rules)
                semgrep_cmd = f"{install} && pip install semgrep && semgrep --config semgrep_rules.txt --json"
                semgrep_code = _run_in_docker(image, workspace, semgrep_cmd, semgrep_stdout, semgrep_stderr, args.timeout)
                semgrep_findings = 0
        else:
            pytest_code, pytest_failed = run_pytest(str(workspace), pytest_stdout, pytest_stderr)
            rules = _listify(case["acceptance_criteria"].get("static_check_rules"))
            if len(rules) > 0:
                semgrep_code, semgrep_findings = run_semgrep(str(workspace), rules, semgrep_stdout, semgrep_stderr)

        passed = evaluate_pass_condition(
            case["acceptance_criteria"]["pass_condition"],
            pytest_code,
            semgrep_findings or 0,
        )

        ended_at = _utc_now()
        duration = time.time() - t0

        result = {
            "case_id": case_id,
            "agent_name": adapter.get("agent_name", "unknown"),
            "agent_version": adapter.get("agent_version", ""),
            "category_id": case["vcfcst_category"]["level3_id"],
            "difficulty": case["difficulty"],
            "case_type": case["case_type"],
            "passed": bool(passed),
            "has_expected_defect": parse_result.get("has_expected_defect"),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_sec": round(duration, 3),
            "metrics": {
                "pytest_exit_code": pytest_code,
                "pytest_failed": pytest_failed,
                "semgrep_exit_code": semgrep_code,
                "semgrep_findings": semgrep_findings,
            },
            "artifacts": {
                "run_dir": str(case_dir),
                "workspace_dir": str(workspace),
                "agent_stdout": str(agent_stdout),
                "agent_stderr": str(agent_stderr),
                "tests_stdout": str(pytest_stdout),
                "tests_stderr": str(pytest_stderr),
            },
            "agent_return_code": agent_code,
            "changed_files": changed_files,
            "code_change_summary": parse_result.get("code_change_summary", ""),
            "failure_reason": parse_result.get("failure_reason", ""),
        }
        results.append(result)

    try:
        import pandas as pd  # type: ignore

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results).to_parquet(out_path, index=False)
    except Exception as exc:
        raise SystemExit("pandas/pyarrow required for parquet output") from exc


if __name__ == "__main__":
    raise SystemExit(main())
