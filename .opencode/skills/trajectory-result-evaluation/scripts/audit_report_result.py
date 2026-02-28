#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional, Tuple


DEFAULT_REPORT_MD = Path("output/test-run/report.md")
DEFAULT_ANALYSIS_JSON = Path("output/test-run/analyze-messages.json")
DEFAULT_ARTIFACT_TRACE = Path(".opencode/traces/report_artifacts.latest.jsonl")
DEFAULT_RESULT_AUDIT_MD = Path(".opencode/traces/latest_result_audit_report.md")


@dataclass
class WeightedMetric:
    key: str
    label: str
    weight: float


METRIC_WEIGHTS: List[WeightedMetric] = [
    WeightedMetric("structure", "结构完整性", 0.15),
    WeightedMetric("summary_consistency", "数据概览一致性", 0.35),
    WeightedMetric("top10_consistency", "Top10一致性", 0.20),
    WeightedMetric("low_quality_consistency", "低质成员一致性", 0.20),
    WeightedMetric("artifact_integrity", "报告哈希一致性", 0.10),
]


def env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw) if raw else default


def safe_text(value: object) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def table_safe(value: object) -> str:
    return safe_text(value).replace("|", "\\|")


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"invalid json object: {path}")
    return data


def parse_summary_counts(report_md: str) -> Tuple[Dict[str, Optional[int]], List[str]]:
    mapping = {
        "total_members": "总成员数",
        "active_members": "活跃成员数",
        "low_quality_count": "低质成员数",
        "highlights_count": "精彩内容数",
    }
    values: Dict[str, Optional[int]] = {key: None for key in mapping}
    reasons: List[str] = []

    for key, label in mapping.items():
        pattern = rf"^\|\s*{re.escape(label)}\s*\|\s*(\d+)\s*\|\s*$"
        match = re.search(pattern, report_md, flags=re.MULTILINE)
        if match:
            values[key] = int(match.group(1))
        else:
            reasons.append(f"missing summary row: {label}")

    return values, reasons


def parse_top10_rows(report_md: str) -> List[dict]:
    rows: List[dict] = []
    row_re = re.compile(
        r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(\d+)\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|\s*$"
    )
    for line in report_md.splitlines():
        m = row_re.match(line.strip())
        if not m:
            continue
        rank = int(m.group(1))
        if rank < 1 or rank > 10:
            continue
        rows.append(
            {
                "rank": rank,
                "name": m.group(2),
                "messageCount": int(m.group(3)),
                "averageScore": float(m.group(4)),
            }
        )
    rows.sort(key=lambda x: x["rank"])
    return rows


def parse_low_quality_names(report_md: str) -> List[str]:
    names: List[str] = []
    for line in report_md.splitlines():
        m = re.match(r"^###\s+\d+\.\s+(.+?)\s*$", line.strip())
        if m:
            names.append(m.group(1))
    return names


def expected_from_analysis(analysis: dict) -> Tuple[dict, List[dict], List[str]]:
    data = analysis.get("data")
    if not isinstance(data, dict):
        raise ValueError("analysis.data missing")

    member_scores = data.get("memberScores")
    highlights = data.get("highlights")
    low_quality_members = data.get("lowQualityMembers")

    if not isinstance(member_scores, list):
        raise ValueError("analysis.data.memberScores missing")
    if not isinstance(highlights, list):
        raise ValueError("analysis.data.highlights missing")
    if not isinstance(low_quality_members, list):
        raise ValueError("analysis.data.lowQualityMembers missing")

    summary = {
        "total_members": len(member_scores),
        "active_members": len(
            [
                m
                for m in member_scores
                if isinstance(m, dict) and m.get("messageCount", 0) > 0
            ]
        ),
        "low_quality_count": len(low_quality_members),
        "highlights_count": len(highlights),
    }

    sorted_members = sorted(
        [m for m in member_scores if isinstance(m, dict)],
        key=lambda m: m.get("messageCount", 0),
        reverse=True,
    )
    top10: List[dict] = []
    for idx, m in enumerate(sorted_members[:10], start=1):
        top10.append(
            {
                "rank": idx,
                "name": table_safe(m.get("nickname") or m.get("wxid") or ""),
                "messageCount": int(m.get("messageCount", 0) or 0),
                "averageScore": round(float(m.get("averageScore", 0.0) or 0.0), 1),
            }
        )

    low_names: List[str] = []
    for m in low_quality_members:
        if not isinstance(m, dict):
            continue
        low_names.append(safe_text(m.get("nickname") or m.get("wxid") or ""))

    return summary, top10, low_names


def metric_structure(report_md: str) -> Tuple[dict, List[str], List[str]]:
    required = [
        "## 数据概览",
        "## 活跃度排行榜 (Top10)",
        "## 本期精彩内容",
        "## 低质成员名单",
    ]
    found = [h for h in required if h in report_md]
    missing = [h for h in required if h not in report_md]
    score = (len(found) / len(required)) * 100.0
    reasons = [f"required_sections={len(found)}/{len(required)}"]
    if missing:
        reasons.append("missing: " + ", ".join(missing))
    violations = [f"missing section: {h}" for h in missing]
    return (
        {
            "required": len(required),
            "found": len(found),
            "score": round(score, 2),
        },
        reasons,
        violations,
    )


def metric_summary_consistency(
    report_md: str, expected: dict
) -> Tuple[dict, List[str], List[str]]:
    actual, parse_reasons = parse_summary_counts(report_md)
    mismatches: List[str] = []
    matched = 0
    total = len(expected)

    for key, exp_value in expected.items():
        act_value = actual.get(key)
        if act_value is None:
            continue
        if act_value == exp_value:
            matched += 1
        else:
            mismatches.append(f"{key}: expected={exp_value}, actual={act_value}")

    score = (matched / total) * 100.0 if total else 100.0
    reasons = [f"summary_fields_matched={matched}/{total}"] + parse_reasons
    reasons.extend(mismatches[:10])
    violations = [f"summary mismatch: {item}" for item in mismatches]
    violations.extend([f"summary parse issue: {item}" for item in parse_reasons])
    return (
        {
            "matched": matched,
            "total": total,
            "score": round(score, 2),
        },
        reasons,
        violations,
    )


def metric_top10_consistency(
    report_md: str, expected_top10: List[dict]
) -> Tuple[dict, List[str], List[str]]:
    actual_rows = parse_top10_rows(report_md)
    expected_count = len(expected_top10)
    compare_count = min(len(actual_rows), expected_count)
    mismatches: List[str] = []
    matched = 0

    for i in range(compare_count):
        exp = expected_top10[i]
        act = actual_rows[i]
        name_ok = act["name"] == exp["name"]
        msg_ok = act["messageCount"] == exp["messageCount"]
        avg_ok = abs(act["averageScore"] - exp["averageScore"]) <= 0.05
        if name_ok and msg_ok and avg_ok:
            matched += 1
        else:
            mismatches.append(
                f"rank={exp['rank']}, expected=({exp['name']}, {exp['messageCount']}, {exp['averageScore']:.1f}), actual=({act['name']}, {act['messageCount']}, {act['averageScore']:.1f})"
            )

    count_penalty = abs(len(actual_rows) - expected_count)
    score_base = (matched / max(1, expected_count)) * 100.0
    score = max(0.0, score_base - (count_penalty * 10.0))

    reasons = [
        f"top10_rows_actual={len(actual_rows)}",
        f"top10_rows_expected={expected_count}",
        f"top10_rows_matched={matched}/{max(1, expected_count)}",
    ]
    if mismatches:
        reasons.extend(mismatches[:10])

    violations: List[str] = []
    if len(actual_rows) != expected_count:
        violations.append(
            f"top10 row count mismatch: expected={expected_count}, actual={len(actual_rows)}"
        )
    violations.extend([f"top10 mismatch: {item}" for item in mismatches])

    return (
        {
            "expected_rows": expected_count,
            "actual_rows": len(actual_rows),
            "matched_rows": matched,
            "score": round(score, 2),
        },
        reasons,
        violations,
    )


def metric_low_quality_consistency(
    report_md: str, expected_names: List[str]
) -> Tuple[dict, List[str], List[str]]:
    actual_names = parse_low_quality_names(report_md)
    if "- 本期无低质成员" in report_md and not actual_names:
        actual_names = []

    expected_count = len(expected_names)
    actual_count = len(actual_names)
    compare_count = min(expected_count, actual_count)
    matched = 0
    name_mismatches: List[str] = []

    for i in range(compare_count):
        if actual_names[i] == expected_names[i]:
            matched += 1
        else:
            name_mismatches.append(
                f"index={i + 1}, expected={expected_names[i]}, actual={actual_names[i]}"
            )

    count_penalty = abs(expected_count - actual_count)
    score_base = (matched / max(1, expected_count)) * 100.0
    score = max(0.0, score_base - min(60.0, count_penalty * 3.0))

    reasons = [
        f"low_quality_expected={expected_count}",
        f"low_quality_actual={actual_count}",
        f"low_quality_order_matched={matched}/{max(1, expected_count)}",
    ]
    if name_mismatches:
        reasons.extend(name_mismatches[:10])

    violations: List[str] = []
    if expected_count != actual_count:
        violations.append(
            f"low-quality count mismatch: expected={expected_count}, actual={actual_count}"
        )
    violations.extend(
        [f"low-quality name mismatch: {item}" for item in name_mismatches]
    )

    return (
        {
            "expected_count": expected_count,
            "actual_count": actual_count,
            "matched_order_prefix": matched,
            "score": round(score, 2),
        },
        reasons,
        violations,
    )


def load_latest_artifact_hash(
    artifact_trace: Path, report_path: Path
) -> Tuple[Optional[str], List[str]]:
    reasons: List[str] = []
    if not artifact_trace.exists():
        reasons.append("artifact trace not found; integrity check downgraded")
        return None, reasons

    target_abs = str(report_path.resolve())
    latest_hash: Optional[str] = None
    parse_errors = 0

    with artifact_trace.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if not isinstance(item, dict):
                continue
            path_value = item.get("report_path")
            hash_value = item.get("sha256")
            if not isinstance(path_value, str) or not isinstance(hash_value, str):
                continue
            path_candidates = {path_value, str((Path(path_value)).resolve())}
            if target_abs in path_candidates or str(report_path) in path_candidates:
                latest_hash = hash_value

    if parse_errors:
        reasons.append(f"artifact trace parse_errors={parse_errors}")
    if latest_hash is None:
        reasons.append("no matching artifact hash found for report path")
    return latest_hash, reasons


def metric_artifact_integrity(
    report_path: Path, artifact_trace: Path
) -> Tuple[dict, List[str], List[str]]:
    reasons: List[str] = []
    violations: List[str] = []

    if not report_path.exists():
        return (
            {
                "mode": "artifact_hash",
                "checked": False,
                "score": 0.0,
            },
            ["report file missing"],
            [f"report file not found: {report_path}"],
        )

    actual_hash = sha256_file(report_path)
    expected_hash, extra_reasons = load_latest_artifact_hash(
        artifact_trace, report_path
    )
    reasons.extend(extra_reasons)
    reasons.append(f"report_sha256={actual_hash}")

    if expected_hash is None:
        # Optional metric: no hard failure when plugin trace is unavailable.
        return (
            {
                "mode": "artifact_hash",
                "checked": False,
                "score": 70.0,
            },
            reasons,
            violations,
        )

    reasons.append(f"artifact_sha256={expected_hash}")
    if expected_hash == actual_hash:
        score = 100.0
    else:
        score = 0.0
        violations.append("artifact hash mismatch with plugin trace")

    return (
        {
            "mode": "artifact_hash",
            "checked": True,
            "score": score,
        },
        reasons,
        violations,
    )


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def build_markdown_report(report: dict) -> str:
    lines: List[str] = []
    lines.append("# 报告结果审计报告")
    lines.append("")
    lines.append(f"- report_file: `{report['report_file']}`")
    lines.append(f"- analysis_file: `{report['analysis_file']}`")
    lines.append(f"- total_score: {report['score']}/100")
    lines.append(f"- passed: {str(report['passed']).lower()}")
    lines.append("")

    lines.append("## 分项评分")
    for item in METRIC_WEIGHTS:
        metric = report["metrics"][item.key]
        lines.append(f"- {item.label}: {metric['score']} (weight={item.weight:.2f})")
        for reason in report["reasons"][item.key]:
            lines.append(f"  - 原因: {reason}")
    lines.append("")

    lines.append("## 违规")
    if report["violations"]:
        for violation in report["violations"]:
            lines.append(f"- {violation}")
    else:
        lines.append("- 无")

    return "\n".join(lines) + "\n"


def parse_args(argv: List[str]) -> Tuple[Path, Path, Path, Path]:
    report_file = env_path("TRAJECTORY_RESULT_REPORT_MD", DEFAULT_REPORT_MD)
    analysis_file = env_path("TRAJECTORY_RESULT_ANALYSIS_JSON", DEFAULT_ANALYSIS_JSON)
    artifact_trace = env_path(
        "TRAJECTORY_RESULT_ARTIFACT_TRACE", DEFAULT_ARTIFACT_TRACE
    )
    audit_md = env_path("TRAJECTORY_RESULT_AUDIT_MD", DEFAULT_RESULT_AUDIT_MD)

    i = 0
    while i < len(argv):
        arg = argv[i]
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
            audit_md = Path(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--out="):
            audit_md = Path(arg.split("=", 1)[1])
            i += 1
            continue
        i += 1

    return report_file, analysis_file, artifact_trace, audit_md


def evaluate(
    report_file: Path, analysis_file: Path, artifact_trace: Path, audit_md: Path
) -> Tuple[dict, int]:
    if not report_file.exists():
        return {
            "error": {
                "code": "REPORT_NOT_FOUND",
                "message": f"report file not found: {report_file}",
            },
            "report_file": str(report_file),
        }, 2
    if not analysis_file.exists():
        return {
            "error": {
                "code": "ANALYSIS_NOT_FOUND",
                "message": f"analysis file not found: {analysis_file}",
            },
            "analysis_file": str(analysis_file),
        }, 2

    report_md = report_file.read_text(encoding="utf-8")
    analysis = load_json(analysis_file)
    expected_summary, expected_top10, expected_low_names = expected_from_analysis(
        analysis
    )

    metrics: Dict[str, dict] = {}
    reasons: Dict[str, List[str]] = {}
    violations: List[str] = []

    structure_metric, structure_reasons, structure_violations = metric_structure(
        report_md
    )
    metrics["structure"] = structure_metric
    reasons["structure"] = structure_reasons
    violations.extend(structure_violations)

    summary_metric, summary_reasons, summary_violations = metric_summary_consistency(
        report_md, expected_summary
    )
    metrics["summary_consistency"] = summary_metric
    reasons["summary_consistency"] = summary_reasons
    violations.extend(summary_violations)

    top10_metric, top10_reasons, top10_violations = metric_top10_consistency(
        report_md, expected_top10
    )
    metrics["top10_consistency"] = top10_metric
    reasons["top10_consistency"] = top10_reasons
    violations.extend(top10_violations)

    low_metric, low_reasons, low_violations = metric_low_quality_consistency(
        report_md, expected_low_names
    )
    metrics["low_quality_consistency"] = low_metric
    reasons["low_quality_consistency"] = low_reasons
    violations.extend(low_violations)

    artifact_metric, artifact_reasons, artifact_violations = metric_artifact_integrity(
        report_file, artifact_trace
    )
    metrics["artifact_integrity"] = artifact_metric
    reasons["artifact_integrity"] = artifact_reasons
    violations.extend(artifact_violations)

    weighted_score = 0.0
    for item in METRIC_WEIGHTS:
        score = float(metrics[item.key].get("score", 0.0))
        weighted_score += item.weight * clamp_score(score)

    unique_violations = list(dict.fromkeys(violations))
    passed = len(unique_violations) == 0

    payload = {
        "report_file": str(report_file),
        "analysis_file": str(analysis_file),
        "artifact_trace_file": str(artifact_trace),
        "result_audit_report": str(audit_md),
        "score": round(clamp_score(weighted_score), 2),
        "max_score": 100,
        "passed": passed,
        "violations": unique_violations,
        "metrics": metrics,
        "reasons": reasons,
    }

    audit_md.parent.mkdir(parents=True, exist_ok=True)
    audit_md.write_text(build_markdown_report(payload), encoding="utf-8")
    return payload, 0 if passed else 1


def main() -> int:
    report_file, analysis_file, artifact_trace, audit_md = parse_args(sys.argv[1:])
    report, code = evaluate(report_file, analysis_file, artifact_trace, audit_md)
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
