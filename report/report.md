# From observed stress to future stress: real stressful periods of the European power system under climate change

Mikhail Serikov, Hamburg, November 2026. Working report (not peer reviewed). Code and data notes: this repository.

## Abstract

Stressful periods of an electricity system with high wind and solar shares are defined by weather, demand and the system that meets them. We start from periods the European system actually experienced in 2015-2025, build a weather-only stress index for today's fleet from ERA5, and show that it reproduces observed residual-load stress (correlation 0.91 of daily anomalies, 72% of observed event days captured) and part of the price stress (44% of European winter price-stress days against 12% by chance). Using Climate2Energy, bias-corrected CESM2 output for three realizations, we compare present (1995-2014) and SSP3-7.0 (2080-2099) climates. Bias-corrected CESM2 reproduces the frequency of low-wind spells but is more persistent than ERA5 and couples winter wind and demand more tightly, which matters for long events. The net-load set-up of Bloin-Wibe et al. (2026) is reproduced in sign, season and order of magnitude. Stress shifts from northern to southern Europe and from winter to summer; Dunkelflaute becomes more frequent around the North Sea margin (Great Britain, Ireland, Norway). The weather configurations of three named events become about half as frequent, but analogues of the December 2024 Dunkelflaute become more often stressful. Air conditioning amplifies the climate signal through an interaction larger than either effect alone, whereas warmer winters offset part of the stress added by heat pumps. Pooling across countries is the strongest mitigation; storage needs are dominated by internal variability across realizations rather than by the forced change. Converting the same ERA5 hours on a CESM2-like grid changes best-site wind output little in flat and coastal countries but by 20-40% in Alpine and Balkan countries, where it also lengthens low-wind spells; a PyPSA system sized on a present-day stress year loses 0.8-1.8 TWh of load in a future stress year in all three realizations.

## 1. Introduction

Planning studies usually ask how the statistics of net load change. System operators and markets, however, experience events: a cold, windless week in January 2017, the Dunkelflaute of November and December 2024. This report turns the question around: it starts from such real events, asks which weather patterns produce them, and then asks how often and how severely the same situations occur in a warmer climate, which technologies make them worse or milder and which mitigation options remove them. It builds on Climate2Energy (Wohland et al. 2025) and on the net-load analysis of Bloin-Wibe et al. (2026), whose set-up it reproduces before extending it from statistics to events.

## 2. Data and methods

- **Observed system 2015-2025**: Open Power System Data (2015 to 09/2020) and the ENTSO-E Transparency Platform (10/2020-2025): load, wind and solar generation by country; day-ahead prices 2015-2025. Great Britain is excluded after Brexit (no ENTSO-E data).
- **ERA5**: C3S ERA5-based country capacity factors and 2 m temperature (1979-2026); ERA5 mean sea level pressure (1990-2025); ERA5 single levels at 0.25 degrees for two winter windows.
- **Climate2Energy** (Zenodo 15269455): hourly country capacity factors (onshore SWT142, offshore E-126, PV), heating and cooling demand (demand.ninja), hydro inflow; realizations A (random), B (max NAO), C (min NAO).
- **Net load** N = D - G as in Bloin-Wibe et al. (2026); fleets defined by annual energy (current: ENTSO-E 2024; net-zero: VRE = 80% of demand with 60/40, 80/20, 30/70 wind/PV shares).
- **Events**: threshold exceedances with gaps merged; duration, severity, extent, co-occurrence, GPD return levels; signal-to-noise against block-bootstrap and between-realization variability.
- **Weather-only stress index**: today's fleet on C3S ERA5 capacity factors and a temperature-driven daily demand model fitted on observed load.
- **Patterns**: four winter regimes (EOF + k-means) from ERA5 pressure; future analogues searched on standardized driver patterns (wind, PV, demand in 32 countries) because Climate2Energy holds no pressure fields.
- **Mitigation**: sequent-peak storage, national vs regional vs European pooling, intraday demand shifting and a PyPSA capacity expansion of 12 countries (from eu-weather-years-pypsa) driven by Climate2Energy weather.
- **Resolution**: the same ERA5 hours converted on the native grid and on a CESM2-like 1.25 x 0.94 degree grid.

## 3. Results

### 3.1 Real events and the weather-only index
The index correlates 0.91 with the observed residual-load anomaly (2015-2025), its top-3% days capture 72% of observed residual-load event days (false-alarm ratio 13%) and 44% of European winter price-stress days (12% by chance; 95th percentile of chance 22%). Rank correlation with the median price ratio in winter is 0.80; by regression (Newey-West errors), each +10 GW of the index raises the German day-ahead price by 10.6% relative to its monthly median (t = 18.5) and the odds of a European price-stress day by a factor of 1.74. Many weather-stress days pass without a price spike (false-alarm ratio 73%), and the November 2024 Dunkelflaute, which nearly doubled German prices, is not extreme in weather terms for the continental pool. The December 2024 event is about a 1-in-2.8-year weather situation for today's fleet, January 2017 about 1-in-2.1.

### 3.2 Does bias-corrected CESM2 reproduce event statistics?
Rank-based statistics, 18 countries, 1995-2014: the frequency of low-wind spells agrees (8.4 per year in ERA5, 8.5-8.8 in C2E), but persistence is higher in C2E (lag-3-day autocorrelation 0.34-0.36 against 0.23), the European pool's longest low-wind spell is longer (12-19 against 11 days) and winter wind and demand anomalies are more negatively correlated (-0.27 to -0.31 against -0.17, different demand models). Univariate quantile mapping fixes marginals, not persistence or joint behaviour; both shape long events.

### 3.3 Reproducing the net-load result
High-net-load hours (above P90) change by +21.6% (realization range 20.0-24.0%) for the high-wind fleet with current heating, mainly in summer (+55%) and autumn (+23%), and by -51.5% in winter and -75% in spring with fully electrified heating. Bloin-Wibe et al. report about +30% and about -50%.

### 3.4 Present vs future events
Country stress hours show a north-south split (Italy +121%, signal-to-noise 8.6; Sweden, Latvia, Estonia, France, Finland -36 to -40%). Dunkelflaute becomes more frequent in Great Britain (+72%), Ireland (+68%) and Norway (+47%), each with signal-to-noise above 2 and the same sign in all realizations, and less frequent in most continental countries. The annual maximum 7-day net load rises for the high-wind fleet in all three realizations.

### 3.5 Weather patterns and their future analogues
Scandinavian blocking is 1.8 times over-represented on stress days (90% interval 1.5-2.2), NAO- 1.5 times; NAO+ almost excludes stress. There is no trend in blocking frequency 1990-2025. Analogues of the three named events occur about half as often under SSP3-7.0 (9.2 against 3.8-4.8 per decade), but December 2024 analogues exceed today's 98th percentile of net load on 67% of days instead of 37%.

### 3.6 Technology trends
With today's technology the climate signal adds 24 stress hours a year. Tripled air conditioning adds 23 hours alone but 121 hours through its interaction with the warmer climate. Heat pumps add stress that warmer winters partly remove (interaction -261 to -430 hours). Uncontrolled EV charging adds 778 hours, smart charging 275.

### 3.7 Mitigation
Energy above national firm capacity falls from about 6 TWh a year (each country alone) to about 1 TWh (four regional pools) and below 0.1 TWh (European copper plate). Storage to hold net load at today's P95 is about 2.4 TWh (present) and 2.1 TWh (future) for the balanced fleet, but its future range across realizations (1.1-3.4 TWh) is much wider than the present one. Moving 5% of daily demand within the day lowers the European peak by about 76 GW. In a 12-country PyPSA capacity expansion (realization A, 6-hour steps), a system designed on the present stress year loses 1.76 TWh of load when operated on the future stress year (2088), a system designed on a normal future year 3.3 TWh, whereas a present normal-year design loses only 37 GWh in the present stress year. Designing for the future stress year costs 57.0 bn EUR a year against 50.2 for a normal future year; in the present climate the two cost about the same (51.5 and 52.3). Realizations B and C confirm the direction: the present stress design loses 0.8-1.8 TWh in the future stress year in all three realizations, and the future stress design costs 4-7 bn EUR a year more than a normal future year, whereas the present-day cost difference between stress and normal design years changes sign between realizations.

### 3.8 Resolution
Climate2Energy corrects CESM2 on its own grid, so a perfectly corrected CESM2 behaves like ERA5 at 1.25 x 0.94 degrees. Converting the same ERA5 hours on both grids (December 2016 to February 2017; winter 2024/25 was still queued at CDS when this was written) changes national best-site wind output by -4% to +3% in flat and coastal countries, but by -39% (North Macedonia), -25% (Slovenia), -22% (Switzerland) and +40% (Albania) in complex terrain, where the longest low-wind spell also grows (Switzerland 278 to 510 hours). Low-wind hours are more frequent on the coarse grid in 19 of 30 countries. Stretched-grid simulations matter most for Alpine and Balkan wind and for event duration.

### 3.9 Nordic hydrology
Climate2Energy inflow in Norway rises from 114 to 116 TWh a year and becomes less variable (coefficient of variation 0.14 to 0.11); dry years fall from 21% to 18% (Sweden 21% to 4%). A dry inflow year followed by a continental stress winter occurs once in 57 Norwegian inflow years in both periods, and in the observed record (NVE filling in early October 1995-2025 against the next winter's ERA5 stress days) the rank correlation is 0.15. No compound link is visible, though twenty years per realization cannot exclude one.

## 4. Discussion and limitations
One climate model and one scenario with three realizations limit the forced signal to what CESM2 under SSP3-7.0 produces; twenty-year periods make return levels beyond twenty years an extrapolation. Fleets are stylised, and the technology scenarios are illustrative multipliers on open-source magnitudes (IEA Future of Cooling; a fully electrified car fleet of about 450 TWh), not projections. The weather-only index is a deliberately simple bridge between observed and modelled events; it misses market and outage drivers, as the November 2024 case shows. The ERA5 comparison relies on C3S series built with different conversion models, so only rank statistics are compared. The analogue search replaces pressure-field analogues, which require CESM2 pressure output for the Climate2Energy members.

## 5. Conclusions and next steps
1. Events, not only net-load statistics, carry the planning signal: their frequency, persistence and co-occurrence differ in ways the mean change does not show.
2. Bias-corrected global model output reproduces event frequency but not persistence; multivariate correction and higher resolution (stretched-grid runs) are the natural next steps for Climate2Energy.
3. The interaction of technology and climate (air conditioning, heat pumps) is as large as either effect alone and should be modelled jointly.
4. Next: pressure-field analogues with CESM2 output for the C2E members, highRES runs on stress and normal years, and imperfect foresight (operating events on day-ahead forecasts).

## References
- Bloin-Wibe L, Fischer E, Göke L, Knutti R, De Marco A, Wohland J (2026). Climate change impacts on net load under technological uncertainty in European power systems. Environmental Research Letters 21, 084004. doi 10.1088/1748-9326/ae5727
- Wohland J, Bloin-Wibe L, Fischer E, Göke L, Knutti R, De Marco A, Beyerle U, Savelsberg J (2025). Climate2Energy: a framework to consistently include climate change into energy system modeling. Environmental Research: Energy 2(4). doi 10.1088/2753-3751/ae2870
- Wohland J, Reyers M, Weber J, Witthaut D (2017). More homogeneous wind conditions under strong climate change decrease the potential for inter-state balancing of electricity in Europe. Earth System Dynamics 8, 1047-1060. doi 10.5194/esd-8-1047-2017
- Wohland J, Folini D, Pickering B (2021). Wind speed stilling and its recovery due to internal climate variability. Earth System Dynamics 12, 1239-1251. doi 10.5194/esd-12-1239-2021
- Mühlemann D, Folini D, Pfenninger S, Wild M, Wohland J (2022). Meteorologically-informed spatial planning of European PV deployment to reduce multiday generation variability. Earth's Future 10, e2022EF002673. doi 10.1029/2022EF002673
- IEA (2018). The Future of Cooling. International Energy Agency, Paris.
