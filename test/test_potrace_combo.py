# test_potrace_combo.py
from PIL import Image
import numpy as np
from potrace import Bitmap

img = Image.open("test_image.jpg").convert("L")
gr = np.array(img, dtype=np.uint8)

for nom, seuil in [("seuil=128", 128), ("seuil=7 (Otsu)", 7)]:
    for inv_nom, inv in [("normal", False), ("inversé", True)]:
        binaire = (gr < seuil).astype(np.uint32)
        if inv:
            binaire = 1 - binaire
        bmp = Bitmap(binaire)
        path = bmp.trace()
        n = len(list(path))
        print(f"{nom:15s} {inv_nom:10s} → {n} courbe(s)")