import numpy as np
import rasterio
import matplotlib.pyplot as plt
from pystac_client import Client
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from scipy.ndimage import median_filter

BBOX = (-2.945, 43.285, -2.875, 43.325)
FECHA = "2026-08-12"

# Posiciones aproximadas (x, y) medidas con el ratón en ver.py
SEMILLAS = {"red": (66, 158), "green": (70, 160), "blue": (74, 162)}
EJE_PISTA = 120.0   # rumbo aproximado de la pista 12/30 (grados desde el norte)
PX = 10.0           # metros por píxel

catalog = Client.open("https://earth-search.aws.element84.com/v1")
item = catalog.search(
    collections=["sentinel-2-l2a"], bbox=BBOX,
    datetime=f"{FECHA}T00:00:00Z/{FECHA}T23:59:59Z",
).item_collection()[0]

def read_band(asset):
    with rasterio.open(item.assets[asset].href) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *BBOX)
        win = from_bounds(*bounds, transform=src.transform)
        return src.read(1, window=win).astype("float32")

bandas = {n: read_band(n) for n in SEMILLAS}
h = min(b.shape[0] for b in bandas.values())
w = min(b.shape[1] for b in bandas.values())
bandas = {n: b[:h, :w] for n, b in bandas.items()}

def centroide(banda, x0, y0, radio=3):
    # Resta el fondo local para quedarnos solo con lo que destaca
    anom = np.clip(banda - median_filter(banda, size=9), 0, None)
    ys, xs = np.mgrid[y0 - radio:y0 + radio + 1, x0 - radio:x0 + radio + 1]
    sub = anom[y0 - radio:y0 + radio + 1, x0 - radio:x0 + radio + 1]
    sub = np.where(sub >= 0.5 * sub.max(), sub, 0)   # solo el pico principal
    return np.array([(xs * sub).sum() / sub.sum(), (ys * sub).sum() / sub.sum()])

pos = {n: centroide(bandas[n], *SEMILLAS[n]) for n in SEMILLAS}
for n, p in pos.items():
    print(f"{n:6s}: x={p[0]:.2f}  y={p[1]:.2f}")

r, g, b = pos["red"], pos["green"], pos["blue"]
v = b - r
dist = np.hypot(*v) * PX
rumbo = np.degrees(np.arctan2(v[0], -v[1])) % 360      # 0° = norte, sentido horario
gv = g - r
perp = abs(v[0] * gv[1] - v[1] * gv[0]) / np.hypot(*v)  # desviación del verde (px)
frac = np.dot(gv, v) / np.dot(v, v)                     # posición relativa del verde
dif = abs((rumbo - EJE_PISTA + 90) % 180 - 90)

print(f"\nDesplazamiento rojo→azul: {dist:.0f} m, rumbo {rumbo:.0f}°")
print(f"Diferencia con el eje de la pista ({EJE_PISTA:.0f}°): {dif:.1f}°")
print(f"Desviación del verde respecto a la recta rojo-azul: {perp:.2f} px")
print(f"Posición relativa del verde entre rojo (0) y azul (1): {frac:.2f}")
print("\nVelocidad implícita según el desfase Δt entre rojo y azul:")
for dt in (0.25, 0.5, 1.0, 1.5):
    print(f"  Δt={dt:4.2f} s -> {dist / dt * 3.6:6.0f} km/h")

# Imagen de comprobación
rgb = np.dstack([bandas[k] for k in ("red", "green", "blue")])
rgb = np.clip(rgb / np.percentile(rgb, 99), 0, 1)
x0, y0 = SEMILLAS["green"]
fig, ax = plt.subplots(figsize=(8, 8))
ax.imshow(rgb, interpolation="nearest")
for n, c in zip(("red", "green", "blue"), ("red", "lime", "cyan")):
    ax.plot(*pos[n], "o", mfc="none", mec=c, ms=14, mew=2)
ax.set_xlim(x0 - 15, x0 + 15)
ax.set_ylim(y0 + 15, y0 - 15)
plt.savefig("analisis.png", dpi=150)
plt.show()