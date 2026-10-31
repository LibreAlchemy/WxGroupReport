from typing import Literal

from pydantic import BaseModel, Field, field_validator

from highlight_url_repair import (
    canonicalize_highlight_from_message,
    sanitize_url,
)
from message_context import safe_text


HIGHLIGHT_TYPES = ("news", "article", "github", "insight", "opportunity")
EVIDENCE_KINDS = ("topic", "claim", "resource", "interaction")

QUALITY_WEIGHTS = {
    "informationDensity": 0.35,
    "originality": 0.25,
    "resourceValue": 0.20,
    "interactionValue": 0.10,
    "continuity": 0.10,
}
CALIBRATION_RAW_WEIGHT = 0.70
CALIBRATION_COHORT_WEIGHT = 0.30


class Highlight(BaseModel):
    type: Literal["news", "article", "github", "insight", "opportunity"]
    content: str = Field(min_length=1, max_length=300)
    url: str = ""
    messageId: str = ""

    @field_validator("content", "url", "messageId", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return safe_text(value)


class Evidence(BaseModel):
    messageId: str
    topic: str = Field(default="", max_length=100)
    kind: Literal["topic", "claim", "resource", "interaction"] = "claim"

    @field_validator("messageId", "topic", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return safe_text(value)


class Dimensions(BaseModel):
    informationDensity: float = Field(ge=0, le=100)
    originality: float = Field(ge=0, le=100)
    resourceValue: float = Field(ge=0, le=100)
    interactionValue: float = Field(ge=0, le=100)


class AnalysisResult(BaseModel):
    summary: str = Field(min_length=10, max_length=160)
    dimensions: Dimensions
    evidence: list[Evidence] = Field(default_factory=list, max_length=12)
    highlights: list[Highlight] = Field(default_factory=list, max_length=10)

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value):
        return safe_text(value)


def _normalize_dimensions(payload: dict) -> dict:
    raw = payload.get("dimensions")
    if not isinstance(raw, dict):
        legacy_score = int(payload.get("score", 50))
        return {
            "informationDensity": legacy_score,
            "originality": legacy_score,
            "resourceValue": legacy_score,
            "interactionValue": legacy_score,
        }
    values = {
        "informationDensity": raw.get(
            "informationDensity", raw.get("information_density", 0)
        ),
        "originality": raw.get("originality", 0),
        "resourceValue": raw.get("resourceValue", raw.get("resource_value", 0)),
        "interactionValue": raw.get(
            "interactionValue", raw.get("interaction_value", 0)
        ),
    }
    return {
        key: min(100.0, max(0.0, float(value or 0)))
        for key, value in values.items()
    }


def normalize_analysis_payload(payload: dict) -> AnalysisResult:
    evidence = []
    for item in (payload.get("evidence") or [])[:12]:
        if not isinstance(item, dict):
            continue
        kind = safe_text(item.get("kind", "claim")).lower()
        if kind not in EVIDENCE_KINDS:
            kind = "claim"
        evidence.append(
            {
                "messageId": item.get("messageId", item.get("message_id", "")),
                "topic": item.get("topic", ""),
                "kind": kind,
            }
        )

    highlights = []
    for item in (payload.get("highlights") or [])[:10]:
        if not isinstance(item, dict):
            continue
        highlight_type = safe_text(item.get("type")).lower()
        if highlight_type == "resource":
            highlight_type = "article" if safe_text(item.get("url")) else "insight"
        if highlight_type not in HIGHLIGHT_TYPES:
            highlight_type = "insight"
        content = safe_text(item.get("content"))[:300]
        if not content:
            continue
        highlights.append(
            {
                "type": highlight_type,
                "content": content,
                "url": item.get("url", ""),
                "messageId": item.get("messageId", item.get("message_id", "")),
            }
        )

    summary = safe_text(payload.get("summary", ""))[:160]
    if len(summary) < 10:
        summary = "成员在统计周期内的有效发言总结。"
    return AnalysisResult.model_validate(
        {
            "summary": summary,
            "dimensions": _normalize_dimensions(payload),
            "evidence": evidence,
            "highlights": highlights,
        }
    )


def filter_valid_evidence(
    evidence: list[Evidence], allowed_ids: set[str]
) -> list[dict]:
    result = []
    seen = set()
    for item in evidence:
        message_id = item.messageId
        key = (message_id, item.topic, item.kind)
        if message_id not in allowed_ids or key in seen:
            continue
        seen.add(key)
        result.append(item.model_dump())
    return result


def repair_highlights_with_sources(
    highlights: list[Highlight],
    own_messages: list[dict],
    context_messages: list[dict],
) -> list[dict]:
    own_ids = {safe_text(message.get("id")) for message in own_messages}
    messages_by_id = {
        safe_text(message.get("id")): message
        for message in [*own_messages, *context_messages]
        if safe_text(message.get("id"))
    }

    repaired = []
    seen = set()
    for item in highlights:
        normalized = item.model_dump()
        message_id = normalized["messageId"]
        if message_id not in own_ids:
            continue

        canonical = canonicalize_highlight_from_message(
            normalized, messages_by_id.get(message_id)
        )
        if not canonical:
            continue
        if canonical.get("url"):
            canonical["url"] = sanitize_url(canonical["url"])
            if not canonical["url"]:
                canonical.pop("url", None)

        key = (
            canonical["type"],
            canonical["messageId"],
            safe_text(canonical.get("content")).lower(),
            canonical.get("url", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        repaired.append(canonical)
        if len(repaired) >= 10:
            break
    return repaired


def aggregate_dimensions(chunks: list[dict]) -> dict[str, float]:
    total_weight = sum(max(1, int(chunk.get("own_count", 1))) for chunk in chunks)
    names = (
        "informationDensity",
        "originality",
        "resourceValue",
        "interactionValue",
    )
    return {
        name: round(
            sum(
                float(chunk["dimensions"][name])
                * max(1, int(chunk.get("own_count", 1)))
                for chunk in chunks
            )
            / total_weight,
            1,
        )
        for name in names
    }


def continuity_score(active_days: int, period_days: int) -> float:
    if period_days <= 0:
        return 0.0
    return round(min(100.0, active_days / period_days * 100.0), 1)


def raw_quality_score(dimensions: dict, continuity: float) -> float:
    values = {**dimensions, "continuity": continuity}
    return round(
        sum(float(values[name]) * weight for name, weight in QUALITY_WEIGHTS.items()),
        1,
    )


def confidence_for(substantive_count: int) -> str:
    if substantive_count < 5:
        return "low"
    if substantive_count < 20:
        return "medium"
    return "high"


def calibrate_member_scores(results: list[dict]) -> dict:
    eligible = [
        result
        for result in results
        if result.get("status") == "normal"
        and result.get("dimensions")
        and result.get("confidence") != "low"
    ]
    if len(eligible) < 3:
        for result in results:
            if result.get("rawScore") is not None:
                result["score"] = round(float(result["rawScore"]), 1)
            result["calibrated"] = False
        return {
            "applied": False,
            "eligibleMembers": len(eligible),
            "rawWeight": CALIBRATION_RAW_WEIGHT,
            "cohortWeight": CALIBRATION_COHORT_WEIGHT,
        }

    ordered = sorted(eligible, key=lambda item: float(item["rawScore"]))
    denominator = max(1, len(ordered) - 1)
    for rank, result in enumerate(ordered):
        percentile_score = rank / denominator * 100.0
        calibrated = (
            CALIBRATION_RAW_WEIGHT * float(result["rawScore"])
            + CALIBRATION_COHORT_WEIGHT * percentile_score
        )
        result["score"] = round(min(100.0, max(0.0, calibrated)), 1)
        result["calibrated"] = True

    eligible_ids = {result["wxid"] for result in eligible}
    for result in results:
        if result["wxid"] not in eligible_ids:
            if result.get("rawScore") is not None:
                result["score"] = round(float(result["rawScore"]), 1)
            result["calibrated"] = False

    return {
        "applied": True,
        "eligibleMembers": len(eligible),
        "rawWeight": CALIBRATION_RAW_WEIGHT,
        "cohortWeight": CALIBRATION_COHORT_WEIGHT,
    }
