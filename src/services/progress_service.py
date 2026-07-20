"""Application service for personal progress reporting."""

from datetime import datetime, timezone

from src.repositories.interfaces import GameHistoryRepository, ProgressSummary


class ProgressService:
    """Load one user's persisted coaching summary."""

    def __init__(self, repository: GameHistoryRepository, *, username: str) -> None:
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("Username cannot be empty.")
        self.repository = repository
        self.username = clean_username

    def summary(self, *, now: datetime | None = None) -> ProgressSummary:
        """Return progress as of the supplied time or the current UTC time."""
        return self.repository.progress_summary(
            username=self.username,
            as_of=now or datetime.now(timezone.utc),
        )
