# Sentinel-2 Pushbroom Inter-Band Temporal Delays & Band Order Determination

## 1. Physical Sensor Architecture
The MultiSpectral Instrument (MSI) aboard Sentinel-2A and Sentinel-2B is a pushbroom imaging sensor. It acquires Earth observation swaths using two separate focal planes:
- **VNIR (Visible and Near-Infrared) Focal Plane**: houses detectors for bands B02 (Blue), B03 (Green), B04 (Red), and B08 (NIR), alongside narrow atmospheric bands.
- **SWIR (Short-Wave Infrared) Focal Plane**: houses detectors for SWIR bands (B11, B12, etc.).

Because the individual spectral band filter strips are spatially displaced along the flight direction on the focal plane, a given ground point is not observed simultaneously by all bands. As the satellite progresses along its sun-synchronous descending orbit (southward at ~7.46 km/s orbital speed, ~6.7 km/s ground track speed), each spectral band passes over the target at a distinct time offset.

For stationary terrain, standard Level-1C/Level-2A ortho-rectification registers the bands to a common cartographic grid (WGS84 / UTM). However, for fast-moving targets (e.g. aircraft), this inter-band delay causes chromatic separation: the object appears at a slightly different pixel location in each spectral band.

---

## 2. Band Delays in Scientific Literature vs Ground Sequence

### 2.1 Literature Values
Published literature provides the physical spacing delays between the 10 m VNIR bands. In particular, **Krauß (2021)** (*Extraction of Cloud Heights from Sentinel-2 Multispectral Images*, Table 1) and **Binet et al. (2022)** (*Accurate Sentinel-2 Inter-Band Time Delays*) report the following relative delays, indexed relative to Band 2 (Blue):

| Band Identifier | Spectral Name | Central Wavelength ($\lambda$) | Relative Delay in Krauß (2021) |
|---|---|---|---|
| **B02** | Blue | 490 nm | **0.000 s** (reference index) |
| **B08** | NIR | 842 nm | **+0.264 s** |
| **B03** | Green | 560 nm | **+0.527 s** |
| **B04** | Red | 665 nm | **+1.005 s** |

### 2.2 Table Indexing vs Physical Temporal Direction
A common source of ambiguity in the remote sensing literature is whether tabular values represent **time elapsed since the first detector crossed the target** or **offsets relative to an arbitrarily chosen reference band (B02)**:

- **Table Convention (`blue-first`)**: If B02 is physically the leading detector along-track, the sequence of exposures on the ground is Blue $\rightarrow$ NIR $\rightarrow$ Green $\rightarrow$ Red.
- **Empirical Convention (`red-first`)**: If B04 is physically the leading detector along-track, the sequence of ground exposures is Red $\rightarrow$ Green $\rightarrow$ NIR $\rightarrow$ Blue:
  $$\Delta t_{\text{Red}} = 0.000\text{ s}$$
  $$\Delta t_{\text{Green}} = 1.005 - 0.527 = 0.478\text{ s}$$
  $$\Delta t_{\text{NIR}} = 1.005 - 0.264 = 0.741\text{ s}$$
  $$\Delta t_{\text{Blue}} = 1.005\text{ s}$$

Under both hypotheses, the total elapsed time between Red and Blue is identical ($\Delta t = 1.005\text{ s}$), and the relative position of Green between the two endpoints is nearly symmetric:
- **Red $\rightarrow$ Blue (`red-first`)**: Expected Green fraction = $0.478 / 1.005 \approx 0.4756$ ($47.6\%$)
- **Blue $\rightarrow$ Red (`blue-first`)**: Expected Green fraction = $0.527 / 1.005 \approx 0.5244$ ($52.4\%$)

Because both conventions exhibit near-perfect longitudinal linearity and near-identical fractions ($\sim 48\%$ vs $\sim 52\%$), 3-band geometric collinearity alone **cannot** resolve the temporal sign.

---

## 3. Why Runway Centerline Alignment Does Not Discriminate Band Order

In Case 1 (Bilbao Airport, 2026-08-12), the aircraft is positioned northwest of Runway 12/30 ($43.310770^\circ\text{N}, -2.936874^\circ\text{W} \pm 15\text{ m}$), approximately $1085 \pm 15\text{ m}$ from Threshold 12 along the extended centerline:

- Official Runway 12/30 threshold bearings (ENAIRE AIP España):
  - **Runway 12 true bearing**: **$116.7^\circ$** (Southeast)
  - **Runway 30 true bearing**: **$296.7^\circ$** (Northwest, $116.7^\circ + 180^\circ$)

Applying each band order convention to the observed centroids:
1. **Under `red-first` (Red $\rightarrow$ Blue)**:
   - Heading = **$117.4^\circ \pm 7.0^\circ$** (towards $117.4^\circ$, Southeast).
   - Acute angle with Runway 12 axis: **$0.7^\circ$**.
   - Flight scenario: Aircraft heading Southeast, descending along the extended centerline towards Threshold 12 (**final approach to Runway 12**).
2. **Under `blue-first` (Blue $\rightarrow$ Red)**:
   - Vector inverts: $dx \rightarrow -dx, dy \rightarrow -dy$.
   - Heading rotates $180^\circ$: $117.4^\circ + 180^\circ =$ **$297.4^\circ \pm 7.0^\circ$** (towards $297.4^\circ$, Northwest).
   - Acute angle with Runway 30 axis: $|297.4^\circ - 296.7^\circ| =$ **$0.7^\circ$**.
   - Flight scenario: Aircraft heading Northwest, climbing out along the extended centerline after takeoff from Runway 30 (**initial climb after departure from Runway 30**).

> [!IMPORTANT]
> **Geometric runway alignment is completely symmetric modulo $180^\circ$.**
> Runway alignment does **not** break the band order symmetry: both hypotheses yield a flight path aligned within $0.7^\circ$ of an active runway axis at Bilbao Airport. The hypothesis that Case 1 represents an "approach to runway 12" is **strictly conditional** on assuming the `red-first` band order.

---

## 4. Empirical Evidence Supporting `red-first`

Because runway geometry and 3-band collinearity cannot discriminate the order, `s2motion` establishes the default `red-first` convention from two independent physical observations:

### 4.1 Case 2: Contrail Morphology (Spatial Orientation)
In Case 2 (2026-06-21, high-altitude airliner), the aircraft produces a visible condensation trail (contrail):
- Physical principle: An aircraft in flight leaves an exhaust condensation trail trailing *behind* its current position.
- In the Sentinel-2 image, the contrail extends towards the southeast, extending outwards from the **Red** centroid, while the **Blue** centroid is positioned furthest along the flight direction towards the northwest ($330.4^\circ$).
- For the contrail to trail behind the airframe, the aircraft must occupy the Red position at the earlier timestamp and the Blue position at the later timestamp ($t_{\text{red}} < t_{\text{blue}}$).

### 4.2 High-Altitude Parallax Velocity Plausibility
In Case 2, the apparent uncorrected displacement between endpoints is $321.4 \pm 7.1\text{ m}$ over $1.005\text{ s}$, yielding an uncorrected apparent ground velocity of $1151\text{ km/h}$ ($319.8\text{ m/s}$).

Because the aircraft is flying at cruise altitude ($h \approx 10.5\text{ km}$), the satellite's orbital velocity ($\approx 7.46\text{ km/s}$, ground track velocity $\approx 6.7\text{ km/s}$) induces significant stereoscopic parallax:
- Satellite ground track moves southward (azimuth $\approx 190^\circ - 195^\circ$).
- Aircraft is flying northwest ($330.4^\circ$), moving in the opposite general direction to the satellite track.
- **Under `red-first`**: The apparent displacement represents real aircraft displacement plus forward parallax, so the true horizontal aircraft velocity is *lower* than the raw apparent velocity:
  $$v_{\text{true}} \approx 1151\text{ km/h} - v_{\text{parallax}} \approx 850 - 920\text{ km/h} \quad (\text{Mach } 0.78 - 0.84)$$
  This is the standard cruise speed regime for commercial jet transports (A320, B737).
- **Under `blue-first`**: Reversing the time vector inverts the sign of the kinematic motion while parallax geometry remains tied to sensor motion, leading to a calculated aircraft speed exceeding $\approx 1400\text{ km/h}$ (supersonic, Mach $> 1.2$), which is physically implausible for civil commercial air traffic.

---

## 5. Definitive Resolution: External ADS-B Validation

While contrail morphology and aerodynamic speed plausibility strongly support `red-first`, the definitive ground truth resolution requires:
1. **ADS-B State Vectors**: External ADS-B / Mode-S transponder records (from FlightAware, The OpenSky Network, or Flightradar24) matching the scene location.
2. **Active Runway at Bilbao Airport (LEBB)**: Confirming whether Runway 12 or Runway 30 was operational at **11:09 UTC on 2026-08-12**. If arrivals were landing on Runway 12, `red-first` is corroborated; if departures were taking off from Runway 30, `blue-first` would be corroborated.

### Note on Scene Timestamp vs Overpass Time
The datetime string recorded in the STAC metadata (`2026-08-12T11:09:39.516000Z`) corresponds to the **product sensing start time** for the entire datastrip or tile acquisition. Depending on the along-track position of the target within the swath, the actual overpass of the satellite over the moving aircraft may differ by several seconds from the product metadata timestamp. External ADS-B queries should allow a temporal window of $\pm 30\text{ s}$ around 11:09:40 UTC.

---

## 6. Configurable CLI & Python API Usage

To ensure scientific integrity and allow researchers to test both hypotheses, `s2motion` provides `--band-order` in both the CLI and Python API:

```bash
# Default (empirically determined): Red -> Green -> Blue
s2motion measure --config examples/loiu_2026-08-12.toml --band-order red-first

# Alternate hypothesis: Blue -> Green -> Red
s2motion measure --config examples/loiu_2026-08-12.toml --band-order blue-first
```

In Python:
```python
from s2motion.measure import calculate_motion

result_red = calculate_motion(
    red_centroid=(66.0, 158.6),
    blue_centroid=(73.3, 154.9),
    green_centroid=(69.4, 156.9),
    band_order="red-first",
)
# result_red.heading_deg == 117.4 deg

result_blue = calculate_motion(
    red_centroid=(66.0, 158.6),
    blue_centroid=(73.3, 154.9),
    green_centroid=(69.4, 156.9),
    band_order="blue-first",
)
# result_blue.heading_deg == 297.4 deg
```
