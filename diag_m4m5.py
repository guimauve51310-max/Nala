# diag_m4m5.py — Script de diagnostic temporaire (à supprimer après)
# Cherche les occurrences suspectes de M4 et M5 dans LaserCNC.py

import re
from pathlib import Path

FICHIER = Path("LaserCNC.py")

if not FICHIER.exists():
    print(f"Fichier introuvable : {FICHIER}")
    exit(1)

texte = FICHIER.read_text(encoding="utf-8")
lignes = texte.split("\n")

print("=== RECHERCHE DES PATTERNS M4/M5 ===\n")

print("--- Occurrences de M4 (hors 'M4 S...') ---")
for i, ligne in enumerate(lignes, 1):
    if 'M4' in ligne and 'M4 S' not in ligne and 'M4 ;' not in ligne:
        print(f"  Ligne {i}: {ligne.strip()}")

print("\n--- Occurrences de M5 ---")
for i, ligne in enumerate(lignes, 1):
    if 'M5' in ligne:
        print(f"  Ligne {i}: {ligne.strip()}")

print("\n=== FIN DE LA RECHERCHE ===")