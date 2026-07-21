# Trading Bot — Product Owner Decisions

## Vision Alignment

This project is a **developer tool and research project**, not a financial product. Correctness is the primary success metric; profitability is secondary. See GOAL.md for full vision and constraints.

## Competitor Landscape

| Approach | Flaw |
|---|---|
| Retail trading bots (MetaTrader EAs) | Hardcoded rules, no learning, curve-fitted, blow up |
| Generic ML trading systems | Look-ahead bias in features, no risk management, untested |
| DRL agents from papers | Trained on unrealistic environments, no execution realism |
| **Our approach** | Discipline-first: no look-ahead bias, next-bar execution, risk supervisor always on, fully tested |

## Pricing / Distribution

- Open source (MIT license)
- Not monetized — educational/research purpose
- Public repo, public transparency on failures and methodology

## Scope Decisions

### In Scope (v1)
- XAU/USD on MetaTrader 5 (MT5) platform
- DREAMER + PPO agents trained offline
- Offline backtesting with correct execution model
- Paper trading via MT5 demo account
- Risk supervisor: position sizing, stop-loss, drawdown circuit breaker
- CI: lint → tests → backtest smoke test

### Out of Scope
- Live trading with real money until 2+ weeks paper trading validates
- Any asset other than XAU/USD
- Manual strategy intervention
- User-facing product (broker integration, web dashboard for clients)
- Proprietary model weights (model architecture is open, weights can be released)

## MVP Definition

**Must ship before any live trading:**
1. Feature pipeline passes: no global statistics, rolling windows only, all features documented
2. Backtester passes: next-bar execution, risk check on every trade, full audit log
3. Risk supervisor: integrated into both backtester and live_trade_mt5.py
4. Tests: pytest suite passes, ≥80% coverage on features/, backtest/, models/, env/
5. CI: GitHub Actions pipeline green on main
6. Documentation: GOAL.md complete, QUALITY_BAR.md complete, all public functions docstring'd
7. Paper trading: 7-day minimum on MT5 demo with results logged

## MVP Must NOT Ship With
- Live trading with real funds
- Unvalidated model weights
- Features without rolling-window implementation
- Backtester using bar-close execution
- Risk supervisor disconnected from live_trade_mt5.py

## Technical Decisions

| Decision | Rationale |
|---|---|
| MT5 as broker interface | Industry standard, supports demo accounts, Python API available |
| DREAMER as primary agent | State-of-the-art for continuous control, handles partial observability |
| PPO as baseline | Faster training, easier to validate, good comparison point |
| Rolling-window normalization only | Prevents look-ahead bias, aligns with GOAL.md constraint #1 |
| Risk supervisor as independent gate | Separates model prediction from risk enforcement; model can be wrong, risk must always be right |
| pytest for testing | Industry standard, good pytest-cov integration, fast |
| GitHub Actions CI | Free for public repos, parallel jobs for lint/test/backtest |

## Current State

As of project take-over:
- Codebase exists with core modules in place
- Several critical bugs documented in initial task list:
  - T001: Feature normalization uses global mean/std (look-ahead bias)
  - T002: Backtester executes on bar close (wrong execution model)
  - T003: Risk supervisor not wired into live_trade_mt5.py
  - T004: Candle detection broken, duplicate orders possible
  - T005: Environment flat penalty biasing model toward inaction
  - T006: No unit tests for core components
- Tests directory exists but not comprehensive
- No CI pipeline
- No formal docs beyond README

## Priority Order

1. Fix look-ahead bias (T001) — this makes all existing backtest results invalid
2. Fix backtester timing (T002) — makes backtest results misleading
3. Wire risk supervisor (T003) — required for any live trading
4. Fix candle detection (T004) — prevents duplicate orders in live trading
5. Remove flat penalty (T005) — unbiases model training
6. Add tests (T006) — required before CI, required before live trading
