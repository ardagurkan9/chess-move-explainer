from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.repositories.interfaces import ProgressSummary
from src.services.progress_service import ProgressService


def empty_summary() -> ProgressSummary:
    return ProgressSummary(
        total_games=0,
        total_analyzed_moves=0,
        total_mistakes=0,
        mistake_counts=(),
        pending_positions=0,
        learning_positions=0,
        mastered_positions=0,
        due_positions=0,
        total_practice_attempts=0,
        correct_practice_attempts=0,
        success_rate=None,
        recent_success_rate=None,
        previous_success_rate=None,
        success_rate_change=None,
        next_review_at=None,
    )


def test_progress_service_scopes_summary_to_its_user() -> None:
    repository = MagicMock()
    repository.progress_summary.return_value = empty_summary()
    service = ProgressService(repository, username=" student ")
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)

    assert service.summary(now=now) == empty_summary()
    repository.progress_summary.assert_called_once_with(
        username="student", as_of=now
    )


def test_progress_service_rejects_empty_username() -> None:
    with pytest.raises(ValueError, match="Username"):
        ProgressService(MagicMock(), username="  ")
