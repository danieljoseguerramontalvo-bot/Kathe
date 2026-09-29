"""Indicators vs hand-computed values (MT5 definitions) and truncation invariance."""
import numpy as np
import pytest

from kq.indicators import (adx_mt5, atr_mt5, efficiency_ratio, ema, rolling_max_prev, rolling_min_prev,
                           rolling_percentile_rank, rsi_wilder, sma, true_range)


def test_ema_mt5_first_value_is_first_price():
    x = [1.0, 2.0, 3.0, 4.0]
    # n = 3 -> alpha = 0.5
    np.testing.assert_allclose(ema(x, 3), [1.0, 1.5, 2.25, 3.125])


def test_ema_skips_leading_nans():
    out = ema([np.nan, 2.0, 4.0], 3)
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [2.0, 3.0])


def test_atr_is_simple_average_of_true_range_not_wilder():
    h = [10, 11, 12, 11, 13]
    l = [9, 10, 10, 9, 11]
    c = [9.5, 10.5, 11, 10, 12]
    tr = true_range(h, l, c)
    np.testing.assert_allclose(tr[1:], [1.5, 2.0, 2.0, 3.0])   # max(h, pc) - min(l, pc)
    atr = atr_mt5(h, l, c, 3)
    assert np.isnan(atr[:3]).all()
    assert atr[3] == pytest.approx((1.5 + 2 + 2) / 3)
    assert atr[4] == pytest.approx((2 + 2 + 3) / 3)
    wilder = (atr[3] * 2 + 3) / 3
    assert atr[4] != pytest.approx(wilder)


def test_rsi_wilder_hand_computed():
    c = [10, 11, 10.5, 11.5, 11]
    r = rsi_wilder(c, 2)
    assert np.isnan(r[:2]).all()
    # seed: avg gain (1+0)/2 = 0.5, avg loss (0+0.5)/2 = 0.25 -> RS 2
    assert r[2] == pytest.approx(100 - 100 / 3)
    # gain (0.5*1 + 1)/2 = 0.75, loss (0.25*1 + 0)/2 = 0.125 -> RS 6
    assert r[3] == pytest.approx(100 - 100 / 7)
    # gain 0.375, loss 0.3125 -> RS 1.2
    assert r[4] == pytest.approx(100 - 100 / 2.2)


def test_rsi_edge_cases():
    assert rsi_wilder([1, 2, 3, 4], 2)[-1] == 100.0
    assert rsi_wilder([5, 5, 5, 5], 2)[-1] == 50.0


def test_adx_mt5_hand_computed():
    h = [10, 11, 11.5, 11]
    l = [9, 9.5, 10.5, 10]
    c = [9.5, 10.5, 11, 10.2]
    a = 2 / 3                                  # alpha for n = 2
    # bar 1: +DM 1, -DM 0, TR 1.5 -> pdi 66.67, ndi 0
    p1 = 100 * 1 / 1.5 * a
    n1 = 0.0
    x1 = 100.0 * a                              # DX = 100
    # bar 2: +DM 0.5, -DM 0, TR 1 -> pdi 50
    p2 = 50 * a + p1 * (1 - a)
    n2 = 0.0
    x2 = 100 * a + x1 * (1 - a)
    # bar 3: +DM 0 (negative), -DM 0.5, TR 1 -> ndi 50
    p3 = 0 * a + p2 * (1 - a)
    n3 = 50 * a + n2 * (1 - a)
    dx3 = 100 * abs(p3 - n3) / (p3 + n3)
    x3 = dx3 * a + x2 * (1 - a)
    adx, pdi, ndi = adx_mt5(h, l, c, 2)
    np.testing.assert_allclose(pdi[1:], [p1, p2, p3])
    np.testing.assert_allclose(ndi[1:], [n1, n2, n3])
    np.testing.assert_allclose(adx[1:], [x1, x2, x3])
    assert dx3 == pytest.approx(35.0)
    assert adx[3] == pytest.approx(52.962962962963)


def test_adx_equal_directional_moves_cancel():
    # +DM = -DM = 1 -> both set to 0 -> DI stay 0, DX 0
    adx, pdi, ndi = adx_mt5([10, 11], [9, 8], [9.5, 9.5], 14)
    assert pdi[1] == 0 and ndi[1] == 0 and adx[1] == 0


def test_efficiency_ratio_and_percentile_rank():
    er = efficiency_ratio([1, 2, 3, 2, 3], 2)
    assert np.isnan(er[:2]).all()
    np.testing.assert_allclose(er[2:], [1.0, 0.0, 0.0])
    pr = rolling_percentile_rank([1, 2, 3, 4, 2], 3)
    assert np.isnan(pr[:3]).all()
    assert pr[3] == pytest.approx(1.0)          # 4 above [1,2,3]
    assert pr[4] == pytest.approx(0.5 / 3)      # 2 vs [2,3,4]: one tie


def test_donchian_uses_previous_bars_only():
    h = np.array([1, 5, 2, 3, 4], float)
    mx = rolling_max_prev(h, 2)
    np.testing.assert_allclose(mx[2:], [5, 5, 3])
    mn = rolling_min_prev(h, 2)
    np.testing.assert_allclose(mn[2:], [1, 2, 2])
    np.testing.assert_allclose(sma([1, 2, 3, 4], 2)[1:], [1.5, 2.5, 3.5])


@pytest.mark.parametrize("fn", [
    lambda h, l, c: ema(c, 10),
    lambda h, l, c: atr_mt5(h, l, c, 14),
    lambda h, l, c: rsi_wilder(c, 2),
    lambda h, l, c: adx_mt5(h, l, c, 14)[0],
    lambda h, l, c: efficiency_ratio(c, 20),
    lambda h, l, c: rolling_percentile_rank(atr_mt5(h, l, c, 14), 50),
    lambda h, l, c: rolling_max_prev(h, 20),
])
def test_indicators_are_truncation_invariant(fn):
    """Value at i computed on data[:k] equals the value on the full series (no look-ahead)."""
    rng = np.random.default_rng(3)
    c = 2000 + np.cumsum(rng.normal(0, 2, 400))
    h = c + rng.random(400) * 2
    l = c - rng.random(400) * 2
    full = fn(h, l, c)
    for k in (60, 150, 399):
        part = fn(h[:k], l[:k], c[:k])
        np.testing.assert_allclose(part, full[:k], equal_nan=True)
