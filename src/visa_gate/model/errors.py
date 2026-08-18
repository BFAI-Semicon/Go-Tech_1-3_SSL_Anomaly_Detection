from pathlib import Path


class VisaGateError(Exception):
    pass


class DatasetRootMissingError(VisaGateError):
    path: Path

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(path)


class DatasetNotPreparedError(VisaGateError):
    path: Path
    category: str

    def __init__(self, path: Path, category: str) -> None:
        self.path = path
        self.category = category
        super().__init__(path, category)


class DatasetLocationNotWritableError(VisaGateError):
    path: Path

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(path)
