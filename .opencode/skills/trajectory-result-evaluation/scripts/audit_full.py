#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


DEFAULT_TRACE_FILE = Path(".opencode/traces/latest.jsonl")
DEFAULT_PROCESS_AUDIT_MD = Path(".opencode/traces/latest_audit_report.md")
DEFAULT_RESULT_AUDIT_MD = Path(".opencode/traces/latest_result_audit_report.md")
DEFAULT_FULL_AUDIT_MD = Path(".opencode/traces/latest_full_audit_report.md")

DEFAULT_REPORT_MD = Path("output/test-run/report.md")
DEFAULT_ANALYSIS_JSON = Path("output/test-run/analyze-messages.json")
DEFAULT_ARTIFACT_TRACE = Path(".opencode/traces/report_artifacts.latest.jsonl")


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def parse_json_from_output(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("no json payload found in command output")


def run_process_audit(trace_file: Path, process_audit_md: Path) -> Tuple[dict, int]:
    script = Path(".opencode/skills/trajectory-evaluation/scripts/audit.py")
    cmd = [sys.executable, str(script), str(trace_file), f"--report={process_audit_md}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    payload = parse_json_from_output(proc.stdout)
    return payload, proc.returncode


def run_result_audit(
    report_md: Path,
    analysis_json: Path,
    artifact_trace: Path,
    result_audit_md: Path,
) -> Tuple[dict, int]:
    script = Path(
        ".opencode/skills/trajectory-result-evaluation/scripts/audit_report_result.py"
    )
    cmd = [
        sys.executable,
        str(script),
        f"--report={report_md}",
        f"--analysis={analysis_json}",
        f"--artifact-trace={artifact_trace}",
        f"--out={result_audit_md}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    payload = parse_json_from_output(proc.stdout)
    return payload, proc.returncode


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def build_markdown(report: dict) -> str:
    process = report["process_audit"]
    result = report["result_audit"]
    formula = report["formula"]

    lines: List[str] = []
    lines.append("# 全链路审计报告（过程 + 结果）")
    lines.append("")
    lines.append(f"- trace_file: `{report['trace_file']}`")
    lines.append(f"- report_file: `{report['report_file']}`")
    lines.append(f"- analysis_file: `{report['analysis_file']}`")
    lines.append(f"- total_score: {report['score']}/100")
    lines.append(f"- passed: {str(report['passed']).lower()}")
    lines.append("")

    lines.append("## 过程审计")
    lines.append(f"- score: {process.get('score')}")
    lines.append(f"- passed: {str(process.get('passed')).lower()}")
    lines.append(f"- violations: {len(process.get('violations', []))}")
    lines.append("")

    lines.append("## 结果审计")
    lines.append(f"- score: {result.get('score')}")
    lines.append(f"- passed: {str(result.get('passed')).lower()}")
    lines.append(f"- violations: {len(result.get('violations', []))}")
    lines.append("")

    lines.append("## 组合公式")
    lines.append(
        f"`FullScore = ({formula['w_process']} * ProcessScore) + ({formula['w_result']} * ResultScore)`"
    )
    lines.append(f"- process_score: {formula['process_score']}")
    lines.append(f"- result_score: {formula['result_score']}")
    lines.append(f"- full_score: {formula['full_score']}")
    lines.append("")

    lines.append("## 违规")
    if report["violations"]:
        for item in report["violations"]:
            lines.append(f"- {item}")
    else:
        lines.append("- 无")

    return "\n".join(lines) + "\n"


def evaluate(
    trace_file: Path,
    report_file: Path,
    analysis_file: Path,
    artifact_trace: Path,
    process_audit_md: Path,
    result_audit_md: Path,
    full_audit_md: Path,
) -> Tuple[dict, int]:
    process_payload, process_code = run_process_audit(trace_file, process_audit_md)
    result_payload, result_code = run_result_audit(
        report_file, analysis_file, artifact_trace, result_audit_md
    )

    if "error" in process_payload:
        return process_payload, 2
    if "error" in result_payload:
        return result_payload, 2

    w_process = env_float("TRAJECTORY_FULL_AUDIT_W_PROCESS", 0.60)
    w_result = env_float("TRAJECTORY_FULL_AUDIT_W_RESULT", 0.40)
    total_w = w_process + w_result
    if total_w <= 0:
        w_process, w_result, total_w = 0.60, 0.40, 1.0

    process_score = float(process_payload.get("score", 0.0))
    result_score = float(result_payload.get("score", 0.0))
    full_score = clamp_score(
        (w_process / total_w) * process_score + (w_result / total_w) * result_score
    )

    violations: List[str] = []
    for item in process_payload.get("violations", []):
        violations.append(f"process: {item}")
    for item in result_payload.get("violations", []):
        violations.append(f"result: {item}")

    payload: Dict[str, object] = {
        "trace_file": str(trace_file),
        "report_file": str(report_file),
        "analysis_file": str(analysis_file),
        "process_audit_report": str(process_audit_md),
        "result_audit_report": str(result_audit_md),
        "full_audit_report": str(full_audit_md),
        "score": round(full_score, 2),
        "max_score": 100,
        "passed": bool(process_payload.get("passed"))
        and bool(result_payload.get("passed")),
        "violations": violations,
        "process_audit": {
            "score": process_score,
            "passed": process_payload.get("passed"),
            "violations": process_payload.get("violations", []),
        },
        "result_audit": {
            "score": result_score,
            "passed": result_payload.get("passed"),
            "violations": result_payload.get("violations", []),
        },
        "formula": {
            "name": "FullScore = (w_process * ProcessScore) + (w_result * ResultScore)",
            "w_process": round(w_process / total_w, 4),
            "w_result": round(w_result / total_w, 4),
            "process_score": round(process_score, 2),
            "result_score": round(result_score, 2),
            "full_score": round(full_score, 2),
        },
        "codes": {
            "process_exit_code": process_code,
            "result_exit_code": result_code,
        },
    }

    full_audit_md.parent.mkdir(parents=True, exist_ok=True)
    full_audit_md.write_text(build_markdown(payload), encoding="utf-8")

    return payload, 0 if payload["passed"] else 1


def parse_args(argv: List[str]) -> Tuple[Path, Path, Path, Path, Path, Path, Path]:
    trace_file = Path(os.getenv("TRAJECTORY_TRACE_PATH", str(DEFAULT_TRACE_FILE)))
    report_file = Path(os.getenv("TRAJECTORY_RESULT_REPORT_MD", str(DEFAULT_REPORT_MD)))
    analysis_file = Path(
        os.getenv("TRAJECTORY_RESULT_ANALYSIS_JSON", str(DEFAULT_ANALYSIS_JSON))
    )
    artifact_trace = Path(
        os.getenv("TRAJECTORY_RESULT_ARTIFACT_TRACE", str(DEFAULT_ARTIFACT_TRACE))
    )
    process_audit_md = Path(
        os.getenv("TRAJECTORY_REPORT_PATH", str(DEFAULT_PROCESS_AUDIT_MD))
    )
    result_audit_md = Path(
        os.getenv("TRAJECTORY_RESULT_AUDIT_MD", str(DEFAULT_RESULT_AUDIT_MD))
    )
    full_audit_md = Path(
        os.getenv("TRAJECTORY_FULL_AUDIT_MD", str(DEFAULT_FULL_AUDIT_MD))
    )

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--trace" and i + 1 < len(argv):
            trace_file = Path(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--trace="):
            trace_file = Path(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--report" and i + 1 < len(argv):
            report_file = Path(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--report="):
            report_file = Path(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--analysis" and i + 1 < len(argv):
            analysis_file = Path(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--analysis="):
            analysis_file = Path(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--artifact-trace" and i + 1 < len(argv):
            artifact_trace = Path(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--artifact-trace="):
            artifact_trace = Path(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--out" and i + 1 < len(argv):
            full_audit_md = Path(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--out="):
            full_audit_md = Path(arg.split("=", 1)[1])
            i += 1
            continue
        i += 1

    return (
        trace_file,
        report_file,
        analysis_file,
        artifact_trace,
        process_audit_md,
        result_audit_md,
        full_audit_md,
    )


def main() -> int:
    (
        trace_file,
        report_file,
        analysis_file,
        artifact_trace,
        process_audit_md,
        result_audit_md,
        full_audit_md,
    ) = parse_args(sys.argv[1:])
    report, code = evaluate(
        trace_file,
        report_file,
        analysis_file,
        artifact_trace,
        process_audit_md,
        result_audit_md,
        full_audit_md,
    )
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
