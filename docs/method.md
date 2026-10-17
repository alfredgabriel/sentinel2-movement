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

## 6. Environmental Surface Meteorological Telemetry
Ground velocity ($v_{\text{ground}}$) measured from satellite parallax captures motion relative to the Earth's surface. To provide local environmental context, `s2motion` queries historical surface meteorological reanalysis (via Open-Meteo calibrated with ECMWF ERA5) linearly interpolated to the scene timestamp.

### 6.1 Wind Decomposition along Flight Track
Let $v_{\text{wind}}$ be the 10 m AGL surface wind speed and $\theta_{\text{wind}}$ be the meteorological wind origin angle ($0^\circ$ = North, $90^\circ$ = East, angle *from* which the wind blows).
For an aircraft with ground track heading $\theta_{\text{track}}$:

$$\Delta \theta = \theta_{\text{wind}} - \theta_{\text{track}}$$

The wind vector is decomposed into:
- **Headwind Component ($v_{\text{hw}}$)**:
  $$v_{\text{hw}} = v_{\text{wind}} \cdot \cos(\Delta \theta)$$
  Where $v_{\text{hw}} > 0$ denotes headwind and $v_{\text{hw}} < 0$ denotes tailwind.

- **Crosswind Component ($v_{\text{xw}}$)**:
  $$v_{\text{xw}} = v_{\text{wind}} \cdot \sin(\Delta \theta)$$
  Where $v_{\text{xw}} > 0$ denotes crosswind from the right and $v_{\text{xw}} < 0$ from the left.

### 6.2 Surface True Airspeed (TAS) Resolution
In flight mechanics, resolving True Airspeed ($v_{\text{TAS}}$) relative to ground speed ($v_{\text{GS}}$) and the along-track wind component is given by:

$$v_{\text{TAS}} = v_{\text{GS}} + v_{\text{hw}} = v_{\text{GS}} + v_{\text{wind}} \cdot \cos(\theta_{\text{wind}} - \theta_{\text{track}})$$

For low-altitude flight, this provides the aerodynamic speed relative to the local air mass.

### 6.3 Density Altitude (DA)
Under the International Standard Atmosphere (ICAO ISA):
- Sea level standard pressure: $P_0 = 1013.25\text{ hPa}$
- Sea level standard temperature: $T_0 = 15.0^\circ\text{C}$
- Lapse rate: $L = 0.0065\text{ K/m} \approx 1.98^\circ\text{C} / 1,000\text{ ft}$

From station elevation ($h_{\text{elev}}$) and observed surface pressure ($QNH$):

$$\text{PA} = h_{\text{elev}} + (1013.25 - QNH) \times 27.2\text{ ft/hPa}$$

The ISA standard temperature at this pressure altitude is:
$$T_{\text{ISA}} = 15^\circ\text{C} - 0.0019812 \times \text{PA}_{[\text{ft}]}$$

The **Density Altitude** (the altitude in the standard atmosphere at which the air density equals the observed air density) is:
$$\text{DA} = \text{PA} + 118.8 \cdot (T_{\text{observed}} - T_{\text{ISA}})$$

*Note: These meteorological parameters capture ground-level ambient state (10 m AGL) for contextual documentation and do not imply physical causality for aircraft ground velocity or flight phase.*
