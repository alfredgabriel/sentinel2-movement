# External ADS-B Trajectory Validation Methodology

This document details the independent empirical validation framework of `s2motion` against external Automatic Dependent Surveillance–Broadcast (ADS-B) and Mode-S transponder records.

While inter-band parallax and aerodynamic plausibility establish the physical basis of Sentinel-2 moving target kinematics, **external ADS-B state vectors provide ground truth validation** to resolve the band order convention and calibrate measurement uncertainties.

---

## 1. A Priori Concordance Criteria

To preserve scientific integrity and prevent confirmation bias, all validation criteria are **defined a priori** before inspecting any external flight database and are evaluated strictly without post-hoc threshold adjustment:

| Parameter | Case 1: Approach / Terminal Area | Case 2: En-Route Cruising Flight | Mathematical Formulation |
| :--- | :--- | :--- | :--- |
| **Max CPA Distance ($d_{\max}$)** | **$1000\text{ m}$** ($1.0\text{ km}$) | **$2000\text{ m}$** ($2.0\text{ km}$) | $d_{\text{CPA}} \le d_{\max}$ |
| **Temporal Matching Window** | **$\pm 60.0\text{ s}$** around sensing time | **$\pm 60.0\text{ s}$** around sensing time | $|t_{\text{CPA}} - t_{\text{sensing}}| \le 60\text{ s}$ |
| **Heading Concordance** | **$2\sigma \approx \pm 14.0^\circ$** ($\sigma \approx 7.0^\circ$) | **$2\sigma \approx \pm 3.6^\circ$** ($\sigma \approx 1.8^\circ$) | $\|\Delta \psi\| \le 2 \sigma_{\psi}$ |
| **Ground Speed Concordance** | Within interval **$[254, 338]\text{ km/h}$** | Within interval **$[907, 960]\text{ km/h}$** | $v_{\text{adsb}} \in [v_{\min}, v_{\max}]$ |

> [!IMPORTANT]
> **No Post-Hoc Adjustment Rule**:
> If an aircraft candidate falls outside these established bounds, it is classified as incompatible or unmatched. Thresholds are never expanded retroactively to force a match.

---

## 2. Trajectory Interpolation and Closest Point of Approach (CPA)

ADS-B transponders broadcast discrete position messages (typically spaced by $0.5 - 5\text{ s}$). Because the satellite overpass occurs at an exact physical instant ($t_{\text{sensing}}$), `s2motion` reconstructs the continuous aircraft flight trajectory to find the exact **Closest Point of Approach (CPA)** to the georeferenced satellite centroid $(lat_{\text{target}}, lon_{\text{target}})$.

### 2.1 Segment Parameterization
For each adjacent pair of trajectory points $(p_0, p_1)$ recorded at timestamps $t_0 < t_1$, the position is parameterized linearly by $\alpha \in [0, 1]$:

$$\vec{p}(\alpha) = \vec{p}_0 + \alpha (\vec{p}_1 - \vec{p}_0), \quad t(\alpha) = t_0 + \alpha (t_1 - t_0)$$

In local metric coordinates relative to the target $(\Delta x, \Delta y)$:
$$\alpha^* = \text{clip}\left( -\frac{\vec{p}_0 \cdot (\vec{p}_1 - \vec{p}_0)}{\|\vec{p}_1 - \vec{p}_0\|^2}, \, 0, \, 1 \right)$$

### 2.2 Extracted Observables at CPA
At the optimal parameter $\alpha^*$, the module evaluates:
1. **CPA Timestamp ($t_{\text{CPA}}$)** and temporal offset $\Delta t_{\text{offset}} = t_{\text{CPA}} - t_{\text{sensing}}$.
2. **Geodesic Distance ($d_{\text{CPA}}$)** via Haversine great-circle calculation.
3. **Interpolated Track Heading ($\psi_{\text{adsb}}$)** evaluated along the shortest circular path.
4. **Interpolated Ground Speed ($v_{\text{adsb}}$)**.
5. **Barometric Altitude ($h_{\text{baro}}$)** and **Geometric Altitude ($h_{\text{geom}}$)**.

---

## 3. Altitude Modeling: Barometric vs Geometric

ADS-B messages report two distinct vertical coordinate representations:
- **Barometric Altitude ($h_{\text{baro}}$)**: Derived from static pressure transducers calibrated to the International Standard Atmosphere (ISA, $1013.25\text{ hPa}$) above the transition altitude (Flight Levels). In non-standard meteorological conditions (summer high-pressure or winter cold-air domes), barometric altitude deviates from the true physical height.
- **Geometric Altitude ($h_{\text{geom}}$)**: Derived directly from onboard GNSS satellite constellation solutions, providing physical height above the WGS84 reference ellipsoid.

All altitudes reported in feet are converted to meters using the exact conversion factor:
$$h_{[\text{m}]} = h_{[\text{ft}]} \times 0.3048$$

When geometric altitude is available, the difference $\Delta h = h_{\text{geom}} - h_{\text{baro}}$ is documented.

### 3.1 Parallax Recalculation with Real Flight Level
For high-altitude flights (Case 2), flight altitude was initially modeled as a user parameter ($h = 10.5\text{ km}$). When ADS-B telemetry supplies the actual flight altitude $h_{\text{adsb}}$, `s2motion` recalculates the stereoscopic parallax correction using the complete pushbroom model:

$$\vec{v}_{\text{true}}(h_{\text{adsb}}) = \left(1 - \frac{h_{\text{adsb}}}{H}\right) \vec{v}_{\text{apparent}} + \frac{h_{\text{adsb}}}{H} \vec{v}_{\text{track}}$$

The recalculated velocity is then compared directly against the ADS-B ground speed ($v_{\text{adsb}}$) to compute the residual difference:

$$\Delta v_{\text{residual}} = v_{\text{recalculated}} - v_{\text{adsb}}$$

---

## 4. Resolving the Band Order Hypotheses

The two candidate chronological conventions (`red-first` vs `blue-first`) predict opposite flight headings ($\Delta \psi = 180^\circ$) and drastically different velocities at high altitude:

1. **`red-first` (Red $\rightarrow$ Green $\rightarrow$ Blue)**:
   - Case 1: Heading $\approx 117.4^\circ$, speed $\approx 295\text{ km/h}$ (approach to Runway 12).
   - Case 2: Heading $\approx 316.4^\circ$, speed $\approx 932\text{ km/h}$ (subsonic cruise).
2. **`blue-first` (Blue $\rightarrow$ Green $\rightarrow$ Red)**:
   - Case 1: Heading $\approx 297.4^\circ$, speed $\approx 295\text{ km/h}$ (departure from Runway 30).
   - Case 2: Heading $\approx 159.8^\circ$, speed $\approx 1386\text{ km/h}$ (supersonic).

The validation engine evaluates both hypotheses simultaneously against the a priori criteria:
- `COMPATIBLE_RED_FIRST`: Only `red-first` passes all heading, speed, and spatial tolerances.
- `COMPATIBLE_BLUE_FIRST`: Only `blue-first` passes all criteria.
- `AMBIGUOUS_BOTH`: Both hypotheses fall within bounds.
- `INCOMPATIBLE_NEITHER`: Neither hypothesis matches the nearest candidate aircraft.
- `NO_DATA_OR_NO_MATCH`: No aircraft recorded within the spatial/temporal window.

---

## 5. Offline File Support & Informative Outcomes

The validation engine runs **strictly offline** without external network dependencies:
- **OpenSky Network CSV**: Standard state vector export format (`time`, `icao24`, `lat`, `lon`, `velocity`, `heading`, `baroaltitude`, `geoaltitude`, `callsign`).
- **ADS-B Exchange JSON**: Standard aircraft snapshots and trace format exports.
- **Configurable Key Mapping**: Custom column and key mappings can be configured in TOML.

### Absence of Match as an Informative Result
If no aircraft matches within the window, `s2motion validate` reports `NO_DATA_OR_NO_MATCH`. This is handled as an **informative finding**, not a runtime exception:
1. Civil transponder was unequipped or operating in Mode-A/C only without ADS-B Out.
2. The aircraft was outside ground ADS-B receiver coverage or masked by terrain.
3. State vectors were suppressed or omitted from public crowd-sourced feeds.

---

## 6. CLI Usage

```bash
# Validate Case 1 approach using an OpenSky CSV export and scenario configuration
s2motion validate --adsb flight_data_20260812.csv --config examples/loiu_2026-08-12.toml

# Validate Case 2 high-altitude cruise with custom tolerance parameters
s2motion validate --adsb flight_data_20260621.json --config examples/loiu_2026-06-21.toml --max-dist 2000

# Pure command-line validation without config file
s2motion validate --adsb opensky_data.csv \
  --target-lat 43.310770 \
  --target-lon -2.936874 \
  --sensing-time "2026-08-12T11:09:40Z" \
  --heading 117.4 \
  --speed 295.0 \
  --speed-bounds 254.0 338.0 \
  --max-dist 1000
```
