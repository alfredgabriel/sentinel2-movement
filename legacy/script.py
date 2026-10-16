# pip install pystac-client rasterio numpy matplotlib
import numpy as np
import rasterio
import matplotlib.pyplot as plt
from pystac_client import Client
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

# Entorno del aeropuerto de Loiu (lon_min, lat_min, lon_max, lat_max)
BBOX = (-2.945, 43.285, -2.875, 43.325)

catalog = Client.open("https://earth-search.aws.element84.com/v1")
items = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=BBOX,
    datetime="2025-01-01/2026-09-30",
    query={"eo:cloud_cover": {"lt": 10}},
).item_collection()
print(len(items), "escenas con poca nube")

def read_band(item, asset):
    with rasterio.open(item.assets[asset].href) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *BBOX)
        win = from_bounds(*bounds, transform=src.transform)
        return src.read(1, window=win).astype("float32")

for item in items:
    bands = [read_band(item, a) for a in ("red", "green", "blue")]
    h = min(b.shape[0] for b in bands)
    w = min(b.shape[1] for b in bands)
    rgb = np.dstack([b[:h, :w] for b in bands])

    # Estiramiento de contraste y ampliación x4 sin suavizar
    rgb = np.clip(rgb / np.percentile(rgb, 99), 0, 1)
    rgb = np.kron(rgb, np.ones((4, 4, 1)))

    fecha = item.properties["datetime"][:10]
    plt.imsave(f"loiu_{fecha}.png", rgb)