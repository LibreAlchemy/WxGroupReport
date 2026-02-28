#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[4]

    run_pipeline_script = (
        repo_root
        / ".opencode/skills/trajectory-evaluation/scripts/run_pipeline_and_audit.py"
    )
    run_full_audit_script = (
        repo_root
        / ".opencode/skills/trajectory-result-evaluation/scripts/audit_full.py"
    )

    pipeline = subprocess.run([sys.executable, str(run_pipeline_script)], cwd=repo_root)
    if pipeline.returncode not in {0, 1}:
        return pipeline.returncode

    full = subprocess.run([sys.executable, str(run_full_audit_script)], cwd=repo_root)
    return full.returncode


if __name__ == "__main__":
    raise SystemExit(main())
