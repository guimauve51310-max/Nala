# test_image_loader.py — test temporaire, à supprimer après
from src.core.image_loader import charger_image

entites, warnings = charger_image(
    "test_image.jpg",
    taille_mm=100.0,   # largeur cible 100 mm
    activer_lissage=True,
)

print(f"Entités : {len(entites)}")
print(f"Warnings :")
for w in warnings:
    print(f"  - {w}")

# Aperçu de la première entité
if entites:
    e = entites[0]
    print(f"\nPremière entité :")
    print(f"  type : {e.type_origine}")
    print(f"  calque : {e.calque}")
    print(f"  nb points : {len(e.points)}")
    print(f"  3 premiers points : {e.points[:3]}")

    # Bounding box globale
    xs = [p[0] for ent in entites for p in ent.points]
    ys = [p[1] for ent in entites for p in ent.points]
    print(f"\nBBox : X=[{min(xs):.2f}, {max(xs):.2f}]  Y=[{min(ys):.2f}, {max(ys):.2f}]")
    print(f"  → largeur = {max(xs)-min(xs):.2f} mm, hauteur = {max(ys)-min(ys):.2f} mm")