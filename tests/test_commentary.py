import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.commentary import (
    CommentaryService,
    GeminiCommentary,
    GeminiCommentaryError,
    TemplateCommentary,
    create_commentary_service,
)
from src.models import (
    EngineResult,
    MoveAnalysis,
    MoveClassification,
    MoveQuality,
    UserLevel,
)


def move_analysis(
    *,
    played_move: str = "f2f3",
    best_move: str = "e2e4",
    loss: int | None = 153,
    missed_mate: bool = False,
    allowed_mate: bool = False,
) -> MoveAnalysis:
    before = EngineResult(best_move, 69, None, (best_move, "e7e5"), 12)
    after = EngineResult("e7e5", -84, None, ("e7e5",), 12)
    return MoveAnalysis(
        played_move=played_move,
        player_is_white=True,
        fen_before="before",
        fen_after="after",
        before=before,
        after=after,
        centipawn_loss=loss,
        missed_forced_mate=missed_mate,
        allowed_forced_mate=allowed_mate,
    )


def classification(
    quality: MoveQuality = MoveQuality.MISTAKE, loss: int | None = 153
) -> MoveClassification:
    return MoveClassification(quality, "test reason", loss)


@pytest.mark.parametrize("level", list(UserLevel))
def test_explanation_is_grounded_in_analysis_for_every_level(
    level: UserLevel,
) -> None:
    result = TemplateCommentary().generate(
        move_analysis(), classification(), level=level
    )

    assert result.source == "template"
    assert result.level is level
    assert "f2f3" in result.text
    assert "e2e4" in result.text
    assert "153 centipawns" in result.text


def test_intermediate_explanation_includes_evaluation_change() -> None:
    result = TemplateCommentary().generate(
        move_analysis(), classification(), level=UserLevel.INTERMEDIATE
    )

    assert "+0.69" in result.text
    assert "-0.84" in result.text


def test_advanced_explanation_includes_depth_and_pv() -> None:
    result = TemplateCommentary().generate(
        move_analysis(), classification(), level=UserLevel.ADVANCED
    )

    assert "depth 12" in result.text
    assert "e2e4 e7e5" in result.text


def test_best_move_explanation_mentions_stockfish_match() -> None:
    result = TemplateCommentary().generate(
        move_analysis(played_move="e2e4", best_move="e2e4", loss=0),
        classification(MoveQuality.BEST, 0),
    )

    assert "best move" in result.text
    assert "matches Stockfish's first choice" in result.text


@pytest.mark.parametrize(
    ("missed", "allowed", "expected"),
    [(True, False, "misses a forced mate"), (False, True, "opponent a forced mate")],
)
def test_mate_templates_take_priority(
    missed: bool, allowed: bool, expected: str
) -> None:
    result = TemplateCommentary().generate(
        move_analysis(loss=None, missed_mate=missed, allowed_mate=allowed),
        classification(MoveQuality.BLUNDER, None),
    )

    assert expected in result.text


def gemini_with_response(text: str) -> tuple[GeminiCommentary, MagicMock]:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return GeminiCommentary("test-key", "test-model", client=client), client


def test_gemini_sends_structured_grounded_payload() -> None:
    gemini, client = gemini_with_response(
        "After f2f3, Stockfish prefers e2e4 because the evaluation worsened."
    )

    result = gemini.generate(move_analysis(), classification())

    assert result.source == "gemini"
    call = client.models.generate_content.call_args.kwargs
    assert call["model"] == "test-model"
    payload = json.loads(call["contents"])
    assert payload["played_move"] == "f2f3"
    assert payload["stockfish_best_move"] == "e2e4"
    assert payload["centipawn_loss"] == 153
    assert "fen_before" not in payload
    assert "principal_variation" not in payload
    assert call["config"]["temperature"] == 0.2


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("A vague explanation with no verified moves.", "verified moves"),
        ("f2f3 " + "x" * 2000 + " e2e4", "long"),
    ],
)
def test_gemini_rejects_unusable_responses(text: str, message: str) -> None:
    gemini, _ = gemini_with_response(text)

    with pytest.raises(GeminiCommentaryError, match=message):
        gemini.generate(move_analysis(), classification())


def test_commentary_service_uses_gemini_for_significant_errors() -> None:
    ai = MagicMock()
    ai.generate.return_value = SimpleNamespace(
        text="f2f3 worsened the evaluation; Stockfish preferred e2e4.",
        level=UserLevel.BEGINNER,
        source="gemini",
    )
    service = CommentaryService(ai=ai)

    result = service.generate(move_analysis(), classification())

    assert result.source == "gemini"
    ai.generate.assert_called_once()


def test_commentary_service_skips_ai_for_good_moves() -> None:
    ai = MagicMock()
    service = CommentaryService(ai=ai)

    result = service.generate(
        move_analysis(loss=50), classification(MoveQuality.GOOD, 50)
    )

    assert result.source == "template"
    ai.generate.assert_not_called()


@pytest.mark.parametrize(
    "side_effect",
    [TimeoutError("timeout"), GeminiCommentaryError("invalid response")],
)
def test_commentary_service_falls_back_when_ai_fails(
    side_effect: Exception,
) -> None:
    ai = MagicMock()
    ai.generate.side_effect = side_effect
    service = CommentaryService(ai=ai)

    result = service.generate(move_analysis(), classification())

    assert result.source == "template"
    assert result.fallback_reason == type(side_effect).__name__
    assert "f2f3" in result.text
    assert "e2e4" in result.text


def test_create_service_without_complete_configuration_uses_templates() -> None:
    service = create_commentary_service(
        provider="gemini", api_key=None, model="test-model"
    )

    result = service.generate(move_analysis(), classification())

    assert result.source == "template"
