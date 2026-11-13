"""WP1b: how much of real price stress does weather stress explain? Regression on ENTSO-E day-ahead prices 2015-2025.

Daily log price ratio (price / centred 31-day median, which removes fuel and carbon price levels) per bidding zone,
October-March, regressed on the anomaly of the weather-only stress index (today's fleet, WP1) with month and
weekday effects; logistic regression of European price-stress days on the same index. Standard errors are HAC
(Newey-West, 7 lags) because both series are autocorrelated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stress import obs
from stress.paths import DERIVED, RESULTS

OUT = RESULTS / "wp1"
ZONES = ["DE", "FR", "NL", "BE", "AT", "CH", "PL", "CZ", "DK", "IT", "ES"]


def hac_ols(y, X, lags=7):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    n = len(y)
    xu = X * u[:, None]
    S = xu.T @ xu
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = xu[L:].T @ xu[:-L]
        S += w * (G + G.T)
    XtX_inv = np.linalg.inv(X.T @ X)
    V = XtX_inv @ S @ XtX_inv
    r2 = 1 - u.var() / y.var()
    return beta, np.sqrt(np.diag(V)), r2


def logit(y, X, iters=50):
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ b))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None])
        b = b + np.linalg.solve(H + 1e-9 * np.eye(len(b)), X.T @ (y - p))
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return b, se


def main():
    idx = pd.read_parquet(DERIVED / "era5_stress_index_daily.parquet")["stress_index_GW"].loc["2015":"2025"]
    anom = idx - idx.rolling(365, center=True, min_periods=180).mean()
    p = obs.entsoe_panel("price")[ZONES].resample("1D").mean()
    med = p.rolling(31, center=True, min_periods=15).median()
    lr = np.log((p / med.where(med > 5)).clip(lower=0.05))
    rows = []
    for z in ZONES:
        d = pd.concat({"y": lr[z], "x": anom}, axis=1).dropna()
        d = d[d.index.month.isin([10, 11, 12, 1, 2, 3])]
        X = np.column_stack([np.ones(len(d)), d["x"] / 10.0] +
                            [(d.index.month == m).astype(float) for m in (11, 12, 1, 2, 3)] +
                            [(d.index.day_of_week == k).astype(float) for k in range(1, 7)])
        b, se, r2 = hac_ols(d["y"].to_numpy(), X)
        rows.append({"zone": z, "days": len(d), "pct_price_per_10GW": 100 * (np.exp(b[1]) - 1),
                     "t_hac": b[1] / se[1], "r2": r2})
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "price_regression.csv", index=False)
    # logistic: European price-stress day (>= 4 of 11 zones at >= 1.5 x median)
    eu = ((p / med.where(med > 5)) >= 1.5).sum(axis=1) >= 4
    d = pd.concat({"y": eu.astype(float), "x": anom}, axis=1).dropna()
    d = d[d.index.month.isin([10, 11, 12, 1, 2, 3])]
    X = np.column_stack([np.ones(len(d)), d["x"] / 10.0])
    b, se = logit(d["y"].to_numpy(), X)
    res = {"logit_odds_ratio_per_10GW": float(np.exp(b[1])), "z": float(b[1] / se[1]), "days": len(d),
           "events": int(d["y"].sum())}
    pd.Series(res).to_csv(OUT / "price_logit.csv", header=["value"])
    print(tab.round(2).to_string())
    print(res)


if __name__ == "__main__":
    main()
