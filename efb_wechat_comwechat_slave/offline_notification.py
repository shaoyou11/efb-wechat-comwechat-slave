class OfflineNotificationPolicy:
    """Decide when an offline status should trigger a notification."""

    def __init__(self, interval_seconds: int):
        self.interval_seconds = interval_seconds
        self.last_notification_at = None

    def observe(self, logged_in: bool, now: float) -> bool:
        if logged_in:
            self.last_notification_at = None
            return False

        if (
            self.last_notification_at is None
            or now - self.last_notification_at >= self.interval_seconds
        ):
            self.last_notification_at = now
            return True

        return False
