# Trading Bot — Contributing

This project is built by an autonomous development system (kanban worker + agy for implementation + Hermes for planning/review). These guidelines exist so automated contributors produce consistent, high-quality output.

## For the Autonomous Worker

### Before Starting a Task
1. Read `GOAL.md` — understand vision, MVP criteria, and hard constraints
2. Read `PO_DECISIONS.md` — understand priority order and what's in/out of scope
3. Read `docs/QUALITY_BAR.md` — understand the quality standard
4. Check `tests/` — run `python3 -m pytest tests/ -v --tb=short` and note pass/fail state

### During Implementation
1. **Plan first**: read the relevant code files before writing anything
2. **TDD**: write tests first (verify they fail), implement, verify they pass
3. **Financial correctness check**: if touching features, backtest, risk supervisor, or live trading — verify no look-ahead bias, no bar-close execution, risk gate always on
4. **Commit often**: one logical change per commit with descriptive message

### What NOT to Do
- Don't hardcode impl_* functions per task — write generic, testable code
- Don't use global statistics in normalization
- Don't modify code outside the task's assigned files without explicit PO approval
- Don't add test files outside `tests/`
- Don't modify .venv/, __pycache__/, .kanban/, .git/

### After Implementation
1. Run tests: `python3 -m pytest tests/ -v --tb=short` — must pass
2. Run linter: `flake8 features/ backtest/ env/ models/ tests/` — fix all errors before submitting
3. Verify git diff only touches intended files
4. Write a sprint message: what was built, what tests pass, what changed since last sprint

## Development Environment

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
python3 -m pytest tests/ -v --tb=short

# Run backtest
python3 -m backtest.run --episodes 10

# Lint
flake8 features/ backtest/ env/ models/ live_trade_mt5.py tests/
```

## Reporting Issues

Issues found in code or tests should be added to the Hermes kanban board as new tasks. Priority:
1. Security/data-leak issues → critical
2. Precision errors (look-ahead bias, wrong execution timing) → critical
3. Failing tests → high
4. Missing tests → medium
5. Documentation gaps → low
