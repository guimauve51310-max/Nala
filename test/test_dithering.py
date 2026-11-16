# test_dithering.py — test temporaire, à supprimer après
import time
from src.core.dithering_loader import generer_gcode_photo

print("Début de la génération...")
t0 = time.time()

lignes, warnings = generer_gcode_photo(
    "test_image.jpg",      # ← ton image de test (cercle + triangle)
    largeur_mm=100.0,
    resolution_mm=0.1,
    vitesse=1500,
    puissance_max=1000,
    puissance_min=0,
    inverser=False,
)

t1 = time.time()

print(f"\n✅ Généré en {t1-t0:.2f} secondes")
print(f"Nombre de lignes G-code : {len(lignes)}")

print("\nWarnings :")
for w in warnings:
    print(f"  - {w}")

print("\n--- 15 premières lignes ---")
for l in lignes[:15]:
    print(l)

print("\n--- 15 dernières lignes ---")
for l in lignes[-15:]:
    print(l)