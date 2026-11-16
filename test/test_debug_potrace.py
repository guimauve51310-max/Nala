# test_debug_potrace.py
from PIL import Image
import numpy as np
from src.core.image_loader import _seuil_otsu, _preparer_masque_binaire

chemin = "test_image.jpg"  # ← adapte au nom de ton image

# --- 1. Infos image ---
img = Image.open(chemin)
print(f"1. Taille : {img.size}  Mode : {img.mode}")

gr = np.array(img.convert("L"))
print(f"2. Min/Max/Moy : {gr.min()} / {gr.max()} / {gr.mean():.1f}")

# --- 2. Seuil Otsu ---
seuil = _seuil_otsu(gr)
print(f"3. Seuil Otsu : {seuil}")

# --- 3. Masque binaire ---
binaire, s, w, h = _preparer_masque_binaire(chemin, seuil=None, inverser=False)
noirs = int(binaire.sum())
total = w * h
print(f"4. Pixels noirs : {noirs} / {total} = {100*noirs/total:.2f}%")
print(f"5. dtype binaire : {binaire.dtype}  shape : {binaire.shape}")

# --- 4. Appel direct à potrace ---
from potrace import Bitmap
print("\n--- Appel direct potrace ---")
bmp = Bitmap(binaire)
path = bmp.trace()
print(f"6. Nombre de courbes retournées : {len(list(path))}")

for i, curve in enumerate(path):
    print(f"   Courbe {i} : {len(curve.decomposition_points)} points, "
          f"start=({curve.start_point.x}, {curve.start_point.y})")