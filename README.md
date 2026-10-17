# Sentinel-2 Movement (`s2motion`)

[![CI](https://github.com/alfredgabriel/sentinel2-movement/actions/workflows/ci.yml/badge.svg)](https://github.com/alfredgabriel/sentinel2-movement/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

> **Detection, trajectory tracking, and velocity measurement of fast-moving surface objects using inter-band sub-second parallax in pushbroom Sentinel-2 imagery.**

*Read this documentation in Spanish: [README.es.md](README.es.md).*

---

## 1. What is this and why does it work?

The **MultiSpectral Instrument (MSI)** on board the European Space Agency's (ESA) **Sentinel-2** satellites is a **pushbroom sensor**. Unlike framing cameras that capture all spectral bands instantaneously, pushbroom sensors image the Earth via linear CCD detector arrays placed at slightly different along-track positions on the focal plane.

As Sentinel-2 orbits at $\sim 7.2 \text{ km/s}$ in a sun-synchronous descending orbit (North to South), the physical layout of the focal plane dictates the along-track scanning sequence:
- **Band 4 (Red)** is the leading detector in the flight direction: it images any ground coordinate **first** ($t = 0.000\text{ s}$).
### Physical Ground Acquisition Sequence
The inter-band time spacings ($0.000, 0.264, 0.527, 1.005\text{ s}$) are derived from scientific literature (Krauß 2021, Binet et al. 2022). The chronological direction (Red $\rightarrow$ Green $\rightarrow$ Blue) was established empirically from contrail orientation in Case 2 and aerodynamic velocity plausibility (detailed in [docs/band-order.md](docs/band-order.md)). Both `red-first` (default) and `blue-first` are supported via `--band-order`.

Under the default `red-first` sequence:
- **Band 4 (Red)** is the leading detector: it images a ground target **first** ($t = 0.000\text{ s}$).
- **Band 3 (Green)** follows $0.478\text{ s}$ later ($1.005 - 0.527\text{ s}$).
- **Band 8 (NIR)** follows $0.741\text{ s}$ later ($1.005 - 0.264\text{ s}$).
- **Band 2 (Blue)** is the trailing detector: it images the ground target **last** ($t = 1.005\text{ s}$).

```mermaid
timeline
    title Sentinel-2 Ground Acquisition Sequence (red-first)
    t = 0.000 s : Band 04 (Red, 665 nm) - Leading
    t = 0.478 s : Band 03 (Green, 560 nm)
    t = 0.741 s : Band 08 (NIR, 842 nm)
    t = 1.005 s : Band 02 (Blue, 490 nm) - Trailing
```

| Band | Spectral Domain | Center Wavelength | Ground Acquisition Delay | Role |
|:---:|:---:|:---:|:---:|:---:|
| **B04** | Red | 665 nm | **0.000 s** | First exposure (Leading) |
| **B03** | Green | 560 nm | **0.478 s** | Intermediate exposure |
| **B08** | Near Infrared (NIR) | 842 nm | **0.741 s** | Intermediate exposure |
| **B02** | Blue | 490 nm | **1.005 s** | Final exposure (Trailing) |

### The Moving Object Signature
When an object travels at high speed during this $\sim 1.005 \text{ s}$ window (such as an aircraft on approach or in flight), it advances along its trajectory between sequential exposures. In an RGB composite (Red=B04, Green=B03, Blue=B02), this manifests as **three distinctly colored spots in a collinear row pointing in the direction of motion**:
$$\mathbf{Red} \longrightarrow \mathbf{Green} \longrightarrow \mathbf{Blue}$$

By estimating the **subpixel centroid** in each band, `s2motion` determines:
1. **Displacement vector** ($\text{Red} \to \text{Blue}$ or $\text{Blue} \to \text{Red}$) and ground distance in meters.
2. **True geographic heading** ($0^\circ = \text{North}$, clockwise, $90^\circ = \text{East}$, $180^\circ = \text{South}$, $270^\circ = \text{West}$).
3. **Ground velocity** with propagated uncertainty bounds.
4. **Georeferenced proximity to aerodrome runways**: Distance to closest threshold, distance along extended runway axis, and perpendicular offset from the centerline with explicit spatial uncertainty ($\approx \pm 15\text{ m}$).
5. **Coherence diagnostics**: Collinearity offset of the Green detection and temporal projection consistency.
6. **Environmental Surface Weather**: Queries historical surface weather (Open-Meteo / ERA5 reanalysis) linearly interpolated to the scene timestamp for environmental context.

---

## 2. Installation

Requires Python $\ge 3.10$.

```bash
# Clone the repository
git clone https://github.com/alfredgabriel/sentinel2-movement.git
cd sentinel2-movement

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package with dependencies
pip install -e .

# Optional: install development tools (pytest, ruff)
pip install -e ".[dev]"
```

---

## 3. Quick Start (3 Commands)

```bash
# 1. Download windowed RGB crops over Bilbao Airport (cloud cover < 10%)
s2motion crops --start 2026-08-01 --end 2026-08-15 --max-cloud 10 --out outputs/

# 2. Inspect a scene interactively to locate coordinate seeds (click logs x, y)
s2motion view --config examples/loiu_2026-08-12.toml

# 3. Detect subpixel centroids, calculate velocity, and export publication figure with weather telemetry
s2motion measure --config examples/loiu_2026-08-12.toml --weather
```

---

## 4. Case Studies & Results

### Case 1: Aircraft on Approach to Runway 12, Bilbao Airport (2026-08-12)
- **Target**: Fast-moving aircraft aligned with runway 12 at Bilbao Airport (LEBB/BIO) (working hypothesis: short final approach under `red-first`, pending ADS-B confirmation).
- **Physical & Spatial Context**:
  - Bilbao Airport Runway 12/30 threshold coordinates from [ENAIRE AIP España (AD 2-LEBB)](https://aip.enaire.es/AIP/):
    - **THR 12 (NW)**: `43°18'22.85"N, 002°55'29.78"W` (`43.306347°N, -2.924939°W`)
    - **THR 30 (SE)**: `43°17'45.91"N, 002°53'49.02"W` (`43.296086°N, -2.896950°W`)
    - True forward geodetic axis calculated from thresholds: **$116.7^\circ$** (the nominal designation '12' is rounded to $120^\circ$).
  - **Georeferenced Position**: The detected aircraft (Red centroid) is located at **$43.310770^\circ\text{N}, -2.936874^\circ\text{W}$** (estimated position uncertainty $\approx \pm 15\text{ m}$ due to 10 m pixel size, Sentinel-2 geolocation accuracy, and motion during line scan), approximately **$1085 \pm 15\text{ m}$ northwest of Threshold 12** along the extended runway centerline ($-1085 \pm 15\text{ m}$ along track) and **$5.0 \pm 15.0\text{ m}$ off the extended centerline**.
  - **Status**: The aircraft is not on the runway surface (`is_on_runway: False`), but positioned in the straight-in approach corridor with heading **$117.4^\circ \pm 7.0^\circ$**, differing by **$0.7^\circ (\pm 7.0^\circ)$** from the runway 12 geodetic axis.

#### Full Scene Overview (Uncropped Crop of Bilbao Airport Area)
![Full Scene Overview - 2026-08-12](docs/img/loiu_2026-08-12_overview.png)

#### Subpixel Kinematics & Inter-Band Analysis (with Live Weather Fusion)
![Case 1: Aircraft on Approach to Bilbao Airport](docs/img/loiu_2026-08-12_measured.png)

```text
============================================================
Sentinel-2 Moving Object Kinematics & Coherence Report
============================================================
Direction:    Red -> Green -> Blue
Distance:     82.4 m (range: 72.4 - 92.4 m, 1-sigma: +/-7.1 m)
Heading:      117.4 deg clockwise from North (+/-7.0 deg)
Velocity:     295 km/h (range: 254 - 338 km/h) [82.0 m/s]
Delta t:      1.005 s (range: 0.985 - 1.025 s)
------------------------------------------------------------
Coherence Diagnostics:
  - Green collinearity offset: 0.11 px (expected < ~1.0 px)
  - Green relative position:  0.47 (expected: 0.48, delta: 0.01)
  - Runway axis difference:   0.7 deg (+/-7.0 deg)
------------------------------------------------------------
Runway Position (LEBB Runway 12/30, axis 116.7°):
  - Reference Centroid:     Red band (estimated spatial uncertainty: ±15 m)
  - Geodetic Coordinates:   lat 43.310770°, lon -2.936874° (±15 m)
  - Proximity to THR 12:    1085 ± 15 m (along extended axis: -1085 ± 15 m)
  - Centerline Offset:      5.0 ± 15.0 m
  - Status:                 APPROACH CORRIDOR (1085 ± 15 m before THR 12) [on runway surface: False]
------------------------------------------------------------
Surface Weather Telemetry (Open-Meteo, 10m AGL - Environmental Context):
  - Surface Weather:  28.9 °C | 1014.4 hPa | Wind 10.6 km/h (5.7 kt) from 14°
  - Wind Components:  Headwind: -2.4 km/h (-1.3 kt) | Crosswind: -10.3 km/h
  - Note:             Surface wind does not imply physical causality for aircraft ground speed.
============================================================
```

**Physical & Kinematic Interpretation**:
- **Flight phase hypothesis**: Ground speed of **$295 \text{ km/h}$** ($82.0 \text{ m/s}$ / $159\text{ kt}$) and geographic heading of **$117.4^\circ \pm 7.0^\circ$** at $1085 \pm 15\text{ m}$ before Threshold 12 are consistent with a commercial jet on short final approach to runway 12 under the `red-first` band order. Note that under `blue-first`, the same geometry corresponds to an initial climb out after departure from Runway 30 ($297.4^\circ \pm 7.0^\circ$). Without external ADS-B state vectors (active runway at ~11:09 UTC), this remains an unvalidated operational hypothesis (see [docs/band-order.md](docs/band-order.md)).
- **Runway axis alignment**: The measured heading ($117.4^\circ \pm 7.0^\circ$) differs by **$0.7^\circ (\pm 7.0^\circ)$** from the geodetic runway axis ($116.7^\circ$) calculated directly from official ENAIRE AIP threshold coordinates.
- **Surface meteorological context**: Historical Open-Meteo reanalysis (interpolated to the product sensing start time $11:09:40\text{ UTC}$, noting that target overpass may differ by a few seconds) shows ground-level temperature of $28.9^\circ\text{C}$, QNH $1014.4\text{ hPa}$, and a surface wind of $10.6\text{ km/h}$ from $014^\circ$. These values describe the local surface atmosphere at 10 m AGL as environmental context without causal interpretation.

---

### Case 2: High-Altitude Cruising Aircraft with Contrail (2026-06-21)
- **Target**: Aircraft at cruising altitude ($\sim 10 - 11 \text{ km}$) heading northwest across the Bilbao region, with a prominent condensation trail (contrail).

#### Full Scene Overview (Bilbao Region with Visible Contrail)
![Full Scene Overview - 2026-06-21](docs/img/loiu_2026-06-21_overview.png)

#### Subpixel Kinematics & Inter-Band Analysis
![Case 2: High-Altitude Cruising Aircraft with Contrail](docs/img/loiu_2026-06-21_measured.png)

```text
============================================================
Sentinel-2 Moving Object Kinematics & Coherence Report
============================================================
Direction:    Red -> Green -> Blue
Distance:     321.4 m (range: 311.4 - 331.4 m, 1-sigma: +/-7.1 m)
Heading:      330.4 deg clockwise from North (+/-1.8 deg)
Velocity:     1151 km/h (range: 1094 - 1211 km/h) [319.8 m/s]
Delta t:      1.005 s (range: 0.985 - 1.025 s)
------------------------------------------------------------
Coherence Diagnostics:
  - Green collinearity offset: 0.54 px (expected < ~1.0 px)
  - Green relative position:  0.46 (expected: 0.48, delta: 0.01)
============================================================
```

**Interpretation**:
- The apparent uncorrected speed is **$1151\text{ km/h}$**, which exceeds typical subsonic airliner ground speed ($800 - 900\text{ km/h}$).
- **Key physical insight**: For an airborne object at high altitude, the observed inter-band shift is a combination of true horizontal aircraft movement **and** stereoscopic parallax caused by the satellite's orbital displacement projected across the target's altitude.
- Surface meteorological parameters and runway comparisons are omitted as irrelevant for a high-altitude cruising target.
- Ground-truth speed requires stereoscopic parallax correction (see Phase 3). Without external altitude data, this case serves as an unvalidated demonstration of chromatic parallax dispersion.

---

## 5. Method Summary

1. **Remote Cloud-Optimized GeoTIFF (COG) Windowing**: Queries AWS Earth Search STAC (`sentinel-2-l2a`) and reads only the target bounding box via `rasterio.windows.from_bounds` without downloading full multi-gigabyte scenes.
2. **Local Anomaly Extraction**: Subtracts a $9 \times 9$ median filter background to eliminate runway markings and static surface features.
3. **Intensity-Weighted Subpixel Centroid**: Evaluates the center of mass of pixels $\ge 50\%$ peak intensity within a $3\text{ px}$ radius.
4. **Vector Kinematics**: Computes displacement from Red ($t=0.000\text{ s}$) to Blue ($t=1.005\text{ s}$), heading, and ground velocity.
5. **Rigorous Uncertainty Propagation**:
   - Accounts for $\pm 0.5\text{ px}$ subpixel localization error per endpoint.
   - Incorporates $\pm 2\%$ timing variation in $\Delta t$ resulting from optical distortion and satellite altitude perturbations ([Binet et al., 2022](https://doi.org/10.5194/isprs-annals-V-1-2022-57-2022)).
   - Always reports velocity as an explicit interval $[v_{\min}, v_{\max}]$, never as an isolated point value.
6. **Atmospheric & Aerodynamic Fusion**: Integrates Open-Meteo reanalysis to resolve headwind/crosswind components, true airspeed (TAS), and density altitude (DA).

*For full mathematical derivations, see [docs/method.md](docs/method.md).*

---

## 6. Limitations

To ensure scientific honesty and transparency, the following physical and sensor constraints must be acknowledged:

1. **Altitude Parallax Conflation**: For airborne targets, apparent displacement is the vector sum of horizontal aircraft ground movement and stereoscopic parallax induced by satellite motion at high altitude. Velocity measurements are only strictly quantitative for targets on or very near ground level.
2. **Lack of Flight Identification**: Satellite imagery does not transmit aircraft callsigns, transponder codes, or flight levels. Correlating detections with specific commercial flights requires ADS-B telemetry validation.
3. **Sensor Spatial Resolution**: At $10\text{ m/pixel}$, an airliner spans only $3 - 5$ pixels. Structural details (wings, engines, fuselage shape) cannot be resolved; identification relies entirely on chromatic dispersion signatures.
4. **Slow-Moving Targets**: Ships and maritime vessels moving at $10 - 20\text{ knots}$ ($5 - 10\text{ m/s}$) displace less than $5 - 10\text{ m}$ in $1.005\text{ s}$, which is near or below the single-pixel limit ($10\text{ m}$), making them challenging to quantify without multi-temporal cross-correlation.

---

## 7. Roadmap

Planned future extensions (not implemented in v0.1):
- [ ] **Automated Runway Swath Scanner**: Unsupervised detection of bright multi-chromatic anomalies along runway corridors with automated CSV reporting.
- [ ] **ADS-B Telemetry Integration**: Automated validation against historical OpenSky Network ADS-B trajectories.
- [ ] **Maritime Port Detection**: Adapted subpixel phase correlation for container ships and ferries entering the Port of Bilbao (El Abra).
- [ ] **20-Meter Band Expansion**: Inclusion of Red Edge (B8A) and Shortwave Infrared (B11, B12) detectors with their corresponding time lags.

---

## 8. Scientific References

- **Krauß, T. (2021)**. *Extraction of Cloud Heights from Sentinel-2 Multispectral Images*.  
  ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences, Vol. V-1-2021, pp. 17–23.  
  DOI: [10.5194/isprs-annals-V-1-2021-17-2021](https://doi.org/10.5194/isprs-annals-V-1-2021-17-2021)
- **Binet, R., Bergsma, E., & Poulain, V. (2022)**. *Accurate Sentinel-2 Inter-Band Time Delays*.  
  ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences, Vol. V-1-2022, pp. 57–66.  
  DOI: [10.5194/isprs-annals-V-1-2022-57-2022](https://doi.org/10.5194/isprs-annals-V-1-2022-57-2022)

---

## 9. License

This project is licensed under the [MIT License](LICENSE).
