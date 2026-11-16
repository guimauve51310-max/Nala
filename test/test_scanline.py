# =============================================================================
# test_scanline.py
# -----------------------------------------------------------------------------
# Script de TEST VISUEL pour l'algorithme de scanline (src/core/scanline.py).
#
# Ouvre une fenêtre Qt qui affiche :
#   - Un contour (noir) : le carré ou la forme à tester
#   - Les segments de fill (rouge) : le résultat du scanline
#
# Usage : depuis C:\LaserCNC\LaserCNC\
#     env\Scripts\python.exe test_scanline.py
#
# Échap pour fermer.
# =============================================================================

import sys
import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from src.core.scanline import generer_scanline


# --- Forme à tester (carré 100x100) ------------------------------------------
FORME = [(50 + 50*math.cos(a), 50 + 50*math.sin(a)) for a in [2*math.pi*i/64 for i in range(64)]]

# --- Paramètres du scanline ---------------------------------------------------
ESPACEMENT_MM = 5.0
ANGLE_DEG = 45.0       # essaie 0, 45, 90 pour voir la différence
SENS = "aller_retour"


class TestWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test scanline")
        self.setMinimumSize(800, 800)

        # Calcul des segments de fill
        self.segments = generer_scanline(
            FORME,
            espacement_mm=ESPACEMENT_MM,
            angle_deg=ANGLE_DEG,
            sens=SENS,
        )
        print(f"Forme : {len(FORME)} points")
        print(f"Espacement : {ESPACEMENT_MM} mm")
        print(f"Angle : {ANGLE_DEG}°")
        print(f"Sens : {SENS}")
        print(f"Segments générés : {len(self.segments)}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fond blanc
        painter.fillRect(self.rect(), QColor("#ffffff"))

        # Échelle : la forme 100x100 doit occuper ~600 px
        marge = 80
        taille_cible = min(self.width(), self.height()) - 2 * marge
        echelle = taille_cible / 100.0  # forme = 100 mm

        # Point d'origine de la forme dans le widget (coin haut-gauche
        # avec marge)
        ox = marge
        oy = marge

        def to_screen(x, y):
            """Convertit un point (x,y) de la forme en pixel écran."""
            return QPointF(ox + x * echelle, oy + (100 - y) * echelle)

        # --- Dessin du contour (noir épais) ---
        pen_contour = QPen(QColor("#000000"))
        pen_contour.setWidthF(2.0)
        painter.setPen(pen_contour)
        painter.setBrush(QBrush(Qt.NoBrush))

        poly = QPolygonF([to_screen(x, y) for (x, y) in FORME])
        painter.drawPolygon(poly)

        # --- Dessin des segments de fill (rouge fin) ---
        pen_fill = QPen(QColor("#ff0033"))
        pen_fill.setWidthF(1.0)
        painter.setPen(pen_fill)

        for (x1, y1, x2, y2) in self.segments:
            painter.drawLine(to_screen(x1, y1), to_screen(x2, y2))


def main():
    app = QApplication(sys.argv)
    w = TestWidget()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()