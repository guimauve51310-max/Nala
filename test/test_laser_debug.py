# =============================================================================
# test_laser_debug.py
# -----------------------------------------------------------------------------
# Rôle : Diagnostiquer pourquoi LaserCNC.py se termine immédiatement et
#        sans message. On reproduit ce que fait LaserCNC.py mais avec des
#        print entre chaque étape, pour voir où ça coince.
# =============================================================================

print("1) Début du diagnostic")

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print("2) sys.path OK")

print("3) Import PySide6...")
from PySide6.QtWidgets import QApplication
print("   → OK")

print("4) Import LaserCNC (le module, sans l'exécuter)...")
import LaserCNC
print("   → OK")

print("5) Création de QApplication...")
app = QApplication(sys.argv)
print("   → OK")

print("6) Création de MainWindow()...")
try:
    window = LaserCNC.MainWindow()
    print("   → OK")
except Exception as e:
    print(f"   !! EXCEPTION dans MainWindow : {type(e).__name__} — {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("7) window.show()...")
window.show()
print("   → OK, fenêtre affichée")

print("8) Entrée dans app.exec()...")

# On met un timer pour fermer automatiquement au bout de 3 s
# (comme ça on est sûrs que la boucle événementielle démarre bien)
from PySide6.QtCore import QTimer
QTimer.singleShot(3000, app.quit)

resultat = app.exec()
print(f"9) app.exec() est retourné : {resultat}")
print("10) Fin du diagnostic.")