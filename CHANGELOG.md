# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-18

### Added
- **Multi-Band Spectral Panels**: Side-by-side visualization of individual spectral bands (`B04`, `B08`, `B03`, `B02`) with subpixel centroid positions marked chronologically.
- **Pixel Grid Zoom Visualizations**: High-zoom RGB composites featuring $10\text{ m/px}$ detector pixel boundaries, subpixel centroid markers, and flight trajectory arrows.
- **4:5 Social Media Cards**: Dark-mode graphics (1080x1350 px) formatted for technical dissemination on LinkedIn/Twitter, featuring $2\sigma$ uncertainties, "apparent / corrected" speed tags, Copernicus attribution, and explicit disclaimers (*"sin validar con datos externos"* / *"not validated with external data"*).
- **Bilingual Support**: `--lang es|en` CLI switch for figure generation and social cards text (defaults to Spanish).
- **Offline Figure Generator**: `scripts/generate_figures.py` reproducing all 10 documentation and social figures from offline fixtures in `examples/data/` without network access.
- **Offline Data Fixtures**: Small windowed arrays in `examples/data/loiu_2026-08-12.npz` and `examples/data/loiu_2026-06-21.npz` containing all necessary spectral bands and georeferencing metadata.
- **Pushbroom Parallax Correction**: Analytical physical model ($\vec{v}_{\text{real}} = (1 - h/H)\vec{v}_{\text{apparent}} + (h/H)\vec{v}_{\text{track}}$) driven by satellite ground-track velocity ($v_{\text{track}} \approx 6.72\text{ km/s}$, heading $\approx 194.7^\circ$) derived from orbital mechanics.
- **Offline ADS-B Validation Module**: `s2motion validate` supporting OpenSky Network CSV and ADS-B Exchange JSON trajectories with linear segment interpolation, Closest Point of Approach (CPA), candidate listing without cherry-picking, combined heading tolerance ($\pm 6.1^\circ$ at $2\sigma$), and geometric altitude over terrain ($h_{\text{AGL}}$).
- **Unit Test Suite**: 82 comprehensive unit tests spanning detection, kinematics, geodesy, aerodynamics, parallax, STAC handling, ADS-B validation, and visualization with zero network dependencies.

### Changed
- **Velocity Interval Reporting**: Replaced single-point speed values with explicit propagated uncertainty intervals $[v_{\min}, v_{\max}]$ incorporating $\pm 0.5\text{ px}$ centroid error, $\pm 2\%$ inter-band timing distortion, and altitude range.
- **Runway Positioning Error Budget**: Calibrated absolute position uncertainty against external aeronautical cartography (ENAIRE AIP) to $\pm 25\text{ m}$ at $\sim 2\sigma$ based on the ESA Sentinel-2 global absolute geolocation specification ($<20\text{ m}$ 2σ without GCPs on WGS84).
- **Symmetric Runway Alignment Clarification**: Documented in `docs/band-order.md` that runway axis alignment is symmetric modulo $180^\circ$ and does not discriminate between `red-first` (approach) and `blue-first` (departure).
- **Contrail Comparison Convention**: Corrected contrail angular difference to compare undirected axes modulo $180^\circ$ in $[-90^\circ, +90^\circ]$, and removed exploratory contrail coordinates from active documentation pending definitive user input.
- **Rigorous Validation Status Table**: Categorized all repository components into "respaldada por literatura", "coherente internamente", and "pendiente de contraste ADS-B", eliminating unwarranted assertions of external robustness.
- **Verified Scientific Citations**: Upgraded literature citations with verified DOIs (Krauß 2021, Binet et al. 2022, Heiselberg 2019, Heiselberg & Heiselberg 2021) and official Copernicus SentiWiki / ESA eoPortal documentation links.

## [0.1.0] - 2026-08-15

### Added
- Initial proof-of-concept release.
- Windowed Remote COG reading via AWS Earth Search STAC (`sentinel-2-l2a`).
- Subpixel centroid calculation via local median background subtraction and intensity-weighted center of mass.
- Apparent displacement velocity and heading estimation between Red and Blue bands.
- Interactive pixel inspector (`s2motion view`).
- TOML scenario configuration parsing.
- Initial case studies: approach to Bilbao Airport Runway 12 (`loiu_2026-08-12`) and high-altitude flight (`loiu_2026-06-21`).
