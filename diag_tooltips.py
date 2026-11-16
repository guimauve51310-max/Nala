# diag_tooltips.py — Script de diagnostic temporaire (à supprimer après)
# Cherche les boutons QPushButton qui n'ont pas de setToolTip()

import re
from pathlib import Path

FICHIERS = [
    Path("LaserCNC.py"),
    Path("src/ui/mise_en_page.py"),
]

# Regex pour trouver les lignes qui créent un QPushButton
PATTERN_BTN = re.compile(r'(\w+)\s*=\s*QPushButton\(')

# Regex pour trouver les setToolTip sur une variable
PATTERN_TOOLTIP = re.compile(r'(\w+)\.setToolTip\(')


def analyser_fichier(chemin):
    if not chemin.exists():
        print(f"  [ECHEC] Fichier introuvable : {chemin}")
        return
    
    texte = chemin.read_text(encoding="utf-8")
    lignes = texte.split("\n")
    
    boutons = {}  # nom -> ligne
    tooltips = set()
    
    for i, ligne in enumerate(lignes):
        # Cherche les créations de QPushButton
        for match in PATTERN_BTN.finditer(ligne):
            nom = match.group(1)
            boutons[nom] = i + 1
        
        # Cherche les setToolTip
        for match in PATTERN_TOOLTIP.finditer(ligne):
            nom = match.group(1)
            tooltips.add(nom)
    
    # Boutons sans tooltip
    sans_tooltip = {nom: ligne for nom, ligne in boutons.items() if nom not in tooltips}
    
    print(f"\n=== {chemin} ===")
    print(f"  Boutons trouvés : {len(boutons)}")
    print(f"  Tooltips trouvés : {len(tooltips)}")
    print(f"  Boutons SANS tooltip : {len(sans_tooltip)}")
    
    if sans_tooltip:
        print("\n  Liste des boutons sans tooltip :")
        for nom, ligne in sorted(sans_tooltip.items(), key=lambda x: x[1]):
            print(f"    Ligne {ligne:5d} : {nom}")


def main():
    print("=== DIAGNOSTIC TOOLTIPS ===")
    for chemin in FICHIERS:
        analyser_fichier(chemin)
    print("\n=== FIN DU DIAGNOSTIC ===")


if __name__ == "__main__":
    main()