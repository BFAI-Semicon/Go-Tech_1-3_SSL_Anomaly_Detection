from datetime import UTC, datetime

from patch_feature_store.model.ports import Clock


def utc_clock() -> Clock:
    return UtcClock()


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
