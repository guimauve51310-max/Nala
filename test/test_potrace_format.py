# test_potrace_format.py
from PIL import Image
import numpy as np
from potrace import Bitmap

img = Image.open("test_image.jpg").convert("L")
gr = np.array(img, dtype=np.uint8)

# Masque correct : 1 = noir (à graver), 0 = blanc (fond)
masque = (gr < 128).astype(np.uint32)

print(f"Pixels à 1 : {masque.sum()} / {masque.size}")

for nom, tab in [
    ("uint32", masque),
    ("uint8", masque.astype(np.uint8)),
    ("bool", masque.astype(bool)),
]:
    try:
        bmp = Bitmap(tab)
        path = bmp.trace()
        courbes = list(path)
        print(f"\n--- {nom} → {len(courbes)} courbe(s) ---")
        for i, c in enumerate(courbes):
            print(f"  Courbe {i} : {len(c.decomposition_points)} pts, "
                  f"start=({c.start_point.x}, {c.start_point.y})")
    except Exception as e:
        print(f"\n--- {nom} → ERREUR : {e}")