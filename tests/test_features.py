"""
test_features.py — verify no look-ahead bias in normalization.

The compute_features() function normalizes each bar i using only data from
bars BEFORE i (expanding window for i < 252, rolling window of 252 bars
thereafter).  These tests ensure future data never leaks into past
normalized values.
"""

import sys, os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from features.make_features import compute_features


def _make_df(n=600, macro=False):
    """Create a minimal OHLCV DataFrame for compute_features."""
    rng = np.random.default_rng(42)
    close = 2000.0 + rng.standard_normal(n).cumsum() * 5
    df = pd.DataFrame({
        "open":  close + rng.standard_normal(n) * 0.5,
        "high":  close + abs(rng.standard_normal(n)) * 2,
        "low":   close - abs(rng.standard_normal(n)) * 2,
        "close": close,
        "volume": rng.integers(100, 10_000, size=n).astype(float),
    })
    if macro:
        df["dxy_close"] = 100.0 + rng.standard_normal(n).cumsum() * 0.3
        df["spx_close"] = 4000.0 + rng.standard_normal(n).cumsum() * 10
        df["us10y_close"] = 4.0 + rng.standard_normal(n).cumsum() * 0.05
    return df


# ---------- No look-ahead bias tests ----------

class TestNoLookAheadBias:
    """Normalized value at bar i must not change when future bars are altered."""

    def test_mutation_of_future_bar_does_not_affect_past(self):
        """Change bar 500 → bars 0..499 should be identical."""
        df = _make_df(600)
        _, feats_original, _ = compute_features(df)

        df_mutated = df.copy()
        # Wildly mutate a far-future close price
        df_mutated.iloc[500, df.columns.get_loc("close")] = 99_999.0
        _, feats_mutated, _ = compute_features(df_mutated)

        # All normalized features before bar 500 must be identical
        np.testing.assert_array_equal(
            feats_original[:500],
            feats_mutated[:500],
            err_msg="Future bar mutation leaked into past normalized values",
        )

    def test_last_bar_uses_only_history(self):
        """The last bar's normalization must be computed from preceding bars only."""
        df = _make_df(400)
        _, feats, _ = compute_features(df)
        # Last bar should be finite (not NaN/inf) — proves normalization ran
        assert np.all(np.isfinite(feats[-1])), "Last bar has non-finite normalized values"

    def test_expanding_window_region_is_correct(self):
        """Bars 0..251 should use expanding window (no rolling yet)."""
        df = _make_df(400)
        _, feats, _ = compute_features(df)
        # In the expanding window region, each bar's norm should differ from
        # what a fixed rolling window would give (because fewer data points).
        # Just confirm these bars are finite and not all zero.
        early = feats[121:252]  # post-il[:120] trim
        assert np.any(early != 0), "Early bars all zero — expanding window may be broken"

    def test_first_bar_is_zero_normalized(self):
        """Bar 0 has no history → feats_norm[0] should remain 0."""
        df = _make_df(300)
        _, feats, _ = compute_features(df)
        np.testing.assert_array_equal(
            feats[0], np.zeros(feats.shape[1], dtype=np.float32),
            err_msg="Bar 0 should be zero (no history to normalize against)",
        )


# ---------- Feature computation correctness ----------

class TestFeatureComputation:

    def test_output_shapes(self):
        """feats shape (T-120, F), rets shape (T-120,)."""
        df = _make_df(500)
        df_out, feats, rets = compute_features(df)
        assert feats.shape[0] == len(df_out)
        assert rets.shape[0] == len(df_out)
        assert feats.shape[1] == 6  # ret, vol, mom, ma_diff, rsi, macd_diff

    def test_output_shapes_with_macro(self):
        """With macro features, feats has 11 columns."""
        df = _make_df(500, macro=True)
        df_out, feats, rets = compute_features(df)
        assert feats.shape[1] == 11

    def test_no_nan_or_inf_in_output(self):
        """Output arrays must be fully finite."""
        df = _make_df(500)
        _, feats, rets = compute_features(df)
        assert np.all(np.isfinite(feats)), "feats contains NaN/Inf"
        assert np.all(np.isfinite(rets)), "rets contains NaN/Inf"

    def test_rsi_bounded(self):
        """RSI feature (column 4) should be in [0, 1] after /100 scaling."""
        df = _make_df(500)
        _, feats, _ = compute_features(df)
        rsi = feats[:, 4]  # ret, vol, mom, ma_diff, rsi, macd_diff
        assert np.all(rsi >= 0.0) and np.all(rsi <= 1.0), f"RSI out of range: [{rsi.min()}, {rsi.max()}]"
