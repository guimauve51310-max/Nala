# =============================================================================
# src/core/estimateur_temps.py
# -----------------------------------------------------------------------------
# Role : Estimer le temps d'execution d'un fichier G-code.
#
# Principe :
#   - On parcourt le G-code ligne par ligne
#   - Pour chaque mouvement (G0 ou G1), on calcule la distance parcourue
#   - On divise par la vitesse pour obtenir le temps
#   - G0 (rapide) -> vitesse VITESSE_G0 (par defaut 3000 mm/min)
#   - G1 (marche) -> vitesse F si presente, sinon F par defaut
#   - On additionne le tout, plus une marge de securite (+15 %)
#
# TODO (plus tard) : remplacer VITESSE_G0 par une preference utilisateur
#                    (actuellement c'est une constante).
# =============================================================================

import math
import re


# --- Constantes --------------------------------------------------------------
# Vitesse par defaut pour les deplacements G0 (rapide) en mm/min.
# Utilisee si on n'a pas l'info de la carte. A remplacer par une preference.
VITESSE_G0_DEFAUT = 3000.0

# Vitesse par defaut pour les G1 sans F (rare, ne devrait pas arriver)
VITESSE_G1_DEFAUT = 500.0

# Marge de securite (%) appliquee au temps total.
# Compense les accelerations, decelerations, micro-arrets, etc.
MARGE_POURCENT = 15


def _parse_coordonnees(mots):
    """
    Extrait X et Y d'une liste de mots G-code.
    Retourne (x, y) ou (None, None) si absents.
    """
    x = None
    y = None
    for mot in mots:
        if mot.startswith("X"):
            try:
                x = float(mot[1:])
            except ValueError:
                pass
        elif mot.startswith("Y"):
            try:
                y = float(mot[1:])
            except ValueError:
                pass
    return x, y


def _parse_f(mots):
    """Extrait la vitesse F si presente, sinon None."""
    for mot in mots:
        if mot.startswith("F"):
            try:
                return float(mot[1:])
            except ValueError:
                pass
    return None


def estimer_temps_gcode(lignes, vitesse_g0=VITESSE_G0_DEFAUT):
    """
    Estime le temps total d'execution d'un G-code.

    Arguments :
        lignes     : liste de lignes de G-code (str)
        vitesse_g0 : vitesse des G0 en mm/min

    Retourne : temps en secondes (float)
    """
    # Position actuelle (mm) - on suppose qu'on part de (0,0) par defaut
    pos_x = 0.0
    pos_y = 0.0

    # Mode de deplacement courant : None, "G0" ou "G1"
    mode = None
    # Vitesse F courante (heritee d'une ligne a l'autre)
    vitesse_courante = VITESSE_G1_DEFAUT

    temps_total = 0.0

    for ligne_brute in lignes:
        ligne = ligne_brute.strip()

        # Ignore les lignes vides et les commentaires
        if not ligne or ligne.startswith(";") or ligne.startswith("("):
            continue

        # Retire les commentaires en fin de ligne
        if ";" in ligne:
            ligne = ligne.split(";")[0].strip()
        if "(" in ligne:
            ligne = ligne.split("(")[0].strip()
        if not ligne:
            continue

        mots = ligne.upper().split()

        # --- Mise a jour du mode ---
        for mot in mots:
            if mot in ("G0", "G00"):
                mode = "G0"
            elif mot in ("G1", "G01"):
                mode = "G1"

        # --- Mise a jour de la vitesse F ---
        f = _parse_f(mots)
        if f is not None:
            vitesse_courante = f

        # --- Coordonnees ---
        x, y = _parse_coordonnees(mots)

        # --- Calcul du temps si deplacement ---
        if mode is not None and (x is not None or y is not None):
            cible_x = x if x is not None else pos_x
            cible_y = y if y is not None else pos_y

            dx = cible_x - pos_x
            dy = cible_y - pos_y
            distance = math.hypot(dx, dy)

            if mode == "G0":
                v = vitesse_g0
            else:
                v = vitesse_courante if vitesse_courante > 0 else VITESSE_G1_DEFAUT

            if v > 0 and distance > 0:
                temps_total += (distance / v) * 60.0  # minutes -> secondes

            pos_x = cible_x
            pos_y = cible_y

    # Marge de securite
    temps_total *= (1 + MARGE_POURCENT / 100.0)

    return temps_total


def formater_temps(secondes):
    """
    Formate un temps en secondes sous une forme lisible.
    - < 60 s       : "42 s"
    - < 1 h        : "5 min 32 s"
    - >= 1 h       : "1 h 23 min"
    """
    secondes = max(0, int(round(secondes)))

    if secondes < 60:
        return f"{secondes} s"

    minutes = secondes // 60
    secondes_restantes = secondes % 60

    if minutes < 60:
        return f"{minutes} min {secondes_restantes} s"

    heures = minutes // 60
    minutes_restantes = minutes % 60
    return f"{heures} h {minutes_restantes:02d} min"
