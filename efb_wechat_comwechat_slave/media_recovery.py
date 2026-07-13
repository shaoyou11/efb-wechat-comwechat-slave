from typing import Optional


HISTORICAL_MEDIA_AGE_SECONDS = 10 * 60
HISTORICAL_MEDIA_WAIT_SECONDS = 10
NORMAL_MEDIA_WAIT_SECONDS = 120


def is_historical_media(
    original_timestamp: Optional[int],
    started_at: int,
) -> bool:
    if not original_timestamp:
        return False
    return started_at - int(original_timestamp) > HISTORICAL_MEDIA_AGE_SECONDS


def media_wait_timeout(historical: bool) -> int:
    if historical:
        return HISTORICAL_MEDIA_WAIT_SECONDS
    return NORMAL_MEDIA_WAIT_SECONDS
