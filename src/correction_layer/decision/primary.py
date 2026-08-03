from correction_layer.model.types import PrimaryJudgment, PrimaryLabel

__all__ = ["judge_primary"]


def judge_primary(max_similarity: float, threshold: float) -> PrimaryJudgment:
    anomaly_score = 1.0 - max_similarity
    label = (
        PrimaryLabel.POSITIVE if anomaly_score > threshold else PrimaryLabel.NEGATIVE
    )
    return PrimaryJudgment(
        label=label,
        anomaly_score=anomaly_score,
        threshold=threshold,
    )
