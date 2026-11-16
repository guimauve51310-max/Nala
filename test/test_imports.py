# =============================================================================
# test_imports.py
# -----------------------------------------------------------------------------
# Rôle : Diagnostiquer précisément où l'application échoue à démarrer.
#        On importe chaque brique une par une, en affichant à chaque étape.
#
# Si le script s'arrête au milieu, la DERNIÈRE ligne affichée indique
# exactement quel import ou quelle création d'objet pose problème.
# =============================================================================

print("1) Début du script")

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print("2) sys.path configuré")

# --- Test des imports un par un ---

print("3) Import PySide6.QtWidgets...")
from PySide6.QtWidgets import QApplication, QMainWindow
print("   → OK")

print("4) Import PySide6.QtCore...")
from PySide6.QtCore import QTimer
print("   → OK")

print("5) Import GrblController...")
from src.grbl.controller import GrblController
print("   → OK")

print("6) Import EnvoiGcodeThread...")
from src.grbl.envoi_thread import EnvoiGcodeThread
print("   → OK")

print("7) Import ApercuWidget...")
from src.ui.apercu import ApercuWidget
print("   → OK")

print("8) Import MiseEnPageWidget...")
from src.ui.mise_en_page import MiseEnPageWidget
print("   → OK")

print("9) Import ezdxf...")
import ezdxf
print("   → OK")

# --- Création d'une QApplication minimale ---

print("10) Création de QApplication...")
app = QApplication(sys.argv)
print("    → OK")

print("11) Création d'un ApercuWidget...")
w1 = ApercuWidget()
print("    → OK")

print("12) Création d'un MiseEnPageWidget...")
w2 = MiseEnPageWidget()
print("    → OK")

print("13) Création d'une fenêtre Qt minimale...")
win = QMainWindow()
win.setWindowTitle("Test imports")
win.resize(400, 200)
win.show()
print("    → OK, fenêtre affichée")

print("\nSi tu vois ce message ET une fenêtre, appuie sur Alt+F4 pour fermer.\n")

sys.exit(app.exec())