class OfflineNotificationPolicy:
    """Decide when an offline status should trigger a notification."""

    def __init__(self, interval_seconds: int):
        self.interval_seconds = interval_seconds
        self.last_notification_at = None
        self.last_logged_in = None
        self.last_recovery_logged_in = None

    def observe_login_transition(self, logged_in: bool) -> bool:
        """Return once when an observed offline session becomes online."""
        transitioned = self.last_logged_in is False and logged_in
        self.last_logged_in = logged_in
        return transitioned

    def observe_recovery_event(self, logged_in: bool) -> bool:
        """Return once for a new offline episode, not reminder intervals."""
        is_new_episode = (
            not logged_in and self.last_recovery_logged_in is not False
        )
        self.last_recovery_logged_in = logged_in
        return is_new_episode

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
