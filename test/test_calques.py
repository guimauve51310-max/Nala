# =============================================================================
# test_calques.py
# -----------------------------------------------------------------------------
# Rôle : Diagnostiquer pourquoi les pastilles de couleur et les entités
#        apparaissent toutes en noir, alors que Calque fonctionne bien.
# =============================================================================

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

# Crée une app Qt minimale (nécessaire pour instancier des widgets)
app = QApplication(sys.argv)

print("=== Diagnostic des calques ===\n")

# --- Test 1 : la classe Calque ---
from src.core.calque import Calque
c1 = Calque("TestManuel", "#c0392b")
print(f"1) Calque manuel :")
print(f"   nom       = {c1.nom}")
print(f"   couleur   = {c1.couleur.name()}")
print(f"   couleur_hex = {c1.couleur_hex()}")

# --- Test 2 : la palette du widget ---
print(f"\n2) Palette du widget (src.ui.mise_en_page.PALETTE_CALQUES) :")
from src.ui.mise_en_page import PALETTE_CALQUES
for i, c in enumerate(PALETTE_CALQUES):
    print(f"   [{i}] {c.name()}")

# --- Test 3 : on instancie le widget et on crée un calque ---
print(f"\n3) Instanciation du widget et création d'un calque :")
from src.ui.mise_en_page import MiseEnPageWidget
w = MiseEnPageWidget()

# On simule ce que fait creer_calque() sans passer par le QInputDialog
index_nouveau = len(w.calques) % len(PALETTE_CALQUES)
couleur = PALETTE_CALQUES[index_nouveau]
print(f"   len(w.calques) = {len(w.calques)}")
print(f"   index_nouveau  = {index_nouveau}")
print(f"   couleur choisie = {couleur.name()}")

nouveau_calque = Calque("TestUI", couleur)
w.calques.append(nouveau_calque)
print(f"   calque créé, couleur = {nouveau_calque.couleur.name()}")

# --- Test 4 : on regarde ce que contient vraiment self.calques ---
print(f"\n4) Contenu de w.calques après création :")
for c in w.calques:
    print(f"   - {c.nom}  →  {c.couleur.name()}")

print("\n=== Fin du diagnostic ===")