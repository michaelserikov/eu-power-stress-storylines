"""WP5: mitigation options for stressful periods, present vs SSP3-7.0, balanced and high-wind net-zero fleets.

1. Firm capacity: European net load P99.9 and maximum (what backup must cover without other options).
2. Storage: for firm capacity F (set at today's P95, P98 of net load), the storage energy needed so that net load
   never exceeds F, by sequent peak (storage recharged from surplus below F at 80% round trip); the implied
   duration E/P with P the largest excess. Computed over each 20-year period and realization.
3. Transmission and pooling: stress energy above each country's own P98 when countries cover themselves, against a
   European copper plate (sum of national net loads above the European P98 scaled to the same total firm capacity),
   and regional pools (North-West, Centre-East, South, Nordic-Baltic).
4. Demand flexibility: a share of daily demand moved within the day (water filling to the daily mean) and the
   remaining firm need.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stress import system as sy
from stress.paths import FIGURES, RESULTS
from stress.pipeline import PERIODS, REALS, compute_netload, demand_from, load_inputs

OUT = RESULTS / "wp5"
OUT.mkdir(parents=True, exist_ok=True)
POOLS = {"North-West": ["BE", "DE", "FR", "GB", "IE", "NL", "DK", "AT", "CH"],
         "Centre-East": ["CZ", "PL", "SK", "HU", "SI", "HR", "RO", "BG", "RS", "BA", "ME", "MK", "AL"],
         "South": ["ES", "PT", "IT", "GR"], "Nordic-Baltic": ["NO", "SE", "FI", "EE", "LV", "LT"]}


def sequent_peak(x: np.ndarray, firm: float, eta: float = 0.8) -> tuple[float, float]:
    """Storage energy (GWh) needed to keep x <= firm; charging from (firm - x) when positive, at round-trip eta."""
    deficit, need = 0.0, 0.0
    for v in x:
        if v > firm:
            deficit += v - firm
        else:
            deficit = max(0.0, deficit - eta * (firm - v))
        need = max(need, deficit)
    return need, float(np.max(x) - firm)


def flex_peak(x: pd.Series, share: float) -> float:
    """Peak after moving up to `share` of each day's energy from the day's highest hours to its lowest (flattening)."""
    out = []
    for _, d in x.groupby(x.index.normalize()):
        v = np.sort(d.to_numpy())[::-1]
        budget = share * np.abs(v).sum()
        # lower the top until the cut energy reaches the budget or the day is flat
        lo, hi = v.mean(), v[0]
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            cut = np.clip(v - mid, 0, None).sum()
            if cut > budget:
                lo = mid
            else:
                hi = mid
        out.append(hi)
    return float(np.max(out))


def main():
    profile, cs, data = load_inputs()
    has_off = set(data[("A", "historical")]["cf"]["wind_off"].columns)
    ann = demand_from(data[("A", "historical")], profile, "heat").mean()
    fleets = sy.scenario_fleets(ann, pd.DataFrame(0, index=ann.index, columns=list(sy.VRE)), has_off)
    fleets = {k: fleets[k] for k in ("balanced", "high_wind")}
    nl = compute_netload(profile, cs, data, fleets, "heat")
    rows, pool_rows, flex_rows = [], [], []
    for fname in fleets:
        eu = {(r, p): nl[(fname, r, p)].sum(axis=1) for r in REALS for p in PERIODS}
        hist = pd.concat([eu[(r, "historical")] for r in REALS])
        firms = {"P95": hist.quantile(0.95), "P98": hist.quantile(0.98)}
        cthr = pd.concat([nl[(fname, r, "historical")] for r in REALS]).quantile(0.98)
        for r in REALS:
            for p in PERIODS:
                x = eu[(r, p)]
                yrs = len(x) / 8760
                row = {"fleet": fname, "real": r, "period": p, "p99_9_GW": x.quantile(0.999), "max_GW": x.max()}
                for k, F in firms.items():
                    e, pw = sequent_peak(x.to_numpy(), F)
                    row[f"storage_GWh_firm{k}"] = e
                    row[f"storage_GW_firm{k}"] = pw
                    row[f"duration_h_firm{k}"] = e / pw if pw > 0 else 0
                rows.append(row)
                # pooling: energy above thresholds, national self-reliance vs pools vs Europe
                n = nl[(fname, r, p)]
                nat = (n - cthr).clip(lower=0).sum().sum() / yrs / 1000
                firm_total = cthr.sum()
                pooled = {}
                for pool, members in POOLS.items():
                    mm = [c for c in members if c in n]
                    pooled[pool] = (n[mm].sum(axis=1) - cthr[mm].sum()).clip(lower=0).sum() / yrs / 1000
                eu_ex = (x - firm_total).clip(lower=0).sum() / yrs / 1000
                pool_rows.append({"fleet": fname, "real": r, "period": p, "national_TWh_per_year": nat,
                                  "regional_pools_TWh_per_year": sum(pooled.values()), "europe_TWh_per_year": eu_ex,
                                  "sum_of_national_peaks_GW": n.max().sum(), "european_peak_GW": x.max()})
                if r == "A":
                    for share in (0.0, 0.05, 0.10):
                        flex_rows.append({"fleet": fname, "period": p, "flex_share": share, "peak_GW": flex_peak(x, share)})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "firm_and_storage.csv", index=False)
    pl = pd.DataFrame(pool_rows)
    pl.to_csv(OUT / "pooling.csv", index=False)
    fx = pd.DataFrame(flex_rows)
    fx.to_csv(OUT / "flexibility.csv", index=False)
    print(df.drop(columns="real").groupby(["fleet", "period"]).agg(["mean", "min", "max"]).round(0).T.to_string())
    print(pl.groupby(["fleet", "period"]).mean(numeric_only=True).round(1).to_string())
    print(fx.round(1).to_string())
    plot(df, pl)


def plot(df, pl):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for i, fname in enumerate(["balanced", "high_wind"]):
        s = df[df.fleet == fname]
        for j, p in enumerate(PERIODS):
            v = s[s.period == p]["storage_GWh_firmP95"] / 1000
            axes[0].scatter(np.full(len(v), i * 3 + j), v, color=["tab:blue", "tab:red"][j],
                            label=p if i == 0 else None)
    axes[0].set_xticks([0.5, 3.5], ["balanced", "high wind"])
    axes[0].set_ylabel("storage energy to hold net load at today's P95 (TWh)")
    axes[0].legend(fontsize=8)
    g = pl.groupby(["fleet", "period"]).mean(numeric_only=True)
    labels = [f"{f}\n{p}" for f, p in g.index]
    x = np.arange(len(g))
    for k, (col, lab) in enumerate([("national_TWh_per_year", "each country alone"),
                                    ("regional_pools_TWh_per_year", "4 regional pools"),
                                    ("europe_TWh_per_year", "European copper plate")]):
        axes[1].bar(x + 0.27 * (k - 1), g[col], 0.27, label=lab)
    axes[1].set_xticks(x, labels, fontsize=7)
    axes[1].set_ylabel("energy above national P98 firm capacity\n(TWh per year)")
    axes[1].legend(fontsize=8)
    fig.suptitle("Mitigation: storage need and the value of pooling (3 realizations)", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / "wp5_mitigation.png", dpi=150)


if __name__ == "__main__":
    main()
