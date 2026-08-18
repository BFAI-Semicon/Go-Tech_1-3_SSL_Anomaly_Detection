from feature_extraction.model.features import ExtractorIdentity


class PrimaryDetectionError(Exception):
    pass


class NormalBankTooSmallError(PrimaryDetectionError):
    requested_k: int
    available_count: int

    def __init__(self, requested_k: int, available_count: int) -> None:
        self.requested_k = requested_k
        self.available_count = available_count
        super().__init__(requested_k, available_count)


class NormalFeatureCountInsufficientError(PrimaryDetectionError):
    feature_count: int
    embedding_dim: int

    def __init__(self, feature_count: int, embedding_dim: int) -> None:
        self.feature_count = feature_count
        self.embedding_dim = embedding_dim
        super().__init__(feature_count, embedding_dim)


class NormalReferenceIdentityMismatchError(PrimaryDetectionError):
    expected: ExtractorIdentity
    actual: ExtractorIdentity

    def __init__(self, expected: ExtractorIdentity, actual: ExtractorIdentity) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(expected, actual)
