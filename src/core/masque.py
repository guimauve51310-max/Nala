# =============================================================================
# src/core/masque.py
# -----------------------------------------------------------------------------
# Rôle : Modèle de données pour les MASQUES de travail.
#
# Un masque est une ÉTIQUETTE VISUELLE (couleur) qui regroupe des entités et
# porte des paramètres de découpe SAISIS PAR L'UTILISATEUR :
#
#   - P : Puissance (0 à 100 %)
#   - V : Vitesse (mm/min)
#   - N : Nombre de passes
#
# ⚠️ Les paramètres P/V/N ne sont PAS fixés par défaut : c'est l'utilisateur
#    qui les saisit, projet par projet. Ils dépendent du matériau, de
#    l'épaisseur, de la pièce, etc.
#
# ⚠️ PALETTE ULTRA-VIVE (fluo) :
#    Les couleurs sont volontairement SATURÉES et TRÈS DIFFÉRENTES entre elles.
#    Objectif : distinguer immédiatement les masques à l'écran, même :
#      - sur une pastille minuscule (12x12 px) dans la liste des masques
#      - sur un trait fin (1 px) dans la vue
#      - sur fond clair (blanc cassé)
#    Une seule teinte par famille : pas de rouge/bordeaux, vert/sarcelle, etc.
#
# Les masques sont ordonnés : leur position dans la liste détermine l'ordre
# de coupe (premier de la liste = premier coupé). Ordre de coupe = Étape 4.
#
# Ce fichier ne dépend d'AUCUN widget : c'est du pur modèle.
# =============================================================================

from PySide6.QtGui import QColor


# --- Palette ultra-vive de 8 couleurs ---------------------------------------
# Chaque entrée = (nom lisible, code hexadécimal).
# L'ordre détermine la présentation dans la boîte de dialogue de création.
PALETTE_MASQUES = [
    ("Noir",           "#000000"),   # import / valeur par défaut
    ("Rouge fluo",     "#ff0033"),   # rouge électrique
    ("Vert fluo",      "#00ff66"),   # vert néon
    ("Bleu électrique","#0066ff"),   # bleu intense
    ("Magenta",        "#ff00ff"),   # fuchsia pur
    ("Cyan",           "#00e5ff"),   # cyan néon
    ("Jaune fluo",     "#e6ff00"),   # jaune acide
    ("Orange fluo",    "#ff6600"),   # orange brûlé
]


class Masque:
    """
    Représente un masque de travail (une couleur + des paramètres de découpe).

    Attributs :
        nom       : nom du masque (ex: "Découpe extérieure")
        couleur   : QColor pour l'affichage
        puissance : P, de 0 à 100 (% de la puissance max de la machine)
        vitesse   : V, en mm/min
        passes    : N, nombre de passages (>= 1)

    ⚠️ P, V, N n'ont PAS de valeur par défaut "sensée" : elles sont mises à
       zéro/une valeur minimale, à charge de l'utilisateur de les saisir.
    """

    def __init__(self, nom, couleur="#000000",
                 puissance=0, vitesse=0, passes=1,
                 mode_rendu="line", espacement_fill=0.10,
                 angle_fill=0.0, sens_fill="aller_retour",
                 puissance_line=None, vitesse_line=None, passes_line=None,
                 puissance_fill=0, vitesse_fill=0, passes_fill=1,
                 inverser_fill=False, marge_fill_inverse=5.0):
        self.nom = nom
        self.couleur = QColor(couleur) if isinstance(couleur, str) else couleur

        # --- Visibilite temporaire (masquage/afficahge) ---
        # True par defaut. Non persistant dans le projet (remis a True
        # par vider_projet()).
        self.visible = True

        # --- Phase Rendu (R.3b) : 2 jeux de parametres P/V/N separes ---
        # Si les *_line sont passes explicitement, on les utilise.
        # Sinon, on reprend les anciens parametres puissance/vitesse/passes
        # (compatibilite avec le code existant qui ne connait que ces noms).
        if puissance_line is not None:
            self.puissance_line = puissance_line
        else:
            self.puissance_line = puissance
        if vitesse_line is not None:
            self.vitesse_line = vitesse_line
        else:
            self.vitesse_line = vitesse
        if passes_line is not None:
            self.passes_line = passes_line
        else:
            self.passes_line = passes

        self.puissance_fill = puissance_fill
        self.vitesse_fill = vitesse_fill
        self.passes_fill = passes_fill

        # --- Phase Rendu : parametres de mode ---
        self.mode_rendu = mode_rendu
        self.espacement_fill = espacement_fill
        self.angle_fill = angle_fill
        self.sens_fill = sens_fill

        # --- Fill inverse (gravure en negatif) ---
        # Si True, on grave TOUT SAUF l'interieur des entites (rectangle
        # englobant + entites traitees en even-odd).
        self.inverser_fill = inverser_fill
        self.marge_fill_inverse = marge_fill_inverse

    # --- Proprietes de compatibilite : puissance/vitesse/passes -> *_line ---
    @property
    def puissance(self):
        return self.puissance_line

    @puissance.setter
    def puissance(self, val):
        self.puissance_line = val

    @property
    def vitesse(self):
        return self.vitesse_line

    @vitesse.setter
    def vitesse(self, val):
        self.vitesse_line = val

    @property
    def passes(self):
        return self.passes_line

    @passes.setter
    def passes(self, val):
        self.passes_line = val

    # -------------------------------------------------------------------------
    # Utilitaires
    # -------------------------------------------------------------------------

    def couleur_hex(self):
        """Retourne la couleur au format '#rrggbb'."""
        return self.couleur.name()

    def __repr__(self):
        return (f"<Masque '{self.nom}' {self.couleur_hex()} "
                f"[LINE P={self.puissance_line}% V={self.vitesse_line}mm/min "
                f"N={self.passes_line}] "
                f"[FILL P={self.puissance_fill}% V={self.vitesse_fill}mm/min "
                f"N={self.passes_fill}] "
                f"mode={self.mode_rendu}>")


# --- Fonction utilitaire : prochaine couleur libre -------------------------

def couleur_suivante(index):
    """
    Retourne la couleur (au format hex) correspondant à l'index donné,
    en cyclant sur la palette si on dépasse les 8 couleurs disponibles.

    Retourne un tuple (nom_couleur, hex).
    """
    nom, hex_code = PALETTE_MASQUES[index % len(PALETTE_MASQUES)]
    return nom, hex_code