---
name: trajectory-result-evaluation
description: Audit both execution trajectory and generated report correctness (process + result).
compatibility: opencode
metadata:
  reference: .opencode/skills/trajectory-result-evaluation/reference/报告结果审计规则.md
---

# Skill: trajectory-result-evaluation

## Overview

Use this skill when you need dual audit coverage:

1. Process audit: verify trace flow `preprocess -> whitelist -> analyze -> report`.
2. Result audit: verify the generated `report.md` is consistent with `analyze-messages.json`.

This skill does not modify existing skills. It runs alongside `trajectory-evaluation`.

## Reference (must read)

- Primary reference: `.opencode/skills/trajectory-result-evaluation/reference/报告结果审计规则.md`
- Process-audit base: `.opencode/skills/trajectory-evaluation/reference/项目运行流程总览.md`

## When to Use

- after pipeline execution, when you need to check both process and report output
- when report quality must be auditable (summary/top10/low-quality consistency)
- when you need a single combined score for go/no-go

## Workflow (must follow)

1. Recommended one-shot command:

```bash
python ".opencode/skills/trajectory-result-evaluation/scripts/run_pipeline_and_full_audit.py"
```

2. The runner will:

- execute existing pipeline + process audit via `trajectory-evaluation`
- run report-result auditor on `output/test-run/report.md`
- run combined auditor and produce a final markdown report

3. Manual mode:

```bash
python ".opencode/skills/trajectory-result-evaluation/scripts/audit_report_result.py"
python ".opencode/skills/trajectory-result-evaluation/scripts/audit_full.py"
```

## Output

- Result-audit JSON: stdout from `audit_report_result.py`
- Result-audit markdown: `.opencode/traces/latest_result_audit_report.md`
- Full-audit JSON: stdout from `audit_full.py`
- Full-audit markdown: `.opencode/traces/latest_full_audit_report.md`

## Optional Plugin

- `.opencode/plugins/report-artifact-logger.ts` logs report artifact hash events.
- If enabled/loaded, result audit can verify report integrity via hash match.

## Config (optional)

- `TRAJECTORY_RESULT_REPORT_MD` (default `output/test-run/report.md`)
- `TRAJECTORY_RESULT_ANALYSIS_JSON` (default `output/test-run/analyze-messages.json`)
- `TRAJECTORY_RESULT_ARTIFACT_TRACE` (default `.opencode/traces/report_artifacts.latest.jsonl`)
- `TRAJECTORY_RESULT_AUDIT_MD` (default `.opencode/traces/latest_result_audit_report.md`)
- `TRAJECTORY_FULL_AUDIT_MD` (default `.opencode/traces/latest_full_audit_report.md`)
- `TRAJECTORY_FULL_AUDIT_W_PROCESS` (default `0.60`)
- `TRAJECTORY_FULL_AUDIT_W_RESULT` (default `0.40`)
