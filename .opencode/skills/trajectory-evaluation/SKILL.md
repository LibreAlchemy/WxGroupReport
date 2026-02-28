---
name: trajectory-evaluation
description: Audit trajectory logs against the required end-to-end flow (preprocess -> whitelist -> analyze -> report).
compatibility: opencode
metadata:
  reference: .opencode/skills/trajectory-evaluation/reference/项目运行流程总览.md
---

# Skill: trajectory-evaluation

## Overview

Use this skill to first generate a fresh trace via plugin (through `opencode run`), then audit `.opencode/traces/latest.jsonl` against the skill-local SOP reference: `.opencode/skills/trajectory-evaluation/reference/项目运行流程总览.md`.

## Reference (must read)

- Primary reference: `.opencode/skills/trajectory-evaluation/reference/项目运行流程总览.md`
- Upstream source (for manual sync if needed): `docs/测试/document/项目运行流程总览.md`

## When to Use

- after finishing a data-processing/report pipeline run
- when you need a compliance score and concrete violations
- when you want to verify the hard ordering rule for key scripts

## Workflow (must follow)

1. Run the one-shot runner (recommended):

```bash
python ".opencode/skills/trajectory-evaluation/scripts/run_pipeline_and_audit.py"
```

2. The runner will:

- clean previous `output/test-run` + trace files (default)
- call `opencode run` to execute preprocess -> whitelist -> analyze -> report
- rely on `.opencode/plugins/trajectory-logger.ts` to generate `.opencode/traces/latest.jsonl`
- invoke `audit.py` and produce JSON + markdown report

3. (Manual mode) If you already have a fresh trace, run the auditor directly:

```bash
python ".opencode/skills/trajectory-evaluation/scripts/audit.py"
```

4. Read JSON score, metrics, and reasons.
5. Read markdown report at `.opencode/traces/latest_audit_report.md`.
6. If violations exist, fix the run order and rerun.

## Hard Rules

- `preprocessor.py` must appear before `generate_report.py`.
- Flow order must be: preprocess -> whitelist -> analyze -> report.
- Missing stages are counted as violations.

## Output

- JSON string to stdout
- keys: `trace_file`, `events_loaded`, `score`, `max_score`, `stage_detection`, `violations`, `passed`
- on missing trace file: JSON error with `error.code=TRACE_NOT_FOUND`
- markdown report file with reasons: `.opencode/traces/latest_audit_report.md`

## Scoring Model

- Efficiency Metrics:
  - step count (penalize if > baseline x 150%)
  - token consumption (prefer lower)
  - redundancy rate (duplicate tool call ratio)
- Compliance Metrics:
  - key action coverage
  - sequence adherence
  - forbidden action limit
- Tool Usage Quality:
  - tool success rate
  - argument accuracy
- Total Score formula:
  - `Score = (W1 x 结果正确性) + (W2 x SOP依从度) - (W3 x 步骤惩罚)`

Config via env (optional):

- `TRAJECTORY_BASELINE_STEPS` (default `10`)
- `TRAJECTORY_BASELINE_TOKENS` (default `8000`)
- `TRAJECTORY_WEIGHT_W1` (default `0.50`)
- `TRAJECTORY_WEIGHT_W2` (default `0.50`)
- `TRAJECTORY_WEIGHT_W3` (default `0.20`)
- `TRAJECTORY_INPUT_PATH` (runner input path, default `docs/测试/data/麦田怪圈.json`)
- `TRAJECTORY_OUTPUT_DIR` (runner output dir, default `output/test-run`)
- `TRAJECTORY_TRACE_PATH` (default `.opencode/traces/latest.jsonl`)
- `TRAJECTORY_REPORT_PATH` (default `.opencode/traces/latest_audit_report.md`)
- `TRAJECTORY_CLEAN` (default `true`)
- `TRAJECTORY_RUN_PROMPT` (custom opencode run prompt)

## Optional Input

You can pass a custom trace path:

```bash
python ".opencode/skills/trajectory-evaluation/scripts/audit.py" ".opencode/traces/latest.jsonl"
```
