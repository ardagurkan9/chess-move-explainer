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
| ---: | --- |
| 0–15 | Best |
| 16–40 | Excellent |
| 41–80 | Good |
| 81–150 | Inaccuracy |
| 151–300 | Mistake |
| 301+ | Blunder |

These values are not absolute chess rules. Forced moves, equivalent candidates, and mating opportunities must be evaluated separately.

### Explainable Feedback

- Explanation of the main issue with a move
- Description of why Stockfish's recommendation is stronger
- Identification of threats and short-term plans
- Different explanations for beginner, intermediate, and advanced players
- Template-based fallback when the language model is unavailable
- End-of-game error distribution, average centipawn loss, and improvement suggestions

## User Levels

| Level | Explanation style |
| --- | --- |
| Beginner | Short explanations focused on development, center control, king safety, and other fundamental principles |
| Intermediate | Tactical ideas, pawn structures, weak squares, and short variations |
| Advanced | Candidate move comparisons, longer variations, and positional plans |

## Technology Stack

- Python
- [python-chess](https://python-chess.readthedocs.io/)
- [Stockfish](https://stockfishchess.org/)
- Streamlit
- pytest
- A language model API or local model
- GitHub Actions
- Docker

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
│   ├── commentary.py
│   ├── models.py
│   └── report.py
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

| Module | Responsibility |
| --- | --- |
| `game.py` | Board state, move validation, game result, and move history |
| `engine.py` | Stockfish process, evaluation, best move, PV, and MultiPV |
| `analysis.py` | Perspective conversion, score comparison, and centipawn loss |
| `move_classifier.py` | Move quality, thresholds, and special mate cases |
| `commentary.py` | Template- or language-model-based educational explanations |
| `models.py` | Data models shared across the application |
| `report.py` | End-of-game statistics and PGN output |

## Installation

The exact installation steps will be finalized as the application code and dependency files are added. The target development environment is described below.

### Requirements

- Python 3.11 or later
- A Stockfish executable compatible with your operating system
- Optionally, a language model API key or a local model

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

Once the dependency file is available, install the dependencies:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and enter your own values:

```env
STOCKFISH_PATH=/path/to/stockfish
AI_API_KEY=your_api_key
AI_MODEL=model_name
```

The real `.env` file and the Stockfish executable must not be committed to the repository.

Once the application entry point is ready, the target command will be:

```bash
streamlit run app.py
```

Run the test suite with:

```bash
pytest
```

## Development Roadmap

- [ ] Project structure, dependencies, and environment configuration
- [ ] Chessboard and move validation
- [ ] Stockfish connection and position analysis
- [ ] Single-move analysis from the player's perspective
- [ ] Move classification system
- [ ] Terminal-based game loop
- [ ] Template-based explanations
- [ ] Language model integration with a safe fallback
- [ ] End-of-game report and PGN output
- [ ] Streamlit interface
- [ ] Automated tests, GitHub Actions, and Docker support

## Out of Scope for the First Release

- Online multiplayer
- User accounts and friend system
- Matchmaking and tournaments
- Mobile application
- Voice assistant
- Development of a custom chess engine
- Training a language model from scratch

## Success Criteria

The first stable release will be considered complete when:

- The user can play a complete game against Stockfish.
- Illegal moves are rejected and special chess rules work correctly.
- Every user move is analyzed from the correct perspective.
- The best move, a short variation, and the move classification are displayed.
- Centipawn loss and mate scores are handled correctly.
- Explanations are grounded in Stockfish analysis.
- The application continues to work when the AI service is unavailable.
- Basic statistics and a PGN are generated at the end of the game.
- Critical behavior is covered by automated tests.

## Contributing

The project is in an early stage of development. To contribute, open an issue or submit a pull request describing the purpose of the change and how it was tested.

## License

The license has not been selected yet. A `LICENSE` file will be added before the project is made available for open-source use.
