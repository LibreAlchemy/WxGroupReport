#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def default_prompt(input_path: str, output_dir: str) -> str:
    return (
        "请在当前仓库直接执行完整流程，按顺序完成并修复运行中的小错误，最后只输出 DONE 和产物路径。"
        f"要求：1) 输入数据固定为 {input_path}，输出目录固定 {output_dir}。"
        "2) 运行 .opencode/skills/import-chat-data/scripts/preprocessor.py。"
        "3) 使用 .opencode/skills/import-chat-data/reference/whitelist.md 对 "
        f"{output_dir}/members/*.json 做白名单标记，命中写入 isWhitelist: true（wxid优先，昵称兜底）。"
        f"4) 生成 {output_dir}/analyze-messages.json，包含 success/data/memberScores/highlights/lowQualityMembers。"
        "5) 运行 .opencode/skills/generate-report/scripts/generate_report.py "
        f"生成 {output_dir}/report.md。不要省略任何步骤。"
    )


def safe_remove(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def load_nonempty_lines(path: Path) -> List[str]:
    lines: List[str] = []
    if not path.exists():
        return lines

    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            lines.append(line)
    return lines


def trim_trace_to_run_window(trace_path: Path, start_offset: int) -> Tuple[int, int]:
    lines = load_nonempty_lines(trace_path)
    before_count = len(lines)

    if start_offset <= 0:
        return before_count, before_count

    kept = lines[start_offset:] if start_offset < before_count else []
    trace_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return before_count, len(kept)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[4]

    input_path = os.getenv("TRAJECTORY_INPUT_PATH", "docs/测试/data/麦田怪圈.json")
    output_dir = os.getenv("TRAJECTORY_OUTPUT_DIR", "output/test-run")
    trace_path = Path(
        os.getenv("TRAJECTORY_TRACE_PATH", ".opencode/traces/latest.jsonl")
    )
    report_path = Path(
        os.getenv("TRAJECTORY_REPORT_PATH", ".opencode/traces/latest_audit_report.md")
    )
    should_clean = env_bool("TRAJECTORY_CLEAN", True)

    abs_trace_path = (repo_root / trace_path).resolve()
    abs_report_path = (repo_root / report_path).resolve()
    abs_output_dir = (repo_root / output_dir).resolve()

    trace_start_offset = 0
    if not should_clean:
        trace_start_offset = len(load_nonempty_lines(abs_trace_path))

    if should_clean:
        safe_remove(abs_output_dir)
        safe_remove(abs_trace_path)
        safe_remove(abs_report_path)

    prompt = os.getenv("TRAJECTORY_RUN_PROMPT") or default_prompt(
        input_path, output_dir
    )

    run_cmd = ["opencode", "run", prompt]
    run_result = subprocess.run(run_cmd, cwd=repo_root)
    if run_result.returncode != 0:
        return run_result.returncode

    if not abs_trace_path.exists() or abs_trace_path.stat().st_size == 0:
        print(
            '{"error":{"code":"TRACE_NOT_FOUND","message":"trace file not generated after opencode run"}}'
        )
        return 2

    filter_run_trace = env_bool(
        "TRAJECTORY_FILTER_RUN_TRACE",
        env_bool("TRAJECTORY_FILTER_BUSINESS_TRACE", True),
    )
    if filter_run_trace:
        before_count, after_count = trim_trace_to_run_window(
            abs_trace_path, trace_start_offset
        )
        print(
            json.dumps(
                {
                    "trace_filter": {
                        "mode": "run_window",
                        "events_before": before_count,
                        "events_after": after_count,
                    }
                },
                ensure_ascii=False,
            )
        )

    audit_script = repo_root / ".opencode/skills/trajectory-evaluation/scripts/audit.py"
    audit_cmd = [
        sys.executable,
        str(audit_script),
        str(trace_path),
        f"--report={report_path}",
    ]
    audit_result = subprocess.run(audit_cmd, cwd=repo_root)
    return audit_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
