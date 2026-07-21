# Trading Bot — Project Goal

## Vision

Build a disciplined, correct, and auditable algorithmic trading system for XAU/USD (gold) that can be backtested, paper-traded, and — only after validation — deployed live. The system must be **correct first, profitable second, fast third**. A bot that loses money slowly and transparently is more valuable than one that wins by luck and hides risk.

## Problem

Most retail trading bots share the same fatal flaws:
- **Look-ahead bias** in features — using data the model couldn't have seen at prediction time, producing backtests that look good but fail live
- **Leakage in execution timing** — backtest assumes instant fill at bar close; live execution happens at next bar open, creating systematic slippage
- **Risk unmanaged** — position sizing disconnected from volatility, no circuit breakers, catastrophic drawdowns
- **Untested** — no unit tests, no edge case coverage, no formal validation pipeline
- **Opaque** — decisions can't be audited, no explainability for why a trade was taken or rejected

## Success Criteria

### Minimum Viable Product (MVP) — production-ready trading system
- [ ] Feature pipeline with **no look-ahead bias**: rolling windows only, no global statistics
- [ ] Backtester with **next-bar execution** (open of next bar, not close of current bar)
- [ ] Risk supervisor integrated into live trading: position limits, stop-loss enforcement, drawdown circuit breaker
- [ ] **All tests pass** (pytest), ≥80% coverage on core modules
- [ ] CI pipeline: lint → tests → backtest smoke test on every push
- [ ] Paper trading for ≥2 weeks with consistent results before any live deployment
- [ ] Full audit trail: every trade decision logged with timestamp, features used, model output, risk check result

### Version 1.0 — live readiness
- [ ] DREAMER / PPO model trained on out-of-sample data, validated with walk-forward analysis
- [ ] Live monitoring dashboard with real-time P&L, open positions, risk metrics
- [ ] Alerting on: drawdown threshold breach, unusual loss streak, model confidence drop
- [ ] Backtest results published with full transparency: methodology, assumptions, known limitations

### Version 2.0 — advanced
- [ ] Multi-asset support (extending beyond XAU/USD)
- [ ] Adaptive position sizing based on realized volatility
- [ ] Meta-learning: model adapts to regime changes overnight
- [ ] Ensemble of models with disagreement-based position reduction

## Non-Goals

- **NOT** a get-rich-quick tool. Transparency and correctness are the brand.
- **NOT** supporting manual strategy override (removes auditability).
- **NOT** trading assets other than XAU/USD in v1.
- **NOT** collecting user funds or operating as a financial service. Developer tool only.

## Key Architectural Constraints

1. **No look-ahead bias**: any feature using `mean()`, `std()`, `min()`, `max()` must use a rolling window bounded at the current time step. Global statistics across the entire dataset are forbidden.
2. **Next-bar execution**: model predicts action at bar `t`; execution fills at open of bar `t+1`. Backtest must mirror this exactly.
3. **Risk before execution**: every trade decision passes through RiskSupervisor. Execution is rejected if risk check fails. This must be wired into both backtester and live trading.
4. **Testability**: every non-trivial function must have a unit test. Integration tests cover the full pipeline (data → features → model → risk → execution).
5. **Reproducibility**: seeds fixed, data versions tracked, experiment results versioned.

## Project Structure

```
tradingbot-fixed/
├── features/              # Feature engineering (no global stats!)
│   ├── make_features.py   # Main feature pipeline
│   ├── microstructure_features.py
│   ├── macro_features.py
│   └── ...
├── backtest/
│   └── backtest_engine.py # Correct next-bar execution
├── env/
│   └── xauusd_env.py      # RL environment
├── models/
│   ├── risk_supervisor.py # Risk management gate
│   ├── dreamer_agent.py
│   └── ...
├── live_trade_mt5.py      # Live trading entry point
├── data/
│   └── load_data.py       # Data loading + cleaning
├── tests/                 # Unit tests for all core modules
├── eval/                  # Model evaluation + validation
└── kanban_worker.py       # Autonomous worker
```
