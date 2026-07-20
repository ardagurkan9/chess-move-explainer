"""Stockfish-grounded template and Gemini move explanations."""

import json
from typing import Any, Protocol

from src.models import (
    CommentaryResult,
    MoveAnalysis,
    MoveClassification,
    MoveContext,
    MoveQuality,
    MistakeTheme,
    ThemeDetection,
    UserLevel,
)
from src.move_context import MoveContextAnalyzer


QUALITY_OPENINGS: dict[MoveQuality, str] = {
    MoveQuality.BEST: "Nice move!",
    MoveQuality.EXCELLENT: "Strong choice!",
    MoveQuality.GOOD: "Good move.",
    MoveQuality.INACCURACY: "A small slip here.",
    MoveQuality.MISTAKE: "This move caused some trouble.",
    MoveQuality.BLUNDER: "This was a costly mistake.",
}

AI_EXPLANATION_QUALITIES = frozenset(MoveQuality)


class CommentaryGenerator(Protocol):
    """Common interface for commentary providers."""

    def generate(
        self,
        analysis: MoveAnalysis,
        classification: MoveClassification,
        *,
        level: UserLevel = UserLevel.BEGINNER,
        theme_detection: ThemeDetection | None = None,
        move_context: MoveContext | None = None,
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
        move_context: MoveContext | None = None,
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

        context = move_context or MoveContextAnalyzer().analyze(analysis)
        context_text = " ".join(context.facts[:2])
        text = f"{QUALITY_OPENINGS[classification.quality]} {context_text} {core}"
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
        if loss is not None and loss <= 40:
            return (
                f"{analysis.played_move} was a solid move. Stockfish slightly "
                f"preferred {analysis.best_move}."
            )
        if loss is None:
            return (
                f"You chose {analysis.played_move}, while Stockfish preferred "
                f"{analysis.best_move}. There is a forced mate in the position."
            )
        return (
            f"{analysis.played_move} made the position harder to handle. "
            f"Stockfish preferred {analysis.best_move}."
        )


class GeminiCommentary:
    """Generate constrained explanations with the Google Gemini API."""

    SYSTEM_INSTRUCTION = (
        "You are a friendly, concise chess coach explaining a verified Stockfish analysis. "
        "Sound like a human coach speaking directly to a student, not an engine report. "
        "Lead with what the move concretely accomplished, using verified_move_context. "
        "Give a practical lesson only when it follows directly from verified evidence. "
        "Do not recite centipawn values or numeric evaluation changes; the UI already shows them. "
        "Do not choose a different best move. Do not invent a tactic, threat, "
        "mistake theme, board feature, opening name, plan, positional concept, "
        "or continuation. You may explain a verified_theme only when it is "
        "present, using only verified_evidence. Do not explain why either move "
        "is good or bad beyond that evidence. The "
        "only permitted facts are the verified move context, classification, "
        "centipawn loss, numeric evaluation change, mate flags, played move, Stockfish best move, and "
        "any explicit verified theme evidence in the payload. Avoid labels such as "
        "'verified theme', robotic phrases, "
        "and raw engine jargon. Mention the played move exactly as supplied; mention "
        "Stockfish's best move only when comparing alternatives is useful. Write "
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
        move_context: MoveContext | None = None,
    ) -> CommentaryResult:
        """Request and validate a grounded explanation from Gemini."""
        context = move_context or MoveContextAnalyzer().analyze(analysis)
        payload = self._payload(
            analysis,
            classification,
            level,
            theme_detection=theme_detection,
            move_context=context,
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
        move_context: MoveContext | None,
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
        if move_context is not None:
            payload["verified_move_context"] = list(move_context.facts)
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
        if analysis.played_move not in text:
            raise GeminiCommentaryError(
                "Gemini explanation does not reference the played move."
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
        move_context: MoveContext | None = None,
    ) -> CommentaryResult:
        """Return AI commentary when safe, otherwise deterministic commentary."""
        context = move_context or MoveContextAnalyzer().analyze(analysis)
        fallback = self.template.generate(
            analysis,
            classification,
            level=level,
            theme_detection=theme_detection,
            move_context=context,
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
                move_context=context,
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
        move_context: MoveContext | None = None,
    ) -> CommentaryResult:
        """Explain an incorrect practice answer, using AI for every quality."""
        context = move_context or MoveContextAnalyzer().analyze(analysis)
        fallback = self.template.generate(
            analysis,
            classification,
            level=level,
            theme_detection=theme_detection,
            move_context=context,
        )
        if self.ai is None:
            return fallback
        try:
            result = self.ai.generate(
                analysis,
                classification,
                level=level,
                theme_detection=theme_detection,
                move_context=context,
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
