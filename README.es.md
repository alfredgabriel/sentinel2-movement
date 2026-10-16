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
$$\mathbf{Rojo \; (B04)} \longrightarrow \mathbf{Verde \; (B03)} \longrightarrow \mathbf{Azul \; (B02)}$$

Un objeto que se desplaza a gran velocidad (como un avión durante el despegue) avanza sobre el terreno entre exposiciones consecutivas. En una composición RGB (Rojo=B04, Verde=B03, Azul=B02), se observa como **tres manchas de colores alineadas en el sentido de la marcha**:
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

# 3. Medir velocidad, rumbo, coherencia e incertidumbre con figura anotada
s2motion measure --config examples/loiu_2026-08-12.toml
```

---

## 4. Casos de uso incluidos

### Caso 1: Despegue por la pista 12 del Aeropuerto de Bilbao (2026-08-12)
- **Escenario**: Avión acelerando en la pista 12/30 (rumbo pista 12: $120.0^\circ$) hacia el sureste.
- **Sentido del movimiento**: Rojo $\to$ Verde $\to$ Azul.
- **Resultados medidos dinámicamente**:
  - **Distancia**: $82.4\text{ m}$ (rango: $72.4 - 92.4\text{ m}$).
  - **Rumbo**: **$117.4^\circ$** desde el norte (alineado con la pista 12 con desvío de solo **$2.6^\circ$**).
  - **Velocidad**: **$295\text{ km/h}$** (rango con incertidumbre: **$254 - 338\text{ km/h}$**).
  - **Colinealidad del verde**: $0.11\text{ px}$ (trayectoria recta prácticamente perfecta).
  - **Posición temporal del verde**: $0.47$ (esperado teórico: $0.48$, $\Delta < 0.01$).

![Despegue Loiu 2026-08-12](docs/img/loiu_2026-08-12_measured.png)

### Caso 2: Avión a alta cota con estela visible (2026-06-21)
- **Escenario**: Avión en crucero a gran altitud ($\approx 10\text{ km}$) rumbo noroeste ($330.4^\circ$).
- **Desplazamiento aparente**: $321.4\text{ m}$ ($1151\text{ km/h}$).
- **Demostración cualitativa**: A gran altura, el desplazamiento aparente mezcla la velocidad del avión con el paralaje estereoscópico inducido por la velocidad orbital del satélite ($\sim 7.2\text{ km/s}$).

![Avión a alta cota Loiu 2026-06-21](docs/img/loiu_2026-06-21_measured.png)

---

## 5. Resumen del método e incertidumbre

1. **Lectura por ventanas COG**: Consulta AWS Earth Search STAC y lee únicamente el bounding box con `rasterio` sin descargar los gigabytes de la escena completa.
2. **Resta de fondo**: Filtro de mediana $9 \times 9$ para eliminar marcas estáticas de la pista.
3. **Centroide subpíxel**: Centro de gravedad ponderado de los píxeles con intensidad $\ge 50\%$ del pico local (radio 3 px).
4. **Cinemática Rojo $\to$ Azul**: Vector de desplazamiento $p_{\text{azul}} - p_{\text{rojo}}$ evaluado en $\Delta t = 1.005\text{ s}$.
5. **Propagación rigurosa de errores**:
   - Error de localización de centroide $\pm 0.5\text{ px}$ por extremo.
   - Variabilidad temporal en $\Delta t$ de hasta $\pm 2\%$ por distorsión óptica y altura del satélite ([Binet et al., 2022](https://doi.org/10.5194/isprs-annals-V-1-2022-57-2022)).
   - La velocidad siempre se presenta en un rango de confianza $[v_{\min}, v_{\max}]$.

---

## 6. Limitaciones físicas y del sensor

- **Paralaje por altura**: La velocidad solo es cuantitativamente exacta para objetos en superficie o muy baja cota.
- **Sin identificación de vuelo**: No se identifica la matrícula o vuelo sin telemetría ADS-B cruzada.
- **Resolución espacial**: A $10\text{ m/px}$, una aeronave ocupa 3–4 píxeles (se mide la dispersión espectral, no la silueta).
- **Objetos lentos**: Embarcaciones a 15 nudos avanzan menos de un píxel en un segundo, requiriendo correlaciones de fase más complejas.

---

## 7. Referencias

- **Krauß, T. (2021)**. *Extraction of Cloud Heights from Sentinel-2 Multispectral Images*.  
  ISPRS Annals, Vol. V-1-2021, pp. 17–23. DOI: [10.5194/isprs-annals-V-1-2021-17-2021](https://doi.org/10.5194/isprs-annals-V-1-2021-17-2021)
- **Binet, R., Bergsma, E., & Poulain, V. (2022)**. *Accurate Sentinel-2 Inter-Band Time Delays*.  
  ISPRS Annals, Vol. V-1-2022, pp. 57–66. DOI: [10.5194/isprs-annals-V-1-2022-57-2022](https://doi.org/10.5194/isprs-annals-V-1-2022-57-2022)

---

## 8. Licencia

Distribuido bajo la [Licencia MIT](LICENSE).
