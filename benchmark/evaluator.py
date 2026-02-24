#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def run_command(cmd: List[str], cwd: str, stdout_path: Path, stderr_path: Path, timeout: int = 600) -> int:
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.run(cmd, cwd=cwd, stdout=out, stderr=err, timeout=timeout)
        return proc.returncode


def run_pytest(cwd: str, stdout_path: Path, stderr_path: Path) -> Tuple[int, int]:
    code = run_command([sys.executable, "-m", "pytest", "-q"], cwd, stdout_path, stderr_path)
    failed = 0
    try:
        text = stderr_path.read_text(encoding="utf-8")
        m = re.search(r"=+\s+(\d+) failed", text)
        if m:
            failed = int(m.group(1))
    except Exception:
        failed = 0
    return code, failed


def run_semgrep(cwd: str, rules: List[str], stdout_path: Path, stderr_path: Path) -> Tuple[int, int]:
    if not rules:
        return 0, 0
    rules_path = Path(cwd) / ".semgrep_rules.json"
    rules_path.write_text("\n".join(rules), encoding="utf-8")
    code = run_command(["semgrep", "--config", str(rules_path), "--json"], cwd, stdout_path, stderr_path)
    findings = 0
    try:
        import json

        data = json.loads(stdout_path.read_text(encoding="utf-8"))
        findings = len(data.get("results", []))
    except Exception:
        findings = 0
    return code, findings


def evaluate_pass_condition(pass_condition: str, pytest_code: int, semgrep_findings: int) -> bool:
    cond = pass_condition.lower()
    ok = True
    if "pytest" in cond:
        ok = ok and (pytest_code == 0)
    if "semgrep" in cond or "高危" in cond or "static" in cond:
        ok = ok and (semgrep_findings == 0)
    return ok
