# Trading Bot — Quality Bar

What "good enough to merge" looks like for this project.

## Code Quality

### Python (General — all modules)
- **Type hints** on all function signatures
- **Docstrings** on all public functions (Google style: Args, Returns, Raises)
- **No bare except** — always catch specific exceptions with explanation
- **All external calls wrapped** in try/except with structured logging
- **Config via environment** — no hardcoded paths, URLs, or credentials
- **Deterministic where required** — fixed seeds for data splitting, model training, backtesting
- **Versioned artifacts** — model weights, scaler parameters, and backtest results include timestamp and git commit hash

### Financial Correctness (non-negotiable)
- **No look-ahead bias**: rolling windows only; `mean()`, `std()`, `min()`, `max()` computed on data strictly before the prediction timestamp
- **Next-bar execution**: model output at bar `t` fills at open of bar `t+1`; backtest must mirror this exactly
- **Risk before execution**: RiskSupervisor.check_trade() called before every execute_trade(); rejected trades logged
- **No NaN propagation**: features/gradients with NaN treated as errors, not silently filled with 0
- **Audit log**: every trade attempt logged with timestamp, features snapshot (hash), model action, risk verdict, fill price

### Machine Learning
- **Train/val/test split** respects temporal ordering (no shuffle — time series!)
- **Model weights versioned**: filename includes `{model}_v{N}_{YYYYMMDD}_{commit}.pt`
- **Overfit detection**: training loss vs validation loss monitored; divergence → stop training
- **Out-of-sample validation**: walk-forward analysis, not single train/test split

### Backtester
- **Execution model matches live**: same open-bar logic, same slippage model, same commission model
- **No survivorship bias**: data includes all symbols, not just currently-listed ones
- **Realistic fill assumptions**: limit orders fill if price crosses limit; market orders fill at next bar open + slippage
- **Full equity curve**: exported as CSV with timestamp, portfolio value, drawdown, trade count

## Tests

### Coverage Requirements
- **Unit tests**: ≥80% coverage for `features/make_features.py`, `backtest/backtest_engine.py`, `models/risk_supervisor.py`, `env/xauusd_env.py`
- **All new code** must include tests
- **Regression tests**: every bug fix must include a test that would have caught it

### Test Specifics
- **Features**: test normalization produces same output on re-run with same input; test no-timestamp-leakage
- **Backtester**: test that buy at bar `t` fills at open of bar `t+1`; test that risk rejection prevents execution
- **Risk supervisor**: test drawdown limit stops new positions; test position size within capital limits
- **Environment**: test observation shape matches model input; test reward calculation has no edge leakage

### Test Hygiene
- Use `pytest -v --tb=short` for readable failures
- No `xfail` without tracking issue
- No skipped tests without documented reason

## Git Discipline

- **One commit per task** (squash merge to main)
- **Conventional commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- **No force push to main**
- **Branch naming**: `task/{id}-{slug}` (e.g., `task/T001-fix-normalization-leak`)
- **Every PR includes**: code, tests, and a brief explanation of the change in the commit message

## Documentation

- **README.md**: project overview, install instructions, current status, known limitations
- **GOAL.md**: vision, MVP criteria, success metrics (required, updated by PO)
- **PO_DECISIONS.md**: scope, priority order, technical decisions (required, maintained by PO)
- **Inline docstrings**: all public functions and classes

## What Does NOT Count as "Done"

- Code that passes tests but uses global feature statistics
- Backtest that shows 95% win rate because of look-ahead bias
- Model weights trained on mixed train/test data
- "I'll add tests later"
- Commit with message "WIP" or "fix stuff"
- Changes outside the worker's assigned task branch (no hijacking)
