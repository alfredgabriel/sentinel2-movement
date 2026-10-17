# External ADS-B Trajectory Validation Methodology

This document details the independent empirical validation framework of `s2motion` against external Automatic Dependent Surveillance–Broadcast (ADS-B) and Mode-S transponder records.

While inter-band parallax and aerodynamic plausibility establish the physical basis of Sentinel-2 moving target kinematics, **external ADS-B state vectors provide ground truth validation** to resolve the band order convention and calibrate measurement uncertainties.

---

## 1. A Priori Concordance Criteria

To preserve scientific integrity and prevent confirmation bias, all validation criteria are **defined a priori** before inspecting any external flight database and are evaluated strictly without post-hoc threshold adjustment:

| Parameter | Case 1: Approach / Terminal Area | Case 2: En-Route Cruising Flight | Mathematical Formulation |
| :--- | :--- | :--- | :--- |
| **Max Capture Distance ($d_{\max}$)** | **$1000\text{ m}$** ($1.0\text{ km}$) | **$2000\text{ m}$** ($2.0\text{ km}$) | $d(t_{\text{sensing}}) \le d_{\max}$ (at capture instant) |
| **CPA Time Offset Limit** | **$|\Delta t_{\text{CPA}}| \le 20.0\text{ s}$** | **$|\Delta t_{\text{CPA}}| \le 20.0\text{ s}$** | Tile scan duration limit ($\sim 15 - 20\text{ s}$) |
| **Candidate Search Window** | **$\pm 60.0\text{ s}$** around sensing time | **$\pm 60.0\text{ s}$** around sensing time | Extraction window only ($|t - t_{\text{sensing}}| \le 60\text{ s}$) |
| **Heading Concordance ($2\sigma$)** | **$\pm 14.0^\circ$** ($\sigma \approx 7.0^\circ$) | **$\pm 6.1^\circ$** (combined $\sigma \approx 3.04^\circ$) | $\|\Delta \psi\| \le 2 \sigma_{\text{comb}}$ |
| **Ground Speed Concordance** | Within interval **$[254, 338]\text{ km/h}$** | Within interval **$[907, 960]\text{ km/h}$** | $v_{\text{adsb}} \in [v_{\min}, v_{\max}]$ |

> [!IMPORTANT]
> **Capture Instant Evaluation Rule**:
> Acceptance is evaluated at the aircraft's interpolated position at the **exact instant of satellite sensing ($t_{\text{sensing}}$)**, demanding $|\Delta t_{\text{CPA}}| \le 20\text{ s}$ (corresponding to the $\sim 15 - 20\text{ s}$ physical sweep duration of a Sentinel-2 MSI tile). The $\pm 60\text{ s}$ window serves exclusively as a broad retrieval and search window. If an aircraft passes close to the target coordinates but at a time offset $|\Delta t_{\text{CPA}}| > 20\text{ s}$, it was not physically present during tile acquisition and is rejected.

> [!IMPORTANT]
> **No Cherry-Picking Rule (All Candidates Listed)**:
> If multiple aircraft are present within the $\pm 60\text{ s}$ search window, `s2motion validate` lists **every single candidate** in an explicit table reporting distance at capture $d(t_{\text{sensing}})$, CPA distance, $\Delta t$, heading, speed, and individual compatibility status. No candidate is selected or suppressed arbitrarily.

---

## 2. Trajectory Interpolation and Capture Instant Kinematics

ADS-B transponders broadcast discrete position messages (typically spaced by $0.5 - 5\text{ s}$). Because the satellite overpass occurs at an exact physical instant ($t_{\text{sensing}}$), `s2motion` reconstructs the continuous aircraft flight trajectory to evaluate:
1. The **exact interpolated position at the sensing instant** $(lat(t_{\text{sensing}}), lon(t_{\text{sensing}}))$ and distance $d(t_{\text{sensing}})$ to the satellite target centroid.
2. The **Closest Point of Approach (CPA)** along the continuous track, obtaining $t_{\text{CPA}}$, $d_{\text{CPA}}$, and the time offset $\Delta t_{\text{CPA}} = t_{\text{CPA}} - t_{\text{sensing}}$.

### 2.1 Segment Parameterization
For each adjacent pair of trajectory points $(p_0, p_1)$ recorded at timestamps $t_0 < t_1$, the position is parameterized linearly by $\alpha \in [0, 1]$:

$$\vec{p}(\alpha) = \vec{p}_0 + \alpha (\vec{p}_1 - \vec{p}_0), \quad t(\alpha) = t_0 + \alpha (t_1 - t_0)$$

In local metric coordinates relative to the target $(\Delta x, \Delta y)$:
$$\alpha^* = \text{clip}\left( -\frac{\vec{p}_0 \cdot (\vec{p}_1 - \vec{p}_0)}{\|\vec{p}_1 - \vec{p}_0\|^2}, \, 0, \, 1 \right)$$

### 2.2 Combined Heading Tolerance for Case 2
In Case 2 (high-altitude cruise), the true flight altitude is not known a priori and is bounded within the realistic cruising interval $[9000, 12000]\text{ m}$. Over this altitude interval, the parallax-corrected heading $\psi_{\text{corr}}(h)$ varies from $318.8^\circ$ ($h=9\text{ km}$) to $313.9^\circ$ ($h=12\text{ km}$), yielding a sensitivity spread of $\Delta \psi_{\text{alt}} \approx 4.90^\circ$.

The heading tolerance combines the apparent heading measurement uncertainty ($\sigma_{\text{app}} \approx 1.8^\circ$) in quadrature with the altitude interval sensitivity ($\sigma_{\text{alt}} = \Delta \psi_{\text{alt}} / 2 \approx 2.45^\circ$):

$$\sigma_{\text{comb}} = \sqrt{\sigma_{\text{app}}^2 + \sigma_{\text{alt}}^2} = \sqrt{1.8^2 + 2.45^2} \approx 3.04^\circ \implies \text{Tolerance}_{2\sigma} = 2 \times 3.04^\circ \approx \pm 6.1^\circ$$

---

## 3. Altitude Modeling: Barometric vs Geometric over Terrain ($h_{\text{AGL}}$)

ADS-B messages report two distinct vertical coordinate representations:
- **Barometric Altitude ($h_{\text{baro}}$)**: Derived from static pressure transducers calibrated to the International Standard Atmosphere (ISA, $1013.25\text{ hPa}$ / QNE) above the transition altitude (Flight Levels). **Barometric altitude is NOT height above the terrain**; in non-standard meteorological conditions (summer high pressure or cold air domes), it deviates significantly from true geometric altitude.
- **Geometric Altitude ($h_{\text{geom}}$)**: Derived directly from onboard GNSS satellite constellation solutions, providing physical height above the WGS84 reference ellipsoid / geoid (MSL).

### 3.1 Pushbroom Parallax Depends on Height Above Terrain ($h_{\text{AGL}}$)
Because stereoscopic parallax between MSI spectral bands arises from optical displacement relative to the imaged ground surface, the physical height variable required by the pushbroom parallax model is the **height above terrain ($h_{\text{AGL}}$)**:

$$h_{\text{AGL}} = \max\left(0.0, \, h_{\text{geom}} - z_{\text{terrain}}\right)$$

Where $z_{\text{terrain}}$ is the local ground elevation (e.g., $42\text{ m}$ for Bilbao Airport LEBB). When geometric GNSS altitude is unavailable, barometric altitude corrected for local elevation is used as fallback ($h_{\text{baro}} - z_{\text{terrain}}$).

### 3.2 Parallax Recalculation with Real Flight Altitude AGL
When ADS-B telemetry supplies the actual flight altitude $h_{\text{AGL}}$, `s2motion` recalculates the stereoscopic parallax correction using the complete pushbroom model:

$$\vec{v}_{\text{true}}(h_{\text{AGL}}) = \left(1 - \frac{h_{\text{AGL}}}{H}\right) \vec{v}_{\text{apparent}} + \frac{h_{\text{AGL}}}{H} \vec{v}_{\text{track}}$$

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
