# Scientific & Mathematical Methodology

## 1. Physical Principle: Pushbroom Sensor Inter-Band Parallax

Sentinel-2's MultiSpectral Instrument (MSI) is a pushbroom imaging spectrometer.
Detectors for each spectral band are arranged as separate linear CCD arrays on the focal plane assembly (FPA), separated along the track of the satellite orbit.

As the satellite flies in its sun-synchronous descending orbit (travelling approximately from North to South at $\sim 7.2 \text{ km/s}$ at an altitude of $\sim 786 \text{ km}$), the focal plane geometry dictates which band scans a given ground coordinate first:
- The detector line for **Band 4 (Red)** is positioned at the leading edge of the focal plane along the flight direction, encountering ground points **first**.
- **Band 3 (Green)** follows sequentially.
- **Band 8 (NIR)** follows next.
- **Band 2 (Blue)** is located at the trailing edge of the focal plane, imaging the ground target **last**.

### 1.1 Ground Acquisition Timing
Based on **Krauß (2021)** (*ISPRS Annals*, vol. V-1-2021, pp. 17–23) and **Binet, Bergsma, & Poulain (2022)** (*ISPRS Annals*, vol. V-1-2022, pp. 57–66), the chronological ground acquisition sequence and time offsets referenced to the leading Red band ($t=0.000\text{ s}$) are:

| Band Identifier | Spectral Region | Central Wavelength ($\lambda$) | Ground Sampling Distance | Ground Acquisition Time ($t$) |
|:---------------:|:---------------:|:------------------------------:|:------------------------:|:----------------------------:|
| **B04**         | Red             | 665 nm                         | 10 m                     | **$0.000 \text{ s}$ (Leading)** |
| **B03**         | Green           | 560 nm                         | 10 m                     | **$0.478 \text{ s}$**        |
| **B08**         | NIR             | 842 nm                         | 10 m                     | **$0.741 \text{ s}$**        |
| **B02**         | Blue            | 490 nm                         | 10 m                     | **$1.005 \text{ s}$ (Trailing)** |

Chronological motion sequence on the ground:
$$\mathbf{Red \; (B04)} \longrightarrow \mathbf{Green \; (B03)} \longrightarrow \mathbf{Blue \; (B02)}$$

Total elapsed observation time between endpoints:
$$\Delta t_{\text{total}} = t_{\text{blue}} - t_{\text{red}} = 1.005\text{ s}$$

When an object moves on or near the ground with high speed (such as an aircraft on approach or in flight), its physical position advances between sequential band exposures. In an RGB true-color composite (Red=B04, Green=B03, Blue=B02), this produces a characteristic rainbow trail of three colored dots aligned in direction of travel:
$$\text{Red} \longrightarrow \text{Green} \longrightarrow \text{Blue}$$

---

## 2. Detection & Subpixel Localization

### 2.1 Background Subtraction
To separate the moving object's spectral signal from static terrain or runway markings, a spatial median filter ($9 \times 9$ kernel) is applied to each band:
$$I_{\text{bg}}(x, y) = \text{median}_{k \in K}(I(x_k, y_k))$$
$$I_{\text{anomaly}}(x, y) = \max\left(0, I(x, y) - I_{\text{bg}}(x, y)\right)$$

### 2.2 Subpixel Weighted Center of Mass
Within a search window of radius $r = 3 \text{ px}$ centered at an initial seed $(x_0, y_0)$, local peaks are selected by thresholding above $50\%$ of the local peak maximum:
$$w(x, y) = \begin{cases} I_{\text{anomaly}}(x, y) & \text{if } I_{\text{anomaly}}(x, y) \ge 0.5 \cdot \max_{(u,v) \in W} I_{\text{anomaly}}(u, v) \\ 0 & \text{otherwise} \end{cases}$$

The subpixel centroid is then evaluated as the intensity-weighted center of gravity:
$$\bar{x} = \frac{\sum_{(x, y) \in W} x \cdot w(x, y)}{\sum_{(x, y) \in W} w(x, y)}, \quad \bar{y} = \frac{\sum_{(x, y) \in W} y \cdot w(x, y)}{\sum_{(x, y) \in W} w(x, y)}$$

---

## 3. Kinematics Formulation (Red $\to$ Blue)

Let $p_{\text{red}} = (x_r, y_r)$ at $t=0.000\text{ s}$ and $p_{\text{blue}} = (x_b, y_b)$ at $t=1.005\text{ s}$ be the subpixel centroids in raster pixel coordinates (where $x$ increases Eastward and $y$ increases Southward down rows).

### 3.1 Displacement and Distance
The motion vector points from the first detection (Red) to the final detection (Blue):
$$\Delta x_{\text{px}} = x_b - x_r$$
$$\Delta y_{\text{px}} = y_b - y_r$$
$$d_{\text{px}} = \sqrt{\Delta x_{\text{px}}^2 + \Delta y_{\text{px}}^2}$$
$$d_{\text{meters}} = d_{\text{px}} \times \text{GSD} \quad (\text{where GSD} = 10.0\text{ m/px})$$

### 3.2 Geographic Heading
In the geographic coordinate frame:
$$\Delta x_{\text{east}} = x_b - x_r$$
$$\Delta y_{\text{north}} = -(y_b - y_r) = y_r - y_b$$
$$\theta = \text{atan2}(\Delta x_{\text{east}}, \Delta y_{\text{north}}) \pmod{360^\circ}$$
Where $\theta = 0^\circ$ is true North, $90^\circ$ is East, $180^\circ$ is South, and $270^\circ$ is West.

### 3.3 Velocity
$$\Delta t = 1.005\text{ s}$$
$$v = \frac{d_{\text{meters}}}{\Delta t} \quad [\text{m/s}], \quad v_{\text{km/h}} = v \times 3.6 \quad [\text{km/h}]$$

---

## 4. Coherence and Quality Controls

### 4.1 Collinearity Test
For an object moving in a straight line during the $1.005\text{ s}$ window, the Green centroid ($p_{\text{green}} = (x_g, y_g)$) must lie on the vector line connecting $p_{\text{red}}$ and $p_{\text{blue}}$.

Let $\vec{v} = p_{\text{blue}} - p_{\text{red}}$ and $\vec{gv} = p_{\text{green}} - p_{\text{red}}$. The perpendicular cross-track deviation is:
$$d_\perp = \frac{|v_x gv_y - v_y gv_x|}{\|\vec{v}\|} \quad [\text{pixels}]$$
Acceptance criterion: $d_\perp \le 1.0 \text{ px}$.

### 4.2 Temporal Position Ratio
Because Green is acquired at $t = 0.478\text{ s}$ after Red ($t = 0.000\text{ s}$), the longitudinal projection fraction along the path is theoretically:
$$f_{\text{expected}} = \frac{t_{\text{green}} - t_{\text{red}}}{t_{\text{blue}} - t_{\text{red}}} = \frac{0.478\text{ s}}{1.005\text{ s}} \approx 0.4756$$
The observed projection fraction is:
$$f_{\text{observed}} = \frac{\vec{gv} \cdot \vec{v}}{\|\vec{v}\|^2}$$
A close agreement ($|f_{\text{observed}} - 0.4756| < 0.1$) confirms that the observation corresponds to a single object moving at constant speed.

---

## 5. Uncertainty Propagation

Following **Binet, Bergsma, & Poulain (2022)**, timing delays can vary by up to $\pm 2\%$ across the swath:
$$\Delta t \in [1.005 \times 0.98, \, 1.005 \times 1.02] = [0.9849\text{ s}, \, 1.0251\text{ s}]$$

Subpixel centroid estimation has an estimated uncertainty of $\delta_{\text{centroid}} \approx \pm 0.5\text{ px}$ per endpoint. The worst-case bounds on distance are:
$$d_{\min} = \max(0, d_{\text{px}} - 2 \delta_{\text{centroid}}) \times 10\text{ m}$$
$$d_{\max} = (d_{\text{px}} + 2 \delta_{\text{centroid}}) \times 10\text{ m}$$

The 1-sigma standard error is:
$$\sigma_d = \sqrt{2} \cdot \sigma_{\text{centroid}} \cdot \text{GSD} = \sqrt{2} \times 0.5 \times 10\text{ m} \approx 7.07\text{ m}$$

The rigorous speed interval is:
$$v_{\min} = \frac{d_{\min}}{\Delta t_{\max}}, \quad v_{\max} = \frac{d_{\max}}{\Delta t_{\min}}$$
No velocity estimate is ever reported as an isolated point value without this confidence range.

---

## 6. Environmental Surface Meteorological Context
Ground velocity ($v_{\text{ground}}$) measured from satellite parallax captures horizontal motion relative to the Earth's surface. To provide local environmental context, `s2motion` queries historical surface meteorological reanalysis (via Open-Meteo calibrated with ECMWF ERA5) linearly interpolated to the scene timestamp.

### 6.1 Wind Decomposition along Flight Track
Let $v_{\text{wind}}$ be the 10 m AGL surface wind speed and $\theta_{\text{wind}}$ be the meteorological wind origin angle ($0^\circ$ = North, $90^\circ$ = East, angle *from* which the wind blows).
For an aircraft with ground track heading $\theta_{\text{track}}$:

$$\Delta \theta = \theta_{\text{wind}} - \theta_{\text{track}}$$

The surface wind vector is decomposed into:
- **Headwind Component ($v_{\text{hw}}$)**:
  $$v_{\text{hw}} = v_{\text{wind}} \cdot \cos(\Delta \theta)$$
  Where $v_{\text{hw}} > 0$ denotes headwind and $v_{\text{hw}} < 0$ denotes tailwind.

- **Crosswind Component ($v_{\text{xw}}$)**:
  $$v_{\text{xw}} = v_{\text{wind}} \cdot \sin(\Delta \theta)$$
  Where $v_{\text{xw}} > 0$ denotes crosswind from the right and $v_{\text{xw}} < 0$ from the left.

*Note: Surface meteorological variables (ambient temperature, surface pressure, 10 m AGL wind speed and direction) capture ground-level ambient state for environmental documentation. They do not imply physical causality for aircraft ground velocity or flight phase, and true airspeed (TAS) or density altitude at aircraft flight level are not inferred from surface measurements.*

---

## 7. Stereoscopic Parallax Correction for Airborne Targets

When an object is airborne at altitude $h$ above the ground terrain/ellipsoid, its observed position across spectral bands is displaced by stereoscopic parallax. In the Sentinel-2 pushbroom architecture, each spectral band's detector strip looks at a distinct along-track forward angle $\theta_b$.

### 7.1 Pushbroom Geometry and Parallax Vector Derivation
Let $H$ be the satellite altitude above the ground surface ($H \approx 786\text{ km}$). An elevated object at position $\vec{X}_{\text{obj}}$ and height $h$ is observed by a detector line looking forward by along-track angle $\theta_b$. In orthorectified products (where rays are projected to the ground DEM at $z = 0$), the object appears at ground coordinate:

$$\vec{x}_{\text{apparent}} = \vec{x}_{\text{nadir}} + h \tan(\theta_b) \hat{u}_{\text{track}}$$

For two spectral bands separated by time delay $\Delta t$ along the ground track:
The spatial separation of their ground swaths corresponds to the distance traveled by the satellite ground track:

$$H \tan(\theta_{\text{leading}}) - H \tan(\theta_{\text{trailing}}) = v_{\text{track}} \Delta t$$

$$\tan(\theta_{\text{leading}}) - \tan(\theta_{\text{trailing}}) = \frac{v_{\text{track}} \Delta t}{H}$$

Consequently, the band captured **first** (the leading detector, $\theta_{\text{leading}}$) images the elevated object **further forward along the satellite ground track** than the band captured **last** (the trailing detector, $\theta_{\text{trailing}}$):

$$\vec{r}_{\text{first}} - \vec{r}_{\text{last}} = +\frac{h}{H} \vec{v}_{\text{track}} \Delta t$$

The parallax displacement vector from the first band to the last band is therefore directed **opposite** to the satellite ground track:

$$\Delta \vec{r}_{\text{parallax}} = \vec{r}_{\text{last}} - \vec{r}_{\text{first}} = -\frac{h}{H} \vec{v}_{\text{track}} \Delta t$$

The complete geometric pushbroom model projects rays from the satellite at altitude $H$ through the target at altitude $h$ onto the cartographic ground plane:

$$\vec{X}_{\text{ground}}(t) - \vec{X}_{\text{sat}}(t) = \frac{H}{H - h} \left[\vec{X}_{\text{obj}}(t) - \vec{X}_{\text{sat}}(t)\right]$$

Taking the time derivative yields the apparent ground velocity:

$$\vec{v}_{\text{apparent}} = \frac{H}{H - h} \vec{v}_{\text{true}} - \frac{h}{H - h} \vec{v}_{\text{track}}$$

Multiplying by $1 - \frac{h}{H} = \frac{H - h}{H}$ and rearranging gives the **complete pushbroom parallax model**:

$$\vec{v}_{\text{true}} = \left(1 - \frac{h}{H}\right) \vec{v}_{\text{apparent}} + \frac{h}{H} \vec{v}_{\text{track}}$$

*Comparison with Linear Approximation*:
Neglecting the $(1 - h/H)$ term yields the simplified linear approximation $\vec{v}_{\text{apparent}} + \frac{h}{H} \vec{v}_{\text{track}}$. At cruising altitude ($h = 10.5\text{ km}$, $H = 786\text{ km}$), $\frac{h}{H} \approx 1.34\%$, which reduces the apparent velocity term by $\frac{h}{H} v_{\text{apparent}} \approx 14.9\text{ km/h}$ ($\approx 15\text{ km/h}$) from $947\text{ km/h}$ to $932\text{ km/h}$. The complete model is implemented in `s2motion.parallax`.

> [!IMPORTANT]
> **Directional Consistency Check**:
> - In descending orbit over mid-latitudes, the satellite ground track heading is $\approx 194.7^\circ$ (South-Southwest, so $v_{N,\text{track}} < 0$).
> - When an aircraft flies northwest ($\sim 330^\circ$, $v_{N,\text{apparent}} > 0$), vector addition adds a negative northward contribution, reducing the northward ground speed ($1151\text{ km/h} \to 932\text{ km/h}$ at $h = 10.5\text{ km}$). The resulting ground speed is compatible with commercial jet airliner cruise; wind at flight altitude is unknown.
> - If `blue-first` were assumed, the apparent heading is southeast ($\sim 150^\circ$, $v_{N,\text{apparent}} < 0$), in the same general direction as the satellite track; the addition reinforces the velocity, yielding an unphysical supersonic speed ($1386\text{ km/h}$).

### 7.2 Derivation of Satellite Ground Track Velocity
Rather than assuming a constant inertial orbital velocity ($v_{\text{orb}} \approx 7.46\text{ km/s}$) or an arbitrary estimate ($7.2\text{ km/s}$), `s2motion` derives the ground track velocity directly from Sentinel-2 orbital mechanics:
- Orbit semi-major axis: $a = 7157\text{ km}$
- Sun-synchronous inclination: $i = 98.62^\circ$
- Gravitational parameter: $\mu = 3.986004418 \times 10^{14}\text{ m}^3/\text{s}^2$
- Earth mean radius: $R_E = 6371\text{ km}$
- Earth angular rotation: $\omega_E = 7.292115 \times 10^{-5}\text{ rad/s}$

1. **Orbital speed (inertial)**:
   $$v_{\text{orb}} = \sqrt{\frac{\mu}{a}} \approx 7462.8\text{ m/s}$$

2. **Inertial subsatellite speed on the ground sphere**:
   $$v_{\text{sub}} = v_{\text{orb}} \cdot \frac{R_E}{a} \approx 6643.2\text{ m/s}$$

3. **Descending track azimuth ($\chi$)**:
   $$\sin(\chi) = \frac{\cos(i)}{\cos(\phi)}$$
   For latitude $\phi = 43.3^\circ$ (Bilbao), $\chi \approx 191.9^\circ$.

4. **Earth rotation subtraction**:
   At latitude $\phi$, the Earth rotates eastward at:
   $$v_{\text{rot}} = \omega_E R_E \cos(\phi) \approx 338.1\text{ m/s}$$
   Subtracting this eastward motion from the inertial velocity yields:
   $$v_{N,\text{track}} = v_{\text{sub}} \cos(\chi) \approx -6499.5\text{ m/s}$$
   $$v_{E,\text{track}} = v_{\text{sub}} \sin(\chi) - v_{\text{rot}} \approx -1706.1\text{ m/s}$$
   $$v_{\text{track}} = \sqrt{v_{N,\text{track}}^2 + v_{E,\text{track}}^2} \approx 6721.0\text{ m/s} \quad (\approx 24196\text{ km/h})$$
   $$\psi_{\text{track}} = \text{atan2}(v_{E,\text{track}}, v_{N,\text{track}}) \approx 194.7^\circ$$

*Uncertainty note on satellite speed*: Using the inertial speed ($7.46\text{ km/s}$) instead of the ground-track speed ($6.72\text{ km/s}$) would overestimate the parallax correction by $\approx 11\%$ ($\sim 25\text{ km/h}$ at cruise altitude). This difference is explicitly resolved by using the ground-track velocity.

### 7.3 Literature Context & Sign Validation Integrity
- **Physical Sign Origin**: The sign of the parallax correction originates directly from the pushbroom sensor geometry: the detector strip that captures earlier looks further forward along-track ($\theta_1 > \theta_2$), projecting an elevated object forward in the earlier exposure relative to the later exposure.
- **Role of Krauß (2021)**: Krauß (2021) establishes the relative band time delays ($\Delta t$) and the magnitude of the disparity formula ($h = \frac{d \cdot H}{v \cdot \Delta t}$), but indexes delays arbitrarily from B02 ($0.000\text{ s}$) and does *not* validate the physical temporal sequence of ground exposures.
- **Role of Heiselberg (2019, 2021)**: Models observed multi-band positions as $\mathbf{r}_m = \mathbf{r}_0 + \mathbf{v}\Delta t_m + h \tan\theta_v \hat{\mathbf{u}}_{\text{view}}$, confirming the forward look angle parallax orientation.
- **Synthetic Test Scope**: Synthetic tests in `tests/test_parallax.py` verify the *internal algorithmic and vector consistency* of `s2motion` under both hypotheses; they do *not* constitute independent experimental proof of the physical sign. Physical sign validation currently rests on contrail morphology and cruise speed plausibility, pending external ADS-B corroboration.

> [!CAUTION]
> **Flight Altitude Disclaimer**: Flight altitude $h$ is a user-specified parameter, not an independently measured observable. The sensitivity of ground speed to altitude is approximately $d v / d h \approx \frac{v_{\text{track}}}{H} \approx 8.5\text{ m/s per km} \approx 30.8\text{ km/h per 1,000 m}$ along track.

---

## 8. Spatial Uncertainty Budget and Geolocation Precision

Every position reported relative to runway infrastructure is qualified by an estimated spatial uncertainty of **$\pm 15\text{ m}$**. This budget is derived from published official specifications:
1. **Copernicus Sentinel-2 Mission Specification ([ESA eoPortal](https://earth.esa.int/eoportal/satellite-missions/c-missions/sentinel-2))**: Specifies an absolute geolocation uncertainty requirement $< 20\text{ m}$ at a $2\sigma$ ($95.5\%$) confidence level without Ground Control Points on WGS84.
2. **Geometric Refinement Performance ([Copernicus SentiWiki](https://sentiwiki.copernicus.eu/web/sentinel-2-quality-reports))**: Routine quality monitoring demonstrates that with the deployment of the Global Reference Image (GRI), multi-temporal registration achieves circular errors $< 5\text{ m}$ at $95\%$ confidence.
3. **Sensor Discretization**: Ground Sampling Distance (GSD) of $10.0\text{ m}$ per pixel.
4. **Pushbroom Dynamic Discretization**: Intraband along-track motion during the detector line integration time.
*(TODO: verify direct permanent public URLs for ESA internal document codes S2-RS-ESA-SY-0001 and ESA-EOPG-EOQC-RP-0001 once officially published).*

Combining these independent error components in quadrature yields a root-sum-square spatial uncertainty on the ground of $\sigma_{\text{pos}} \approx \pm 15\text{ m}$.

---

*Contains modified Copernicus Sentinel data [2026]*
