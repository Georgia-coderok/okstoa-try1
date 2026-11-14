# Make Blueprints Talk (Stoa challenge, Junction)

Answers natural-language questions about construction drawings and BIM models,
with every answer pointing to the exact spot on the drawing it came from.

## Team
| Role | Owns |
|---|---|
| Reader | Reading files, building `building.db`, `render()` |
| Brain | Agent, tools, verification, evaluation |
| Face | Interface, demo, pitch, symbol counting |

## Setup (Windows)
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # then put your own key in .env
```

## Run
```
.venv\Scripts\python.exe brain_starter.py "What is the fire rating of door D-214?"
.venv\Scripts\python.exe tests\smoke_tests.py
```

## Question types (for eval/questions_typed.csv)
| Type | Meaning | Example |
|---|---|---|
| T1 | Text lookup | What is the project number? |
| T2 | Schedule/table lookup | Fire rating of door D-214? |
| T3 | Count | How many windows on level 2? |
| T4 | Measurement | Width of corridor 1.05? |
| T5 | Cross-sheet | Which detail shows the roof edge? |
| T6 | BIM property/quantity | Total wall area of type W3? |
| T7 | Spatial reasoning | Which rooms are next to the stairwell? |

## Git workflow
- Each person works on their own branch: `reader`, `brain`, `face`.
- Merge into `main` through a pull request; Face reviews and merges.
- `main` must always run.
- Never commit `.env` or Stoa's data files.