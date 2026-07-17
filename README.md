# Explainable Chess Coach

> A Python-based chess coach that turns Stockfish analysis into clear, educational feedback.

## About the Project

Explainable Chess Coach lets users play against Stockfish while analyzing their moves and explaining the results at an appropriate skill level.

Instead of merely displaying the best move, the project aims to answer questions such as:

- Why was my move good or bad?
- Why is the recommended move stronger?
- What was the main threat or tactical idea in the position?
- Did I leave a piece undefended?
- What plan should I follow in this position?
- Which principle should I learn to avoid making the same mistake?

The core idea is simple:

```text
Stockfish analyzes.
The application calculates.
AI explains.
The user learns.
```

> [!IMPORTANT]
> This project is under development. This README describes the planned architecture and target for the first stable release; not all features listed below have been implemented yet.

## How It Works

```text
The user makes a move
        ↓
The move is validated
        ↓
The positions before and after the move are analyzed with Stockfish
        ↓
The evaluation difference and centipawn loss are calculated
        ↓
The move is assigned a quality classification
        ↓
The best move and a short continuation are displayed
        ↓
An explanation suited to the user's level is generated
        ↓
Stockfish plays its response
```

The language model does not choose the best move or evaluate the position. Stockfish is responsible for both. The language model only makes engine analysis easier to understand and must not present suggestions unsupported by Stockfish as facts.

The same rule applies to mistake themes: the language model must not decide why
a move was wrong. The application derives the theme from board state and
Stockfish evidence; the language model may only explain that verified theme at
the user's level.

## Planned Features

### Gameplay

- Complete games against Stockfish
- Choice of playing as White or Black
- Legal move, check, checkmate, and stalemate detection
- Castling, en passant, and pawn promotion
- Configurable Stockfish strength
- Move history and game restart
- PGN export

### Move Analysis

- Position evaluation before and after each move
- Best move and a short Principal Variation (PV)
- MultiPV comparison of multiple candidate moves
- Centipawn loss calculated from the player's perspective
- Separate handling of mate scores and regular position scores
- Best, Excellent, Good, Inaccuracy, Mistake, and Blunder classifications

The initial classification thresholds are planned as follows:

| Centipawn loss | Classification |
| -------------: | -------------- |
|          0–15 | Best           |
|         16–40 | Excellent      |
|         41–80 | Good           |
|        81–150 | Inaccuracy     |
|       151–300 | Mistake        |
|           301+ | Blunder        |

These values are not absolute chess rules. Forced moves, equivalent candidates, and mating opportunities must be evaluated separately.

### Explainable Feedback

- Explanation of the main issue with a move
- Description of why Stockfish's recommendation is stronger
- Identification of threats and short-term plans
- Different explanations for beginner, intermediate, and advanced players
- Template-based fallback when the language model is unavailable
- End-of-game error distribution, average centipawn loss, and improvement suggestions

### Reliable Mistake Themes

Move quality and mistake theme are treated as separate concepts:

```text
Mistake / Blunder = How costly was the move?
Hanging piece      = What kind of error was it?
```

The first version will deliberately use a small set of themes:

| Theme | Meaning |
| --- | --- |
| `HANGING_PIECE` | A piece was left capturable without sufficient compensation |
| `MISSED_MATE` | The player had a forced mate but lost it |
| `ALLOWED_MATE` | The move gave the opponent a forced mate |
| `MATERIAL_LOSS` | The verified continuation leads to a net material loss |
| `KING_SAFETY` | The move creates a verifiable weakness around the king |
| `GENERAL_ERROR` | No more specific theme can be established safely |

Theme detection must be deterministic and evidence-based. Mate themes come
directly from Stockfish scores. Other themes use board comparison, attack and
defense information, material changes, and the principal variation. When the
available evidence is not strong enough, the application uses `GENERAL_ERROR`
instead of guessing.

A detected theme should include both evidence and confidence:

```python
ThemeDetection(
    theme=MistakeTheme.HANGING_PIECE,
    evidence=(
        "The knight on e5 is attacked by the pawn on d6.",
        "Stockfish's principal variation begins with d6e5.",
    ),
    confidence=0.95,
)
```

The language model receives this verified result and follows three constraints:

- Do not change the detected mistake theme.
- Do not invent a tactic, threat, or alternative move.
- Explain only the supplied evidence and Stockfish continuation.

### Personal Mistake Tracking

The project will store important mistakes so users can learn from recurring
patterns instead of receiving only one-time move feedback. The system will:

- Save analyzed games and significant mistakes
- Group repeated mistakes by verified theme
- Generate review positions from the FEN before each mistake
- Let users attempt those positions again
- Record review attempts and whether the expected move was found
- Track improvement by theme over time
- Schedule missed positions for another review

The first review schedule can use simple intervals:

```text
Incorrect answer   -> review tomorrow
First correct      -> review in 3 days
Second correct     -> review in 7 days
Third correct      -> review in 14 days
```

Database access will remain separate from chess and analysis logic through a
repository layer:

```text
CLI / Streamlit
      ↓
Application service
      ↓
MistakeRepository / GameRepository
      ↓
SQLAlchemy 2
      ↓
PostgreSQL
```

Core persistence entities are planned as:

| Entity | Stored information |
| --- | --- |
| `games` | Date, player color, result, PGN, engine settings, and starting FEN |
| `move_analyses` | FENs, played and recommended moves, scores, loss, quality, PV, and depth |
| `mistakes` | Verified theme, evidence, confidence, and review schedule |
| `review_attempts` | Submitted move, expected move, result, duration, and attempt date |

Analysis modules must not import SQLAlchemy or write to the database directly.
They return domain results, and an application service decides what should be
persisted through repository interfaces.

## User Levels

| Level        | Explanation style                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------- |
| Beginner     | Short explanations focused on development, center control, king safety, and other fundamental principles |
| Intermediate | Tactical ideas, pawn structures, weak squares, and short variations                                      |
| Advanced     | Candidate move comparisons, longer variations, and positional plans                                      |

## Technology Stack

- Python
- [python-chess](https://python-chess.readthedocs.io/)
- [Stockfish](https://stockfishchess.org/)
- Streamlit
- pytest
- Google Gemini API (`gemini-3.1-flash-lite` by default)
- GitHub Actions
- Docker
- PostgreSQL
- SQLAlchemy 2
- Alembic
- psycopg
- Docker Compose

## Planned Project Structure

```text
explainable-chess-coach/
├── app.py
├── src/
│   ├── __init__.py
│   ├── game.py
│   ├── engine.py
│   ├── analysis.py
│   ├── move_classifier.py
│   ├── mistake_detector.py
│   ├── commentary.py
│   ├── models.py
│   ├── report.py
│   ├── services/
│   └── repositories/
├── migrations/
├── tests/
│   ├── test_game.py
│   ├── test_engine.py
│   ├── test_analysis.py
│   ├── test_move_classifier.py
│   └── test_report.py
├── examples/
├── assets/
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── PROJECT_SPEC.md
└── LICENSE
```

Core module responsibilities:

| Module                 | Responsibility                                               |
| ---------------------- | ------------------------------------------------------------ |
| `game.py`            | Board state, move validation, game result, and move history  |
| `engine.py`          | Stockfish process, evaluation, best move, PV, and MultiPV    |
| `analysis.py`        | Perspective conversion, score comparison, and centipawn loss |
| `move_classifier.py` | Move quality, thresholds, and special mate cases             |
| `mistake_detector.py` | Evidence-based mistake-theme detection                      |
| `commentary.py`      | Template- or language-model-based educational explanations   |
| `models.py`          | Data models shared across the application                    |
| `report.py`          | End-of-game statistics and PGN output                        |
| `repositories/`      | Database interfaces and SQLAlchemy implementations           |

## Installation

The exact installation steps will be finalized as the application code and dependency files are added. The target development environment is described below.

### Requirements

- Python 3.11 or later
- A Stockfish executable compatible with your operating system
- Optionally, a Gemini API key for AI explanations

### Development Environment

```bash
git clone <repository-url>
cd chess-move-explainer

python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install the runtime dependencies:

```bash
pip install -r requirements.txt
```

For development and testing, install the development dependencies instead:

```bash
pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` and enter your own values:

```env
STOCKFISH_PATH=/path/to/stockfish
AI_PROVIDER=gemini
AI_API_KEY=your_api_key
AI_MODEL=gemini-3.1-flash-lite
```

Gemini is called only for Inaccuracy, Mistake, and Blunder classifications.
Missing configuration, timeouts, API errors, empty responses, and responses
that do not reference the verified moves automatically fall back to the
deterministic template explanation. Stockfish analysis and gameplay never
depend on the language model being available.

The real `.env` file and the Stockfish executable must not be committed to the repository.

Run the current terminal application with:

```bash
python app.py
```

The later Streamlit interface will use `streamlit run app.py` or a dedicated
web entry point.

Run the test suite with:

```bash
pytest
```

## Development Roadmap

- [X] Project structure, dependencies, and environment configuration
- [X] Chessboard and move validation
- [X] Stockfish connection and position analysis
- [x] Single-move analysis from the player's perspective
- [x] Move classification system
- [x] Terminal-based game loop
- [x] Template-based explanations
- [x] Language model integration with a safe fallback
- [ ] End-of-game report and PGN output
- [ ] Evidence-based mistake-theme detection
- [ ] PostgreSQL, SQLAlchemy, Alembic, and repository infrastructure
- [ ] Persistent game and move-analysis history
- [ ] Personal mistake library and recurring-theme statistics
- [ ] Position review and spaced-repetition workflow
- [ ] Streamlit interface
- [ ] Automated tests, GitHub Actions, and Docker support

## License

The license has not been selected yet. A `LICENSE` file will be added before the project is made available for open-source use.
