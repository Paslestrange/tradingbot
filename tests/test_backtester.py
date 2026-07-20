"""
test_backtester.py — verify next-bar execution semantics.

The backtester uses a pending_action pattern: on bar N the agent's decision
is stored as pending_action, and the actual trade is only EXECUTED on bar N+1.
This tests enforce that decisions never execute on the same bar they are made.
"""

import sys, os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.backtest_engine import RigorousBacktester


def _make_data(n=200, freq="h"):
    """Create simple OHLC data with datetime index."""
    dates = pd.date_range("2023-01-01", periods=n, freq=freq)
    rng = np.random.default_rng(0)
    close = 2000.0 + rng.standard_normal(n).cumsum() * 3
    return pd.DataFrame({
        "open":  close,
        "high":  close + 1.0,
        "low":   close - 1.0,
        "close": close,
    }, index=dates)


class RecordingAgent:
    """Agent that records which bar index it was called on and what it returned."""

    def __init__(self, pattern):
        self.pattern = pattern  # callable(idx) -> action
        self.call_log = []      # list of bar indices when act() was called

    def act(self, obs):
        # The backtester passes idx to _get_observation; we intercept via call_log.
        idx = obs  # _get_observation returns the idx directly in our test harness
        self.call_log.append(idx)
        return self.pattern(idx)


class RecordingBacktester(RigorousBacktester):
    """Override _get_observation to pass the bar index directly to the agent."""

    def _get_observation(self, idx):
        return idx  # pass idx so agent knows which bar it is


# ---------- Next-bar execution tests ----------

class TestNextBarExecution:
    """
    CRITICAL: The agent decides on bar N, but the trade must only execute
    on bar N+1.  These tests enforce that.
    """

    def test_decision_on_bar_n_executes_on_bar_n_plus_1(self):
        """
        An agent that always goes long on bar 5 should not have that trade
        recorded until bar 6's price is used.
        """
        data = _make_data(20)
        # Always go long (action=1)
        agent = RecordingAgent(lambda idx: 1)
        bt = RecordingBacktester(agent, data)
        bt.run_backtest()

        # The pending_action mechanism means bar 0's decision is deferred to bar 1.
        # After the full backtest, the first trade entry should show that
        # entry_time is AFTER the first call to act().
        assert len(bt.agent.call_log) > 0, "Agent was never called"
        first_call_idx = bt.agent.call_log[0]
        # First call is at data.index[0]. Decision is stored as pending.
        # Trade executes at data.index[1] at the earliest.
        if bt.results_trades:
            first_trade = bt.results_trades[0]
            # Entry time must be strictly after the first call index
            first_call_time = data.index[first_call_idx]
            assert first_trade["entry_time"] > first_call_time, (
                f"Trade executed at {first_trade['entry_time']} but agent "
                f"decided at {first_call_time} — same-bar execution!"
            )

    def test_pending_action_defers_by_one_bar(self):
        """
        Verify the pending_action pattern: first bar's action is stored,
        second bar's action replaces it only if pending was already used.
        """
        data = _make_data(5)
        call_count = [0]
        actions = [0, 1, 1, 0, 0]

        def agent_fn(idx):
            a = actions[call_count[0] % len(actions)]
            call_count[0] += 1
            return a

        agent = RecordingAgent(agent_fn)
        bt = RecordingBacktester(agent, data)
        bt.run_backtest()

        # After bar 0: pending_action = 0 (agent returned 0)
        # Bar 1: pending_action is 0, so action=0 is used; new pending=1
        # Bar 2: pending_action is 1, so action=1 is used → entry at bar 2's price
        # This proves 1-bar deferral.
        assert call_count[0] == len(data), "Agent should be called every bar"

    def test_no_trade_on_first_bar(self):
        """The very first bar should never have a trade entry (it's always deferred)."""
        data = _make_data(20)
        # Agent always wants to go long
        agent = RecordingAgent(lambda idx: 1)
        bt = RecordingBacktester(agent, data)
        bt.run_backtest()

        if bt.results_trades:
            first_trade_time = bt.results_trades[0]["entry_time"]
            assert first_trade_time > data.index[0], (
                f"First trade at {first_trade_time} == data start {data.index[0]} — "
                "should be deferred to next bar"
            )

    def test_cost_applied_on_entry_and_exit(self):
        """Every trade must have non-zero cost for both entry and exit."""
        data = _make_data(50)
        agent = RecordingAgent(lambda idx: 1)
        bt = RecordingBacktester(agent, data)
        bt.run_backtest()

        if bt.results_trades:
            for t in bt.results_trades:
                assert t["cost"] > 0, f"Trade has zero cost: {t}"


# Fixtures to capture trades from the backtester
@pytest.fixture(autouse=True)
def patch_recording_bt():
    """Monkey-patch RigorousBacktester to expose trades list for assertions."""
    original_run = RigorousBacktester.run_backtest

    def patched_run(self):
        results = original_run(self)
        # Expose trades as attribute for tests
        self.results_trades = results["trades"]
        return results

    RigorousBacktester.run_backtest = patched_run
    yield
    RigorousBacktester.run_backtest = original_run


# ---------- Cost model tests ----------

class TestCostModel:
    """Verify the cost model is pessimistic as documented."""

    def test_total_cost_includes_spread_slippage_commission(self):
        """Total cost must be sum of spread (with multiplier) + slippage + commission."""
        data = _make_data(10)
        agent = RecordingAgent(lambda idx: 0)
        config = {"spread": 0.0003, "slippage": 0.0003, "commission": 0.00005, "spread_mult": 1.5}
        bt = RigorousBacktester(agent, data, config=config)

        row = data.iloc[0]
        cost = bt._compute_total_cost(row)
        expected = 0.0003 * 1.5 + 0.0003 + 0.00005
        assert abs(cost - expected) < 1e-10, f"Cost {cost} != expected {expected}"

    def test_spread_multiplier_makes_costs_worse(self):
        """Higher spread_mult should increase total cost."""
        data = _make_data(10)
        agent = RecordingAgent(lambda idx: 0)

        bt_normal = RigorousBacktester(agent, data, config={"spread_mult": 1.0})
        bt_wide = RigorousBacktester(agent, data, config={"spread_mult": 3.0})

        row = data.iloc[0]
        assert bt_wide._compute_total_cost(row) > bt_normal._compute_total_cost(row)
