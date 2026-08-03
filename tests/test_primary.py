from correction_layer.decision.primary import judge_primary
from correction_layer.model.types import PrimaryJudgment, PrimaryLabel


def test_should_return_positive_when_anomaly_score_exceeds_threshold():
    max_similarity = 0.7
    threshold = 0.2
    expected_score = 1.0 - max_similarity

    judgment = judge_primary(max_similarity, threshold)

    assert isinstance(judgment, PrimaryJudgment)
    assert expected_score > threshold
    assert judgment.label == PrimaryLabel.POSITIVE
    assert judgment.anomaly_score == expected_score
    assert judgment.threshold == threshold


def test_should_return_negative_when_anomaly_score_is_below_threshold():
    max_similarity = 0.9
    threshold = 0.2
    expected_score = 1.0 - max_similarity

    judgment = judge_primary(max_similarity, threshold)

    assert expected_score < threshold
    assert judgment.label == PrimaryLabel.NEGATIVE
    assert judgment.anomaly_score == expected_score
    assert judgment.threshold == threshold


def test_should_return_negative_when_anomaly_score_equals_threshold():
    max_similarity = 0.8
    threshold = 1.0 - max_similarity

    judgment = judge_primary(max_similarity, threshold)

    assert judgment.anomaly_score == threshold
    assert judgment.label == PrimaryLabel.NEGATIVE
    assert judgment.threshold == threshold
