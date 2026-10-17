# Sentinel-2 Movement (`s2motion`)

> **Detección, seguimiento y medición de velocidad de objetos en movimiento mediante el desfase temporal inter-banda del sensor pushbroom de Sentinel-2.**

*Documentación completa en inglés: [README.md](README.md).*

---

## 1. Fundamento físico

El sensor **MSI (MultiSpectral Instrument)** de **Sentinel-2** es de tipo **pushbroom**: las bandas espectrales se capturan mediante líneas de detectores CCD separadas físicamente en el plano focal a lo largo de la trayectoria orbital.

Dado que Sentinel-2 vuela en órbita descendente heliosíncrona (aproximadamente de Norte a Sur), la disposición geométrica de los detectores determina el orden en que barren cualquier punto de la superficie terrestre:
- La línea de detectores de la **Banda 4 (Rojo, 665 nm)** se encuentra en la posición delantera del plano focal y barre la superficie **en primer lugar** ($t = 0.000\text{ s}$).
- La **Banda 3 (Verde, 560 nm)** barre la superficie $0.478\text{ s}$ después.
- La **Banda 8 (NIR, 842 nm)** llega $0.741\text{ s}$ después.
- La **Banda 2 (Azul, 490 nm)** se sitúa en la parte posterior del plano focal y barre la superficie **en último lugar** ($t = 1.005\text{ s}$).

**Secuencia cronológica de adquisición sobre el terreno**:
### Secuencia física de adquisición en el suelo
Los retardos temporales entre bandas ($0.000, 0.264, 0.527, 1.005\text{ s}$) proceden de la literatura científica (Krauß 2021, Binet et al. 2022). La dirección cronológica (Rojo $\rightarrow$ Verde $\rightarrow$ Azul) se determinó empíricamente a partir de la orientación de la estela en el Caso 2 y la plausibilidad de la velocidad con corrección de paralaje (ver [docs/band-order.md](docs/band-order.md)). Ambos órdenes (`red-first` por defecto y `blue-first`) son configurables con `--band-order`.

Bajo la secuencia `red-first`:
$$\mathbf{Rojo \; (B04)} \longrightarrow \mathbf{Verde \; (B03)} \longrightarrow \mathbf{Azul \; (B02)}$$

Un objeto que se desplaza a gran velocidad (como un avión en vuelo o aproximación) avanza sobre su trayectoria entre exposiciones consecutivas. En una composición RGB (Rojo=B04, Verde=B03, Azul=B02), se observa como **tres manchas de colores alineadas en el sentido de la marcha**:
$$\text{Rojo} \longrightarrow \text{Verde} \longrightarrow \text{Azul}$$

---

## 2. Instalación rápida

Requiere Python $\ge 3.10$.

```bash
git clone https://github.com/alfredgabriel/sentinel2-movement.git
cd sentinel2-movement

python -m venv .venv
# En Windows:
.venv\Scripts\activate
# En Linux/macOS:
source .venv/bin/activate

pip install -e .
```

---

## 3. Inicio rápido (3 comandos)

```bash
# 1. Buscar y descargar recortes RGB de baja nubosidad en Loiu / Bilbao
s2motion crops --start 2026-08-01 --end 2026-08-15 --max-cloud 10 --out outputs/

# 2. Abrir el visor interactivo para localizar coordenadas de semillas
s2motion view --config examples/loiu_2026-08-12.toml

# 3. Medir velocidad, rumbo, coherencia e incertidumbre con figura anotada y contexto ambiental
s2motion measure --config examples/loiu_2026-08-12.toml --weather
```

---

## 4. Casos de uso incluidos

### Caso 1: Aeronave en aproximación a la pista 12, Aeropuerto de Bilbao (2026-08-12)
- **Escenario**: Aeronave alineada con la pista 12 del Aeropuerto de Bilbao (LEBB/BIO) (hipótesis de trabajo: aproximación final corta bajo `red-first`, pendiente de confirmación ADS-B).
- **Contexto espacial y georreferenciación**:
  - Coordenadas de los umbrales de la pista 12/30 según [ENAIRE AIP España (AD 2-LEBB)](https://aip.enaire.es/AIP/):
    - **THR 12 (NW)**: `43°18'22.85"N, 002°55'29.78"W` (`43.306347°N, -2.924939°W`)
    - **THR 30 (SE)**: `43°17'45.91"N, 002°53'49.02"W` (`43.296086°N, -2.896950°W`)
    - Eje geodésico calculado entre umbrales: **$116.7^\circ$** (la designación 12 está redondeada a $120^\circ$).
  - **Posición georreferenciada**: El blanco detectado (centroide de la banda Roja) se sitúa en **$43.310770^\circ\text{N}, -2.936874^\circ\text{W}$** (incertidumbre de posición estimada $\approx \pm 15\text{ m}$ por tamaño de píxel de 10 m, geolocalización de Sentinel-2 y desplazamiento del objeto durante el barrido), a aproximadamente **$1085 \pm 15\text{ m}$ al noroeste del umbral 12** sobre el eje prolongado ($-1085 \pm 15\text{ m}$ a lo largo de la prolongación) y a **$5.0 \pm 15.0\text{ m}$ de la línea central prolongada**.
  - **Estado**: La aeronave no está sobre la superficie de la pista (`is_on_runway: False`), sino en el pasillo de aproximación con rumbo **$117.4^\circ \pm 7.0^\circ$**, con una diferencia de rumbo de **$0.7^\circ (\pm 7.0^\circ)$** respecto al eje geodésico de la pista 12.

#### Vista general del recorte completo (Aeropuerto de Bilbao / Loiu)
![Vista general 2026-08-12](docs/img/loiu_2026-08-12_overview.png)

#### Análisis cinemático subpíxel y contexto ambiental
![Aproximación Loiu 2026-08-12](docs/img/loiu_2026-08-12_measured.png)

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

**Interpretación física y cinemática**:
- **Hipótesis de fase de vuelo**: La velocidad sobre el terreno de **$295\text{ km/h}$** ($82.0\text{ m/s}$ / $159\text{ kt}$) y el rumbo de **$117.4^\circ \pm 7.0^\circ$** a $1085 \pm 15\text{ m}$ del umbral son compatibles con un reactor comercial en aproximación final corta a la pista 12 bajo el orden `red-first`. Con `blue-first`, la misma geometría representaría un ascenso inicial tras despegue desde la pista 30 ($297.4^\circ \pm 7.0^\circ$). Sin datos ADS-B externos (pista en uso a las ~11:09 UTC), se documenta como hipótesis de trabajo sin validar (ver [docs/band-order.md](docs/band-order.md)).
- **Alineación con el eje de pista**: El rumbo medido ($117.4^\circ \pm 7.0^\circ$) difiere **$0.7^\circ (\pm 7.0^\circ)$** respecto al eje geodésico de la pista ($116.7^\circ$) calculado a partir de las coordenadas oficiales de los umbrales de ENAIRE AIP, sin interpretaciones cualitativas.
- **Contexto meteorológico de superficie**: El reanálisis de Open-Meteo ERA5 (interpolado a la hora de sensado del producto, $11:09:40\text{ UTC}$, teniendo en cuenta que el paso del satélite sobre el objeto puede diferir unos segundos) indica $28.9^\circ\text{C}$, QNH $1014.4\text{ hPa}$ y viento de superficie de $10.6\text{ km/h}$ desde $014^\circ$. Estos parámetros representan el contexto ambiental a 10 m de altura y no se emplean como explicación causal de la velocidad de la aeronave.

---

### Caso 2: Avión a alta cota con estela visible (2026-06-21)
- **Escenario**: Avión en crucero a gran altitud ($\approx 10 - 11\text{ km}$) rumbo noroeste ($330.4^\circ$).

#### Vista general de la escena con estela de condensación
![Vista general 2026-06-21](docs/img/loiu_2026-06-21_overview.png)

#### Cinemática subpíxel y corrección de paralaje
![Avión a alta cota Loiu 2026-06-21](docs/img/loiu_2026-06-21_measured.png)

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
------------------------------------------------------------
Stereoscopic Parallax Correction (Satellite Track: 6721 m/s, heading: 194.7°):
  - Target Altitude:          10500 m (range: 9000 - 12000 m)
  - Disclaimer:               Flight altitude is a user-specified parameter, not an independently measured observable.
  - Parallax Shift:           90.2 m along satellite track (323 km/h apparent contribution)
  - Apparent Velocity:        1151 km/h [319.8 m/s] | Heading: 330.4°
  - Parallax-Corrected Vel:   947 km/h [263.2 m/s] (range: 924 - 973 km/h) | Heading: 316.6° [-204 km/h vs apparent]
============================================================
```

**Interpretación y corrección de paralaje estereoscópico**:
- **Velocidad aparente sobre el suelo**: La velocidad aparente sin corregir es de **$1151\text{ km/h}$** ($319.8\text{ m/s}$), una cifra anómalamente elevada para un reactor comercial subsónico.
- **Origen físico**: En un blanco aéreo a cota de crucero, el desplazamiento inter-banda observado superpone el avance horizontal real del avión y el paralaje estereoscópico inducido por la velocidad de la traza subsatélite sobre el suelo ($v_{\text{track}} \approx 6.72\text{ km/s}$, rumbo $\approx 194.7^\circ$, derivada de la mecánica orbital).
- > [!CAUTION]
  > **Aviso sobre la altitud de vuelo**: La altitud de vuelo es un parámetro introducido por el usuario, no una magnitud medida de forma independiente. Se asume una cota nominal de crucero de $h = 10.5\text{ km}$ ($34.450\text{ ft}$) y un intervalo plausible de crucero de $[9.0, 12.0]\text{ km}$ ($29.500 - 39.400\text{ ft}$).
- **Comparativa entre hipótesis de orden de bandas**:
  - **Bajo `red-first` (por defecto)**: El avión vuela hacia el noroeste ($330.4^\circ$), en sentido opuesto al avance hacia el sur de la traza orbital ($194.7^\circ$). La corrección del paralaje hacia delante resta velocidad aparente:
    - Altitud nominal $h = 10.5\text{ km}$: **$v_{\text{real}} = 947\text{ km/h}$** ($263.2\text{ m/s}$), rumbo corregido **$316.6^\circ$** ($\Delta v = -204\text{ km/h}$ respecto a la aparente).
    - Intervalo de crucero $[9.0, 12.0]\text{ km}$: **$v_{\text{real}} \in [924, 973]\text{ km/h}$** (Mach $0.85 - 0.89$ a nivel de crucero), plenamente coherente con la envolvente de crucero de reactores comerciales modernos (A350, B787, B777).
  - **Bajo `blue-first` (contrahipótesis)**: La inversión del vector temporal sitúa el rumbo aparente hacia el sureste ($150.4^\circ$), en el mismo sentido general que el satélite. El paralaje se suma a la velocidad aparente:
    - Altitud nominal $h = 10.5\text{ km}$: **$v_{\text{real}} = 1401\text{ km/h}$** ($389.2\text{ m/s}$), rumbo corregido **$159.7^\circ$** ($\Delta v = +250\text{ km/h}$).
    - Intervalo de crucero $[9.0, 12.0]\text{ km}$: **$v_{\text{real}} \in [1363, 1439]\text{ km/h}$** (Mach $1.25 - 1.32$, régimen supersónico, físicamente inverosímil para aviación comercial civil).
- Para la derivación matemática completa, véase [docs/method.md](docs/method.md) y [docs/band-order.md](docs/band-order.md).

---

## 5. Resumen del método e incertidumbre

1. **Lectura por ventanas COG**: Consulta AWS Earth Search STAC y lee únicamente el bounding box con `rasterio` sin descargar los gigabytes de la escena completa.
2. **Resta de fondo**: Filtro de mediana $9 \times 9$ para eliminar marcas estáticas de la pista.
3. **Centroide subpíxel**: Centro de gravedad ponderado de los píxeles con intensidad $\ge 50\%$ del pico local (radio 3 px).
4. **Cinemática vectorial**: Vector de desplazamiento entre bandas extremas evaluado en $\Delta t = 1.005\text{ s}$.
5. **Propagación rigurosa de errores**:
   - Error de localización de centroide $\pm 0.5\text{ px}$ por extremo.
   - Incertidumbre de geolocalización espacial de $\pm 15\text{ m}$ calibrada contra especificaciones oficiales de Sentinel-2 (ESA MRD S2-RS-ESA-SY-0001, error circular $<10\text{ m}$ al 95.5% de confianza según Copernicus DQR ESA-EOPG-EOQC-RP-0001 con GRI).
   - Variabilidad temporal en $\Delta t$ de hasta $\pm 2\%$ por distorsión óptica y perturbaciones de altura del satélite ([Binet et al., 2022](https://doi.org/10.5194/isprs-annals-V-1-2022-57-2022)).
   - La velocidad siempre se presenta en un rango de confianza $[v_{\min}, v_{\max}]$.
6. **Telemetría meteorológica de superficie**: Consulta a Open-Meteo para documentar la temperatura ambiente local, presión y viento a 10 m AGL como contexto ambiental de superficie.
7. **Corrección estereoscópica de paralaje para blancos aéreos**: Modela el ángulo de mira a lo largo de la traza entre bandas mediante la velocidad de la traza subsatélite ($v_{\text{track}} \approx 6.72\text{ km/s}$ derivada de la órbita) para corregir la velocidad aparente a la altitud introducida por el usuario.

---

## 6. Limitaciones físicas y del sensor

- **Paralaje por altura**: La velocidad solo es cuantitativamente exacta sin correcciones para objetos en superficie o muy baja cota. Para aeronaves en crucero se requiere modelar la altitud del blanco.
- **Sin identificación de vuelo**: No se identifica la matrícula o vuelo sin telemetría ADS-B cruzada.
- **Resolución espacial**: A $10\text{ m/px}$, una aeronave ocupa 3–4 píxeles (se mide la dispersión espectral, no la silueta).
- **Objetos lentos**: Embarcaciones a 15 nudos avanzan menos de un píxel en un segundo, requiriendo correlaciones de fase más complejas.

---

## 7. Referencias

- **Krauß, T. (2021)**. *Extraction of Cloud Heights from Sentinel-2 Multispectral Images*.  
  ISPRS Annals, Vol. V-1-2021, pp. 17–23. DOI: [10.5194/isprs-annals-V-1-2021-17-2021](https://doi.org/10.5194/isprs-annals-V-1-2021-17-2021)
- **Binet, R., Bergsma, E., & Poulain, V. (2022)**. *Accurate Sentinel-2 Inter-Band Time Delays*.  
  ISPRS Annals, Vol. V-1-2022, pp. 57–66. DOI: [10.5194/isprs-annals-V-1-2022-57-2022](https://doi.org/10.5194/isprs-annals-V-1-2022-57-2022)
- **Heiselberg, H. (2019)**. *Aircraft and Ship Velocity Determination in Sentinel-2 Multispectral Images*.  
  Sensors, 19(13), 2873. DOI: [10.3390/s19132873](https://doi.org/10.3390/s19132873)
- **Heiselberg, H. (2021)**. *Aircraft Detection above Clouds by Sentinel-2 MSI Parallax*.  
  Remote Sensing, 13(12), 2327. DOI: [10.3390/rs13122327](https://doi.org/10.3390/rs13122327)
- **European Space Agency (ESA)**. *Sentinel-2 Mission Requirements Document (MRD)*, S2-RS-ESA-SY-0001; y *Copernicus Sentinel-2 Data Quality Report*, ESA-EOPG-EOQC-RP-0001.

---

## 8. Licencia

Distribuido bajo la [Licencia MIT](LICENSE).
