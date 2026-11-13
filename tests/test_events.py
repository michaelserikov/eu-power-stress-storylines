import gzip

import numpy as np
import pandas as pd
import pytest

from stress import events as ev
from stress import obs


def series(vals, start="2020-01-01", freq="1h"):
    return pd.Series(vals, pd.date_range(start, periods=len(vals), freq=freq), dtype=float)


def test_runs_and_merge():
    m = pd.Series([0, 1, 1, 0, 1, 0, 0, 0, 1], dtype=bool)
    r = ev.runs(m)
    assert list(zip(r.i0, r.i1)) == [(1, 3), (4, 5), (8, 9)]
    r = ev.runs(m, merge_gap=1)
    assert list(zip(r.i0, r.i1)) == [(1, 5), (8, 9)]
    assert len(ev.runs(m, min_len=2)) == 1


def test_exceedance_severity_and_duration():
    x = series([0, 5, 7, 0, 4, 0])
    e = ev.exceedance_events(x, 3)
    assert list(e.duration) == [2, 1]
    assert e.severity.iloc[0] == pytest.approx(2 + 4)
    assert e.peak.iloc[0] == 7


def test_low_events():
    x = series([1, 0.1, 0.2, 1, 0.0])
    e = ev.low_events(x, 0.5)
    assert list(e.duration) == [2, 1]
    assert e.severity.iloc[0] == pytest.approx(0.4 + 0.3)


def test_gpd_return_levels_increase():
    rng = np.random.default_rng(0)
    s = rng.exponential(10, 400)
    rl = ev.gpd_return_levels(s, n_years=20)
    assert rl.is_monotonic_increasing
    assert rl[2] > np.quantile(s, 0.7)


def test_hit_rate_tolerance():
    idx = pd.date_range("2024-01-01", periods=10, freq="1D")
    obs_ = pd.Series(False, idx)
    obs_.iloc[[2, 7]] = True
    pred = pd.Series(False, idx)
    pred.iloc[[3, 5]] = True
    h = ev.hit_rate(pred, obs_, tolerance_days=1)
    assert h["hit_rate"] == pytest.approx(0.5)
    assert h["false_alarm_ratio"] == pytest.approx(0.5)


def test_co_occurrence_diagonal_is_one():
    f = pd.DataFrame({"A": [1, 1, 0, 0], "B": [1, 0, 0, 1]}, dtype=bool)
    co = ev.co_occurrence(f)
    assert co.loc["A", "A"] == 1 and co.loc["A", "B"] == pytest.approx(0.5)


XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
<TimeSeries><Period><timeInterval><start>2024-01-01T00:00Z</start><end>2024-01-01T02:00Z</end></timeInterval>
<resolution>PT15M</resolution>
<Point><position>1</position><price.amount>10</price.amount></Point>
<Point><position>3</position><price.amount>30</price.amount></Point>
<Point><position>5</position><price.amount>50</price.amount></Point>
</Period></TimeSeries></Publication_MarketDocument>"""


def test_parse_entsoe_curve_a03(tmp_path):
    p = tmp_path / "x.xml.gz"
    p.write_bytes(gzip.compress(XML.encode()))
    s = obs.parse_entsoe(p)
    # 15-min points 10,10,30,30 | 50,50,50,50 (A03: missing positions repeat the previous value)
    assert s.iloc[0] == pytest.approx(20)
    assert s.iloc[1] == pytest.approx(50)
