# diag_svg.py — Afficher le contexte autour de la ligne 411
from pathlib import Path

FICHIER = Path("src/core/svg_loader.py")
texte = FICHIER.read_text(encoding="utf-8")
lignes = texte.split("\n")

# Afficher les lignes 395 à 435 (contexte autour de 411)
print("=== Contexte autour de la ligne 411 ===")
for i in range(395, min(436, len(lignes))):
    marker = " >>> " if i == 410 else "     "  # 410 = index 0-based de la ligne 411
    print(f"{marker}{i+1:4d}: {lignes[i]}")