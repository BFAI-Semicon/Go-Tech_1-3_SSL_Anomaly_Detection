from correction_layer.model.records import (
    Action,
    CorrectionRecord,
    Method,
    ScoreReweightParams,
    ThresholdAdaptParams,
)
from correction_layer.model.types import PrimaryJudgment, PrimaryLabel

__all__ = ["apply_correction"]


def apply_correction(
    record: CorrectionRecord, primary: PrimaryJudgment
) -> PrimaryLabel:
    if record.action is Action.REVIEW_REQUIRED:
        raise ValueError("ReviewRequired must be handled by resolution")
    if record.action is Action.KEEP_PRIMARY:
        return primary.label
    if record.method is Method.LABEL_OVERRIDE:
        if record.action is Action.OVERRIDE_NEGATIVE:
            return PrimaryLabel.NEGATIVE
        return PrimaryLabel.POSITIVE
    if record.method is Method.SCORE_REWEIGHT:
        if not isinstance(record.params, ScoreReweightParams):
            raise ValueError("ScoreReweight requires ScoreReweightParams")
        score = primary.anomaly_score * record.params.weight
        return (
            PrimaryLabel.POSITIVE
            if score > primary.threshold
            else PrimaryLabel.NEGATIVE
        )
    if record.method is Method.THRESHOLD_ADAPT:
        if not isinstance(record.params, ThresholdAdaptParams):
            raise ValueError("ThresholdAdapt requires ThresholdAdaptParams")
        adapted = primary.threshold + record.params.threshold_delta
        return (
            PrimaryLabel.POSITIVE
            if primary.anomaly_score > adapted
            else PrimaryLabel.NEGATIVE
        )
    raise ValueError(f"unsupported method: {record.method!r}")
