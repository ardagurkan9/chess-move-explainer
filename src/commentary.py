"""Stockfish-grounded template and Gemini move explanations."""

import json
from typing import Any, Protocol

from src.models import (
    CommentaryResult,
    MoveAnalysis,
    MoveClassification,
    MoveQuality,
    UserLevel,
)


QUALITY_OPENINGS: dict[MoveQuality, str] = {
    MoveQuality.BEST: "This was the best move.",
    MoveQuality.EXCELLENT: "This was an excellent move.",
    MoveQuality.GOOD: "This was a good move.",
    MoveQuality.INACCURACY: "This move was an inaccuracy.",
    MoveQuality.MISTAKE: "This move was a mistake.",
    MoveQuality.BLUNDER: "This move was a blunder.",
}

AI_EXPLANATION_QUALITIES = frozenset(
    {MoveQuality.INACCURACY, MoveQuality.MISTAKE, MoveQuality.BLUNDER}
)


class CommentaryGenerator(Protocol):
    """Common interface for commentary providers."""

    def generate(
        self,
        analysis: MoveAnalysis,
        classification: MoveClassification,
        *,
        level: UserLevel = UserLevel.BEGINNER,
    ) -> CommentaryResult: ...


class GeminiCommentaryError(RuntimeError):
    """Raised when Gemini cannot produce a usable explanation."""


class TemplateCommentary:
    """Generate explanations without an external language model."""

    def generate(
        self,
        analysis: MoveAnalysis,
        classification: MoveClassification,
        *,
        level: UserLevel = UserLevel.BEGINNER,
    ) -> CommentaryResult:
        """Build an explanation using only supplied engine analysis."""
        if analysis.allowed_forced_mate:
            core = (
                f"{analysis.played_move} gives your opponent a forced mate. "
                f"Stockfish preferred {analysis.best_move}."
            )
        elif analysis.missed_forced_mate:
            core = (
                f"{analysis.played_move} misses a forced mate. "
                f"Stockfish preferred {analysis.best_move}."
            )
        else:
            core = self._standard_explanation(analysis, classification)

        detail = self._level_detail(analysis, level)
        text = f"{QUALITY_OPENINGS[classification.quality]} {core}"
        if detail:
            text = f"{text} {detail}"
        return CommentaryResult(text=text, level=level)

    @staticmethod
    def _standard_explanation(
        analysis: MoveAnalysis, classification: MoveClassification
    ) -> str:
        if analysis.played_move == analysis.best_move:
            return (
                f"{analysis.played_move} matches Stockfish's first choice and "
                "preserves the engine's preferred continuation."
            )

        loss = classification.centipawn_loss
        loss_text = (
            f" It loses {loss} centipawns."
            if loss is not None
            else " The position contains a forced-mate evaluation."
        )
        return (
            f"You played {analysis.played_move}; Stockfish preferred "
            f"{analysis.best_move}.{loss_text}"
        )

    def _level_detail(self, analysis: MoveAnalysis, level: UserLevel) -> str:
        if level is UserLevel.BEGINNER:
            return "Compare your move with the suggested move before continuing."

        evaluation = (
            f"The evaluation changed from {self._format_score(analysis.before)} "
            f"to {self._format_score(analysis.after)}."
        )
        if level is UserLevel.INTERMEDIATE:
            return evaluation

        pv = " ".join(analysis.before.pv)
        depth = analysis.before.depth
        depth_text = f" at depth {depth}" if depth is not None else ""
        line_text = f" Stockfish's line{depth_text}: {pv}." if pv else ""
        return f"{evaluation}{line_text}"

    @staticmethod
    def _format_score(result: object) -> str:
        mate = getattr(result, "mate", None)
        if mate is not None:
            return f"mate {mate:+d}"
        score_cp = getattr(result, "score_cp", None)
        if score_cp is None:
            return "an unknown score"
        return f"{score_cp / 100:+.2f}"


class GeminiCommentary:
    """Generate constrained explanations with the Google Gemini API."""

    SYSTEM_INSTRUCTION = (
        "You are a chess coach explaining a verified Stockfish analysis. "
        "Do not choose a different best move. Do not invent a tactic, threat, "
        "mistake theme, board feature, opening name, plan, positional concept, "
        "or continuation. Do not explain why either move is good or bad. The "
        "only permitted facts are the classification, centipawn loss, numeric "
        "evaluation change, mate flags, played move, and Stockfish best move in "
        "the payload. Mention both moves exactly as supplied. Write at most two "
        "short sentences in English with no markdown."
    )

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 10.0,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Gemini API key cannot be empty.")
        if not model.strip():
            raise ValueError("Gemini model cannot be empty.")

        self.model = model.strip()
        if client is None:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=api_key.strip(),
                http_options=types.HttpOptions(
                    timeout=max(1, int(timeout_seconds * 1000))
                ),
            )
        self.client = client

    def generate(
        self,
        analysis: MoveAnalysis,
        classification: MoveClassification,
        *,
        level: UserLevel = UserLevel.BEGINNER,
    ) -> CommentaryResult:
        """Request and validate a grounded explanation from Gemini."""
        payload = self._payload(analysis, classification, level)
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=json.dumps(payload, ensure_ascii=True),
                config={
                    "system_instruction": self.SYSTEM_INSTRUCTION,
                    "temperature": 0.2,
                    "max_output_tokens": 300,
                },
            )
            text = (response.text or "").strip()
        except Exception as error:
            raise GeminiCommentaryError("Gemini request failed.") from error

        self._validate_response(text, analysis)
        return CommentaryResult(text=text, level=level, source="gemini")

    @staticmethod
    def _payload(
        analysis: MoveAnalysis,
        classification: MoveClassification,
        level: UserLevel,
    ) -> dict[str, object]:
        return {
            "task": "Explain this verified Stockfish move analysis.",
            "user_level": level.value,
            "played_move": analysis.played_move,
            "stockfish_best_move": analysis.best_move,
            "classification": classification.quality.value,
            "centipawn_loss": classification.centipawn_loss,
            "evaluation_before": {
                "centipawns": analysis.before.score_cp,
                "mate": analysis.before.mate,
            },
            "evaluation_after": {
                "centipawns": analysis.after.score_cp,
                "mate": analysis.after.mate,
            },
            "missed_forced_mate": analysis.missed_forced_mate,
            "allowed_forced_mate": analysis.allowed_forced_mate,
            "constraints": [
                "Do not recommend a move other than stockfish_best_move.",
                "Do not infer a specific mistake theme from these values.",
                "Do not add chess claims absent from this payload.",
                "Do not infer anything from your general knowledge of the moves.",
            ],
        }

    @staticmethod
    def _validate_response(text: str, analysis: MoveAnalysis) -> None:
        if not text:
            raise GeminiCommentaryError("Gemini returned an empty explanation.")
        if len(text) > 2000:
            raise GeminiCommentaryError("Gemini explanation is unexpectedly long.")
        if analysis.played_move not in text or analysis.best_move not in text:
            raise GeminiCommentaryError(
                "Gemini explanation does not reference the verified moves."
            )


class CommentaryService:
    """Use Gemini for significant errors and safely fall back to templates."""

    def __init__(
        self,
        template: TemplateCommentary | None = None,
        ai: CommentaryGenerator | None = None,
    ) -> None:
        self.template = template or TemplateCommentary()
        self.ai = ai

    def generate(
        self,
        analysis: MoveAnalysis,
        classification: MoveClassification,
        *,
        level: UserLevel = UserLevel.BEGINNER,
    ) -> CommentaryResult:
        """Return AI commentary when safe, otherwise deterministic commentary."""
        fallback = self.template.generate(
            analysis, classification, level=level
        )
        if self.ai is None:
            return fallback
        if classification.quality not in AI_EXPLANATION_QUALITIES:
            return fallback

        try:
            result = self.ai.generate(analysis, classification, level=level)
        except Exception as error:
            return CommentaryResult(
                text=fallback.text,
                level=fallback.level,
                source="template",
                fallback_reason=type(error).__name__,
            )

        if not result.text.strip():
            return CommentaryResult(
                text=fallback.text,
                level=fallback.level,
                source="template",
                fallback_reason="empty_ai_response",
            )
        return result


def create_commentary_service(
    *, provider: str | None, api_key: str | None, model: str | None
) -> CommentaryService:
    """Build the configured service, defaulting safely to templates."""
    if provider != "gemini" or not api_key or not model:
        return CommentaryService()
    try:
        gemini = GeminiCommentary(api_key=api_key, model=model)
    except Exception:
        return CommentaryService()
    return CommentaryService(ai=gemini)
