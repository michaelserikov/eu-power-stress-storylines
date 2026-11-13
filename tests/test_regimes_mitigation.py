import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from stress import regimes as rg


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_sequent_peak_simple():
    w = load_script("wp5_mitigation")
    x = np.array([0, 10, 10, 0, 0], float)  # firm 5: deficit 5+5, recharge 0.8*5 per hour after
    e, p = w.sequent_peak(x, 5.0, eta=0.8)
    assert e == 10 and p == 5


def test_flex_peak_flattens():
    w = load_script("wp5_mitigation")
    idx = pd.date_range("2020-01-01", periods=24, freq="1h")
    x = pd.Series(np.r_[np.full(23, 10.0), 34.0], idx)
    assert w.flex_peak(x, 0.0) == 34.0
    assert w.flex_peak(x, 0.5) < 12.0


def test_standardized_keeps_future_shift():
    idx = pd.date_range("2000-01-01", periods=730, freq="1D")
    rng = np.random.default_rng(0)
    ref = pd.DataFrame({"a": rng.normal(0, 1, 730)}, idx)
    fut = ref + 1.0
    z = rg.standardized(fut, ref)
    assert z["a"].mean() > 0.7


def test_kmeans_separates_two_patterns():
    lat = np.linspace(30, 70, 5)
    a = np.zeros((40, 5, 6))
    a[:20, :2] = 5
    a[20:, 3:] = 5
    a += np.random.default_rng(1).normal(0, 0.1, a.shape)
    labels, maps, _ = rg.eof_kmeans(a, lat, n_pcs=3, k=2)
    assert len(set(labels[:20])) == 1 and len(set(labels[20:])) == 1 and labels[0] != labels[-1]
