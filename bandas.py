import numpy as np
import rasterio
import matplotlib.pyplot as plt
from pystac_client import Client
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

BBOX = (-2.945, 43.285, -2.875, 43.325)
FECHA = "2026-08-12"

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

bandas = [read_band(a) for a in ("red", "green", "blue")]
h = min(b.shape[0] for b in bandas)
w = min(b.shape[1] for b in bandas)
rgb = np.dstack([b[:h, :w] for b in bandas])
rgb = np.clip(rgb / np.percentile(rgb, 99), 0, 1)

fig, ax = plt.subplots(figsize=(12, 9))
ax.imshow(rgb, interpolation="nearest")
ax.set_title("Zoom con la lupa y pasa el ratón sobre el punto: x e y salen abajo a la derecha")
def onclick(e):
    if e.xdata is not None:
        print(f"x={e.xdata:.0f}  y={e.ydata:.0f}")
fig.canvas.mpl_connect("button_press_event", onclick)
plt.show()