##根据作答证据更新知识点掌握度，并计算推荐优先级
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
# 手动定义 UTC（兼容 Python 3.10 及以下）
UTC = timezone.utc

##练习证据条目：某个知识点上的一次作答。
##字段1 normalized_score：归一化得分[0,1]；字段2 evidence_weight：该作答对这一知识点的证据强度。
Evidence = tuple[float, float]


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def recompute_mastery_from_evidence(
    evidence: Iterable[Evidence],
) -> tuple[float, float, int]:
    """按时间顺序把一列作答证据确定性折叠成 (mastery, confidence, attempts_count)。

    与 record_attempt 的增量更新同构：只要传入相同顺序的证据，
    折叠结果就 == 增量结果的推导值，因此掌握度可以幂等地从证据重放，
    申诉改判后不必在历史状态上打补丁，直接按新证据整体重算。
    """
    mastery = 0.0
    attempts_count = 0
    for normalized_score, evidence_weight in evidence:
        mastery = update_mastery(
            mastery,
            normalized_score,
            evidence_weight,
        )
        attempts_count += 1
    return (
        mastery,
        mastery_confidence(attempts_count),
        attempts_count,
    )


def _as_utc_datetime(value: Any) -> datetime | None:
    """把 None / datetime / ISO 字符串统一成 aware datetime，便于遗忘曲线计算。"""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):  # ISO 8601 的 Z 是 UTC 简写，datetime 解析需展开
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    return value


def update_mastery(
    old_mastery: float,
    normalized_score: float,
    evidence_weight: float,
    alpha: float = 0.25,
) -> float:
    effective_alpha = max(
        0.05,
        min(alpha * clamp(evidence_weight), 0.4),
    )
    result = clamp(old_mastery) + effective_alpha * (
        clamp(normalized_score) - clamp(old_mastery)
    )
    return round(clamp(result), 6)


def mastery_confidence(attempts_count: int) -> float:
    value = 1.0 - math.exp(-max(0, attempts_count) / 5.0)
    return round(clamp(value), 6)


def forgetting_risk(
    last_practiced_at: datetime | str | None,
    half_life_days: float = 14.0,
) -> float:
    last_practiced_at = _as_utc_datetime(last_practiced_at)
    if last_practiced_at is None:
        return 1.0

    if last_practiced_at.tzinfo is None:
        last_practiced_at = last_practiced_at.replace(tzinfo=UTC)

    elapsed_days = max(
        0.0,
        (datetime.now(UTC) - last_practiced_at).total_seconds() / 86_400,
    )
    retention = math.pow(0.5, elapsed_days / max(half_life_days, 0.1))
    return round(clamp(1.0 - retention), 6)


@dataclass(frozen=True, slots=True)
class RecommendationFactors:
    mastery: float
    confidence: float
    forgetting_risk: float
    prerequisite_readiness: float
    learner_preference: float = 0.5

    def score(self) -> float:
        result = (
            0.40 * (1.0 - clamp(self.mastery))
            + 0.20 * clamp(self.confidence)
            + 0.20 * clamp(self.forgetting_risk)
            + 0.15 * clamp(self.prerequisite_readiness)
            + 0.05 * clamp(self.learner_preference)
        )
        return round(clamp(result), 6)