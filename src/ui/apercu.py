# =============================================================================
# src/ui/apercu.py
# -----------------------------------------------------------------------------
# Rôle : Widget d'aperçu 2D du G-code avec suivi temps réel de l'outil.
#
# Ce widget affiche :
#   - le parcours du G-code chargé
#       • G0 (déplacements rapides) en gris pointillé
#       • G1 (déplacements de travail) en bleu plein
#   - un marqueur rouge représentant la position actuelle de l'outil
#
# Navigation :
#   - Molette              : zoom avant / arrière, CENTRÉ SOUS LE CURSEUR
#   - Clic-glisser gauche  : déplacer la vue (pan) à tous les niveaux de zoom
#   - Bouton "Recentrer"   : recadre la vue sur l'ensemble du parcours
#
# ⚠️ Deux points importants sur la navigation :
#
#   1) La sceneRect est volontairement PLUS GRANDE que le parcours (3×).
#      Sans ça, fitInView ajusterait la scène pile à la vue, les scrollbars
#      n'auraient plus de range, et le pan ne marcherait pas.
#
#   2) Le zoom n'utilise PAS AnchorUnderMouse (que fitInView casse). À la
#      place, on calcule manuellement le point sous la souris avant/après
#      zoom, et on décale la vue pour que ce point reste fixe.
#
# Le widget NE touche PAS à la communication série. L'interface lui pousse
# les données via :
#   - charger_parcours(liste_de_lignes_gcode)
#   - maj_position(x, y)
#
# TODO (plus tard) : gérer G20 (pouces) en plus de G21 (mm).
# =============================================================================

from PySide6.QtCore import Qt, QRectF, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsPathItem, QGraphicsEllipseItem, QPushButton, QLabel
)


# --- Couleurs et styles (regroupés pour modification facile plus tard) --------
COULEUR_FOND       = QColor("#1e1e1e")
COULEUR_G0         = QColor("#7f8c8d")
COULEUR_G1         = QColor("#3498db")
COULEUR_MARQUEUR   = QColor("#e74c3c")
COULEUR_AXE        = QColor("#666666")
TAILLE_MARQUEUR_PX = 10
MARGE_VUE          = 0.10          # 10 % de marge autour du parcours

# Facteur d'élargissement de la sceneRect (pour permettre le pan/zoom out).
# 3 = on peut se déplacer jusqu'à 3× la taille du parcours dans chaque sens.
FACTEUR_ELARGISSEMENT_SCENE = 3.0

# Facteur de zoom par cran de molette
FACTEUR_ZOOM = 1.15


class VueApercu(QGraphicsView):
    """
    QGraphicsView avec zoom sous le curseur et pan au clic-glisser.

    Le pan utilise les scrollbars (qui ont un range grâce à la sceneRect
    élargie) et le zoom est calculé manuellement pour rester centré sur
    le curseur.
    """

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        # On n'utilise pas les ancres automatiques de Qt : on gère nous-mêmes.
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setCursor(Qt.OpenHandCursor)

        self._pan_actif = False
        self._dernier_point = QPoint()

    # -------------------------------------------------------------------------
    # Zoom sous le curseur
    # -------------------------------------------------------------------------

    def wheelEvent(self, event):
        """
        Zoom centré sur le curseur :
          1) On note le point scène sous la souris AVANT zoom
          2) On applique le zoom
          3) On note le point scène sous la souris APRÈS zoom
          4) On décale la vue pour que ces deux points coïncident
        """
        point_vue = event.position().toPoint()
        point_scene_avant = self.mapToScene(point_vue)

        facteur = FACTEUR_ZOOM if event.angleDelta().y() > 0 else 1 / FACTEUR_ZOOM
        self.scale(facteur, facteur)

        point_scene_apres = self.mapToScene(point_vue)

        # Décalage nécessaire en coordonnées scène
        delta = point_scene_apres - point_scene_avant

        # centerOn décale la vue : le centre actuel décalé du delta
        centre_actuel = self.mapToScene(self.viewport().rect().center())
        self.centerOn(centre_actuel - delta)

        event.accept()

    # -------------------------------------------------------------------------
    # Pan au clic-glisser
    # -------------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pan_actif = True
            self._dernier_point = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_actif:
            point_actuel = event.position().toPoint()
            delta = point_actuel - self._dernier_point
            self._dernier_point = point_actuel

            # Décalage via les scrollbars (qui ont un range grâce à la
            # sceneRect élargie). Signe inversé : la vue suit la souris.
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pan_actif:
            self._pan_actif = False
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class ApercuWidget(QWidget):
    """Widget d'aperçu 2D avec suivi temps réel."""

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Vue graphique
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(COULEUR_FOND))
        self.view = VueApercu(self.scene)
        layout.addWidget(self.view)

        # Barre du bas : position + bouton recentrer
        barre = QHBoxLayout()

        self.label_position = QLabel("Position : X ---.---   Y ---.---")
        self.label_position.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 14px; padding: 4px 12px;"
        )
        barre.addWidget(self.label_position)

        barre.addStretch()

        self.btn_recentrer = QPushButton("Recentrer la vue")
        self.btn_recentrer.clicked.connect(self.recentrer_vue)
        barre.addWidget(self.btn_recentrer)

        layout.addLayout(barre)

        # --- Items graphiques ---
        self.item_g0 = QGraphicsPathItem()
        pen_g0 = QPen(COULEUR_G0)
        pen_g0.setStyle(Qt.DashLine)
        pen_g0.setWidthF(0)
        pen_g0.setCosmetic(True)
        self.item_g0.setPen(pen_g0)
        self.scene.addItem(self.item_g0)

        self.item_g1 = QGraphicsPathItem()
        pen_g1 = QPen(COULEUR_G1)
        pen_g1.setWidthF(0)
        pen_g1.setCosmetic(True)
        self.item_g1.setPen(pen_g1)
        self.scene.addItem(self.item_g1)

        self.item_axes = QGraphicsPathItem()
        pen_axe = QPen(COULEUR_AXE)
        pen_axe.setWidthF(0)
        pen_axe.setCosmetic(True)
        self.item_axes.setPen(pen_axe)
        self.scene.addItem(self.item_axes)

        self.item_marqueur = QGraphicsEllipseItem()
        demi = TAILLE_MARQUEUR_PX / 2
        self.item_marqueur.setRect(-demi, -demi, TAILLE_MARQUEUR_PX, TAILLE_MARQUEUR_PX)
        self.item_marqueur.setBrush(QBrush(COULEUR_MARQUEUR))
        self.item_marqueur.setPen(QPen(Qt.NoPen))
        self.item_marqueur.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations, True)
        self.item_marqueur.setVisible(False)
        self.scene.addItem(self.item_marqueur)

        self.zone_parcours = QRectF()

        self.pos_x = 0.0
        self.pos_y = 0.0

        # Premiere coordonnee du parcours (pour le suivi decale)
        self.premiere_coord = (0.0, 0.0)

        self._dessiner_axes(20.0)
        self._appliquer_zone(Qt.KeepAspectRatio)
        self.recentrer_vue()

    # -------------------------------------------------------------------------
    # API publique
    # -------------------------------------------------------------------------

    def charger_parcours(self, lignes_gcode):
        """Analyse le G-code, dessine le parcours, recadre la vue."""
        path_g0 = QPainterPath()
        path_g1 = QPainterPath()

        pos_x, pos_y = 0.0, 0.0
        mode_absolu = True
        type_precedent = None
        premiere_coord_stockee = None

        for ligne_brute in lignes_gcode:
            ligne = ligne_brute.strip()

            if "(" in ligne:
                ligne = ligne.split("(")[0].strip()
            if ";" in ligne:
                ligne = ligne.split(";")[0].strip()

            if not ligne:
                continue

            mots = ligne.split()
            g_codes = []
            x_cible = None
            y_cible = None

            for mot in mots:
                mot_upper = mot.upper()
                if mot_upper in ("G0", "G00"):
                    g_codes.append("G0")
                elif mot_upper in ("G1", "G01"):
                    g_codes.append("G1")
                elif mot_upper == "G21":
                    pass
                elif mot_upper == "G20":
                    pass    # TODO plus tard
                elif mot_upper == "G90":
                    mode_absolu = True
                elif mot_upper == "G91":
                    mode_absolu = False
                elif mot_upper.startswith("X"):
                    try:
                        x_cible = float(mot[1:])
                    except ValueError:
                        pass
                elif mot_upper.startswith("Y"):
                    try:
                        y_cible = float(mot[1:])
                    except ValueError:
                        pass

            if "G0" in g_codes or "G1" in g_codes:
                if x_cible is not None:
                    cible_x = x_cible if mode_absolu else pos_x + x_cible
                else:
                    cible_x = pos_x

                if y_cible is not None:
                    cible_y = y_cible if mode_absolu else pos_y + y_cible
                else:
                    cible_y = pos_y

                if "G0" in g_codes:
                    type_ligne = "G0"
                elif "G1" in g_codes:
                    type_ligne = "G1"
                else:
                    type_ligne = type_precedent or "G0"

                path = path_g0 if type_ligne == "G0" else path_g1

                if type_precedent != type_ligne:
                    path.moveTo(cible_x, cible_y)
                else:
                    path.lineTo(cible_x, cible_y)

                type_precedent = type_ligne
                pos_x, pos_y = cible_x, cible_y

                # Memoriser la toute premiere coordonnee vue
                if premiere_coord_stockee is None:
                    premiere_coord_stockee = (cible_x, cible_y)

        # Stocker la 1ere coordonnee du parcours (0,0 si aucune)
        if premiere_coord_stockee is not None:
            self.premiere_coord = premiere_coord_stockee
        else:
            self.premiere_coord = (0.0, 0.0)

        self.item_g0.setPath(path_g0)
        self.item_g1.setPath(path_g1)

        rect_g0 = path_g0.boundingRect()
        rect_g1 = path_g1.boundingRect()
        self.zone_parcours = rect_g0.united(rect_g1)

        if self.zone_parcours.isNull() or self.zone_parcours.isEmpty():
            self.zone_parcours = QRectF(0, 0, 100, 100)
        else:
            marge_x = max(self.zone_parcours.width(), 1.0) * MARGE_VUE
            marge_y = max(self.zone_parcours.height(), 1.0) * MARGE_VUE
            self.zone_parcours.adjust(-marge_x, -marge_y, marge_x, marge_y)

        self._appliquer_zone(Qt.KeepAspectRatio)
        self.recentrer_vue()

    def get_premiere_coordonnee(self):
        """Retourne la 1ere coordonnee (x, y) du parcours charge."""
        return self.premiere_coord

    def maj_position(self, x, y):
        """
        Met a jour la position du marqueur (mise a jour DIRECTE).

        Appelee par LaserCNC.py a chaque rapport de statut recu
        (WPos: extrait de la ligne <...>).
        """
        self.pos_x = x
        self.pos_y = y
        self.item_marqueur.setPos(x, y)
        self.item_marqueur.setVisible(True)
        self.label_position.setText(f"Position : X {x:8.3f}   Y {y:8.3f}")

    def recentrer_vue(self):

        """Recadre la vue sur le parcours (ou la zone par défaut)."""
        if self.zone_parcours.isNull() or self.zone_parcours.isEmpty():
            self.view.fitInView(QRectF(-20, -20, 140, 140), Qt.KeepAspectRatio)
        else:
            self.view.fitInView(self.zone_parcours, Qt.KeepAspectRatio)

    def vider(self):
        """Efface le parcours et cache le marqueur."""
        self.item_g0.setPath(QPainterPath())
        self.item_g1.setPath(QPainterPath())
        self.item_marqueur.setVisible(False)
        self.label_position.setText("Position : X ---.---   Y ---.---")
        self.zone_parcours = QRectF()
        self._appliquer_zone(Qt.KeepAspectRatio)
        self.recentrer_vue()

    # -------------------------------------------------------------------------
    # Interne
    # -------------------------------------------------------------------------

    def _appliquer_zone(self, aspect_ratio_mode):
        """
        Définit la sceneRect = zone du parcours ÉLARGIE d'un facteur
        (FACTEUR_ELARGISSEMENT_SCENE). Cette scène plus grande que le
        parcours est indispensable pour que les scrollbars aient un range
        et que le pan / zoom out fonctionnent.
        """
        if self.zone_parcours.isNull() or self.zone_parcours.isEmpty():
            # Zone par défaut
            zone = QRectF(-20, -20, 140, 140)
        else:
            zone = self.zone_parcours

        centre = zone.center()
        nouvelle_largeur = max(zone.width(), 1.0) * FACTEUR_ELARGISSEMENT_SCENE
        nouvelle_hauteur = max(zone.height(), 1.0) * FACTEUR_ELARGISSEMENT_SCENE

        scene_rect = QRectF(
            centre.x() - nouvelle_largeur / 2,
            centre.y() - nouvelle_hauteur / 2,
            nouvelle_largeur,
            nouvelle_hauteur
        )
        self.scene.setSceneRect(scene_rect)

    def _dessiner_axes(self, longueur):
        """Dessine deux petits traits depuis l'origine pour situer X et Y."""
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(longueur, 0)
        path.moveTo(0, 0)
        path.lineTo(0, longueur)
        self.item_axes.setPath(path)