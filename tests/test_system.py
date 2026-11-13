import numpy as np
import pandas as pd

from stress import system as sy


def test_generation_scales_to_energy_target():
    idx = pd.date_range("2000-01-01", periods=100, freq="1h")
    rng = np.random.default_rng(1)
    cf = {"wind_on": pd.DataFrame({"DE": rng.uniform(0, 1, 100)}, idx),
          "pv": pd.DataFrame({"DE": rng.uniform(0, 0.5, 100)}, idx)}
    ref = {k: v.mean() for k, v in cf.items()}
    fl = sy.Fleet("t", pd.DataFrame({"wind_on": [30.0], "wind_off": [0.0], "pv": [10.0]}, index=["DE"]))
    g = sy.generation(fl, cf, ref)
    assert abs(g["DE"].mean() - 40.0) < 1e-6


def test_net_load_subtracts_generation_and_ror():
    idx = pd.date_range("2000-01-01", periods=3, freq="1h")
    d = pd.DataFrame({"DE": [50.0, 60, 70]}, idx)
    g = pd.DataFrame({"DE": [10.0, 0, 20]}, idx)
    r = pd.DataFrame({"DE": [1.0, 1, 1]}, idx)
    assert list(sy.net_load(d, g, r)["DE"]) == [39, 59, 49]


def test_scenario_fleets_vre_share():
    ann = pd.Series({"DE": 60.0, "AT": 8.0})
    f = sy.scenario_fleets(ann, pd.DataFrame(0, index=ann.index, columns=list(sy.VRE)), {"DE"})
    e = f["high_wind"].energy
    assert np.allclose(e.sum(axis=1), 0.8 * ann)
    assert e.loc["AT", "wind_off"] == 0
