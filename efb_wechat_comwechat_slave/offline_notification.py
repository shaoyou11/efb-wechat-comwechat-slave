class OfflineNotificationPolicy:
    """Decide when an offline status should trigger a notification."""

    def __init__(self, interval_seconds: int):
        self.interval_seconds = interval_seconds
        self.last_notification_at = None
        self.last_logged_in = None

    def observe_login_transition(self, logged_in: bool) -> bool:
        """Return once when an observed offline session becomes online."""
        return self.observe_session_transition(logged_in) == "login"

    def observe_session_transition(self, logged_in: bool):
        """Return ``login`` or ``logout`` once for an observed state change."""
        if self.last_logged_in is None:
            self.last_logged_in = logged_in
            return None
        transitioned = None
        if self.last_logged_in is False and logged_in:
            transitioned = "login"
        elif self.last_logged_in is True and not logged_in:
            transitioned = "logout"
        self.last_logged_in = logged_in
        return transitioned

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
