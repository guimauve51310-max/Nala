# =============================================================================
# src/ui/regles.py
# -----------------------------------------------------------------------------
# Rôle : Widgets de RÈGLES GRADUÉES (horizontale et verticale) pour la vue
#        de mise en page.
#
# ⚠️ ARCHITECTURE :
#   Ces règles sont des WIDGETS SÉPARÉS de la vue (QGraphicsView). Ils sont
#   placés autour de la vue via un QGridLayout dans MiseEnPageWidget :
#
#       ┌──────────┬─────────────────────┐
#       │  (coin)  │  Règle horizontale  │
#       ├──────────┼─────────────────────┤
#       │  Règle   │                     │
#       │ verticale│   Vue graphique     │
#       │          │                     │
#       └──────────┴─────────────────────┘
#
#   Avantage : chaque widget a sa propre zone de dessin, Qt gère les repaints
#   proprement, aucun artefact possible (contrairement à drawForeground).
#
# ⚠️ SYNCHRONISATION :
#   Les règles sont mises à jour par MiseEnPageWidget qui leur passe :
#     - les paramètres d'affichage (origine, sens des axes, pas de graduation)
#     - une fonction de conversion scène → coordonnée machine
#     - la zone visible de la scène (viewport)
# =============================================================================

import math

from PySide6.QtCore import Qt, QRectF, QPointF, QLineF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget


# --- Dimensions des règles ---------------------------------------------------
TAILLE_REGLE_H = 22       # épaisseur de la règle horizontale (hauteur en px)
TAILLE_REGLE_V = 55       # largeur de la règle verticale (px)

# --- Couleurs ----------------------------------------------------------------
COULEUR_FOND  = QColor("#fafafa")
COULEUR_TXT   = QColor("#333333")
COULEUR_TICK  = QColor("#666666")

# --- Espacement minimum en pixels entre deux chiffres ------------------------
ESPACEMENT_MIN_PX = 60

# --- Pas "jolis" à essayer dans l'ordre --------------------------------------
PAS_CANDIDATS = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0,
                 100.0, 200.0, 500.0, 1000.0]


def calculer_pas(pixels_par_mm):
    """
    Calcule le pas de graduation idéal pour au moins ESPACEMENT_MIN_PX pixels
    entre deux chiffres.
    """
    for pas in PAS_CANDIDATS:
        if pas * pixels_par_mm >= ESPACEMENT_MIN_PX:
            return pas
    return PAS_CANDIDATS[-1]


class RegleHorizontale(QWidget):
    """
    Règle horizontale (en haut de la vue) affichant les coordonnées X MACHINE.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TAILLE_REGLE_H)
        self.setMinimumWidth(50)

        # État à synchroniser (mis à jour par MiseEnPageWidget)
        self.pixels_par_mm = 1.0
        self.scene_x_min = 0.0      # x_scene à gauche de la vue
        self.scene_x_max = 100.0    # x_scene à droite de la vue
        self.offset_px = 0          # décalage en pixels (position de la vue
                                    # par rapport au widget règle — utile si
                                    # la règle n'a pas exactement la largeur
                                    # du viewport)
        self.sens_ex = 1            # +1 si X+ vers la droite, -1 sinon
        self.font = QFont()
        self.font.setPointSize(7)

    def maj_etat(self, pixels_par_mm, scene_x_min, scene_x_max,
                 offset_px, sens_ex):
        """Appelé par MiseEnPageWidget pour synchroniser l'affichage."""
        self.pixels_par_mm = pixels_par_mm
        self.scene_x_min = scene_x_min
        self.scene_x_max = scene_x_max
        self.offset_px = offset_px
        self.sens_ex = sens_ex
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()

        # Fond
        painter.fillRect(0, 0, w, h, COULEUR_FOND)

        if self.pixels_par_mm <= 0:
            return

        pas = calculer_pas(self.pixels_par_mm)

        pen_tick = QPen(COULEUR_TICK)
        pen_tick.setWidthF(1.0)
        painter.setFont(self.font)

        # On parcourt les pas de la scène dans la plage visible
        x_debut = math.floor(self.scene_x_min / pas) * pas
        x_scene = x_debut
        while x_scene <= self.scene_x_max:
            # Position à l'écran (en pixels dans le widget règle)
            x_px = (x_scene - self.scene_x_min) * self.pixels_par_mm + self.offset_px

            # Coordonnée machine
            x_machine = x_scene * self.sens_ex

            # Tick
            painter.setPen(pen_tick)
            painter.drawLine(QLineF(x_px, h - 4, x_px, h))

            # Texte
            if pas >= 1:
                texte = f"{int(round(x_machine))}"
            else:
                texte = f"{x_machine:.1f}"
            painter.setPen(QPen(COULEUR_TXT))
            painter.drawText(QPointF(x_px + 2, h - 8), texte)

            x_scene += pas

        # Ligne de séparation en bas
        painter.setPen(QPen(COULEUR_TICK))
        painter.drawLine(0, h - 1, w, h - 1)


class RegleVerticale(QWidget):
    """
    Règle verticale (à gauche de la vue) affichant les coordonnées Y MACHINE.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(TAILLE_REGLE_V)
        self.setMinimumHeight(50)

        self.pixels_par_mm = 1.0
        self.scene_y_min = 0.0
        self.scene_y_max = 100.0
        self.offset_px = 0
        self.sens_ey = 1

        self.font = QFont()
        self.font.setPointSize(7)

    def maj_etat(self, pixels_par_mm, scene_y_min, scene_y_max,
                 offset_px, sens_ey):
        self.pixels_par_mm = pixels_par_mm
        self.scene_y_min = scene_y_min
        self.scene_y_max = scene_y_max
        self.offset_px = offset_px
        self.sens_ey = sens_ey
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()

        painter.fillRect(0, 0, w, h, COULEUR_FOND)

        if self.pixels_par_mm <= 0:
            return

        pas = calculer_pas(self.pixels_par_mm)

        pen_tick = QPen(COULEUR_TICK)
        pen_tick.setWidthF(1.0)
        painter.setFont(self.font)

        y_debut = math.floor(self.scene_y_min / pas) * pas
        y_scene = y_debut
        while y_scene <= self.scene_y_max:
            y_px = (y_scene - self.scene_y_min) * self.pixels_par_mm + self.offset_px

            y_machine = y_scene * self.sens_ey

            # Tick (à droite du widget)
            painter.setPen(pen_tick)
            painter.drawLine(QLineF(w - 4, y_px, w, y_px))

            # Texte aligné à droite
            if pas >= 1:
                texte = f"{int(round(y_machine))}"
            else:
                texte = f"{y_machine:.1f}"
            painter.setPen(QPen(COULEUR_TXT))
            rect_txt = QRectF(0, y_px - 7, w - 6, 14)
            painter.drawText(rect_txt, Qt.AlignRight | Qt.AlignVCenter, texte)

            y_scene += pas

        # Ligne de séparation à droite
        painter.setPen(QPen(COULEUR_TICK))
        painter.drawLine(w - 1, 0, w - 1, h)


class CoinRegles(QWidget):
    """
    Petit widget carré dans le coin supérieur gauche (intersection des deux
    règles). Dessine juste un fond pour éviter un trou visuel.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(TAILLE_REGLE_V, TAILLE_REGLE_H)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), COULEUR_FOND)
        painter.setPen(QPen(COULEUR_TICK))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())