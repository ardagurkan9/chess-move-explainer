"""Stockfish-grounded template and Gemini move explanations."""

import json
from typing import Any, Protocol

from src.models import (
    CommentaryResult,
    MoveAnalysis,
    MoveClassification,
    MoveQuality,
    MistakeTheme,
    ThemeDetection,
    UserLevel,
)


QUALITY_OPENINGS: dict[MoveQuality, str] = {
    MoveQuality.BEST: "Nice move!",
    MoveQuality.EXCELLENT: "Strong choice!",
    MoveQuality.GOOD: "Good move.",
    MoveQuality.INACCURACY: "A small slip here.",
    MoveQuality.MISTAKE: "This move caused some trouble.",
    MoveQuality.BLUNDER: "This was a costly mistake.",
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
        theme_detection: ThemeDetection | None = None,
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
        theme_detection: ThemeDetection | None = None,
    ) -> CommentaryResult:
        """Build an explanation using only supplied engine analysis."""
        if analysis.allowed_forced_mate:
            core = (
                f"After {analysis.played_move}, your opponent has a forced mate. "
                f"{analysis.best_move} was the way to avoid it."
            )
        elif analysis.missed_forced_mate:
            core = (
                f"{analysis.played_move} lets a forced mate slip away. "
                f"{analysis.best_move} would have kept the mating sequence."
            )
        else:
            core = self._standard_explanation(analysis, classification)

        detail = self._level_detail(analysis, level)
        text = f"{QUALITY_OPENINGS[classification.quality]} {core}"
        if detail:
            text = f"{text} {detail}"
        if (
            theme_detection is not None
            and theme_detection.theme is not MistakeTheme.GENERAL_ERROR
        ):
            evidence = " ".join(theme_detection.evidence)
            text = (
                f"{text} The key issue is "
                f"{theme_detection.theme.value.replace('_', ' ').lower()}: {evidence}"
            )
        return CommentaryResult(text=text, level=level)

    @staticmethod
    def _standard_explanation(
        analysis: MoveAnalysis, classification: MoveClassification
    ) -> str:
        if analysis.played_move == analysis.best_move:
            return (
                f"{analysis.played_move} was Stockfish's top choice too, so you "
                "found exactly what the position called for."
            )

        loss = classification.centipawn_loss
        if loss == 0:
            return (
                f"{analysis.played_move} was just as strong as Stockfish's top "
                f"choice, {analysis.best_move}."
            )
        if classification.quality is MoveQuality.BEST and loss is not None:
            return (
                f"{analysis.played_move} was nearly identical in strength to "
                f"Stockfish's top choice, {analysis.best_move}."
            )
        loss_text = (
            f" The evaluation dropped by about {loss / 100:.2f} pawns "
            f"({loss} centipawns)."
            if loss is not None
            else " There is a forced mate in the position."
        )
        return (
            f"You chose {analysis.played_move}, but {analysis.best_move} was "
            f"stronger.{loss_text}"
        )

    def _level_detail(self, analysis: MoveAnalysis, level: UserLevel) -> str:
        if level is UserLevel.BEGINNER:
            return "A useful habit is to pause and compare these two moves before continuing."

        evaluation = self._evaluation_detail(analysis)
        if level is UserLevel.INTERMEDIATE:
            return evaluation

        pv = " ".join(analysis.before.pv)
        depth = analysis.before.depth
        depth_text = f" at depth {depth}" if depth is not None else ""
        line_text = f" Stockfish's line{depth_text}: {pv}." if pv else ""
        return f"{evaluation}{line_text}"

    def _evaluation_detail(self, analysis: MoveAnalysis) -> str:
        before = analysis.before.score_cp
        after = analysis.after.score_cp
        scores = (
            f"{self._format_score(analysis.before)} to "
            f"{self._format_score(analysis.after)}"
        )
        if before is None or after is None:
            return f"The engine evaluation changed from {scores}."

        change = after - before
        if abs(change) <= 15:
            return f"The position stayed roughly stable, moving from {scores}."
        if change > 0:
            return f"From your perspective, the position improved from {scores}."
        return f"From your perspective, the position worsened from {scores}."

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
        "You are a friendly, concise chess coach explaining a verified Stockfish analysis. "
        "Sound like a human coach speaking directly to a student, not an engine report. "
        "Lead with the practical lesson and use simple, varied language. "
        "Do not choose a different best move. Do not invent a tactic, threat, "
        "mistake theme, board feature, opening name, plan, positional concept, "
        "or continuation. You may explain a verified_theme only when it is "
        "present, using only verified_evidence. Do not explain why either move "
        "is good or bad beyond that evidence. The "
        "only permitted facts are the classification, centipawn loss, numeric "
        "evaluation change, mate flags, played move, Stockfish best move, and "
        "any explicit verified theme evidence in the payload. Mention both moves "
        "exactly as supplied. Avoid labels such as 'verified theme', robotic phrases, "
        "and raw centipawn jargon when a plain-language description is enough. Write "
        "at most two short sentences in English with no markdown."
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
        theme_detection: ThemeDetection | None = None,
    ) -> CommentaryResult:
        """Request and validate a grounded explanation from Gemini."""
        payload = self._payload(
            analysis, classification, level, theme_detection=theme_detection
        )
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
        *,
        theme_detection: ThemeDetection | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
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
        if theme_detection is not None:
            payload["verified_theme"] = theme_detection.theme.value
            payload["verified_evidence"] = list(theme_detection.evidence)
            payload["theme_confidence"] = theme_detection.confidence
        return payload

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
        theme_detection: ThemeDetection | None = None,
    ) -> CommentaryResult:
        """Return AI commentary when safe, otherwise deterministic commentary."""
        fallback = self.template.generate(
            analysis,
            classification,
            level=level,
            theme_detection=theme_detection,
        )
        if self.ai is None:
            return fallback
        if classification.quality not in AI_EXPLANATION_QUALITIES:
            return fallback

        try:
            result = self.ai.generate(
                analysis,
                classification,
                level=level,
                theme_detection=theme_detection,
            )
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

    def generate_for_review(
        self,
        analysis: MoveAnalysis,
        classification: MoveClassification,
        *,
        level: UserLevel = UserLevel.BEGINNER,
        theme_detection: ThemeDetection | None = None,
    ) -> CommentaryResult:
        """Explain an incorrect practice answer, using AI for every quality."""
        fallback = self.template.generate(
            analysis,
            classification,
            level=level,
            theme_detection=theme_detection,
        )
        if self.ai is None:
            return fallback
        try:
            result = self.ai.generate(
                analysis,
                classification,
                level=level,
                theme_detection=theme_detection,
            )
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
