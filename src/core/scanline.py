# =============================================================================
# src/core/scanline.py
# -----------------------------------------------------------------------------
# Rôle : Algorithme de REMPLISSAGE PAR LIGNES DE BALAYAGE (scanline fill).
#
# À partir d'un contour fermé (liste de points), génère une série de segments
# parallèles qui remplissent l'intérieur de la forme. C'est ce qui permet de
# graver une surface pleine (Fill) au lieu d'un simple contour (Line).
#
# ⚠️ IMPORTANT : ce module NE DEPEND D'AUCUNE BIBLIOTHEQUE GRAPHIQUE (pas de
# Qt, pas de matplotlib). C'est du pur Python + math, pour être réutilisable
# par le générateur G-code.
#
# ⚠️ Version 1 : traite UNIQUEMENT les formes SANS TROUS (carré, cercle,
# polygone simple). La gestion des trous (lettres "o", "a"...) viendra plus
# tard (R.5).
#
# Algorithme :
#   1. Tourner le contour de -angle pour se ramener à un balayage horizontal
#   2. Générer les lignes horizontales espacées de `espacement_mm`
#   3. Pour chaque ligne, calculer les intersections avec le contour
#   4. Apparier les intersections 2 par 2 (règle even-odd)
#   5. Re-tourner les segments de +angle
# =============================================================================

import math


# -----------------------------------------------------------------------------
# Utilitaires de rotation
# -----------------------------------------------------------------------------

def _tourner_point(x, y, angle_rad):
    """Tourne un point autour de l'origine (0,0) d'un angle en radians."""
    ca = math.cos(angle_rad)
    sa = math.sin(angle_rad)
    return (x * ca - y * sa, x * sa + y * ca)


def _tourner_points(points, angle_rad):
    """Tourne une liste de points autour de l'origine."""
    return [_tourner_point(p[0], p[1], angle_rad) for p in points]


# -----------------------------------------------------------------------------
# Bounding box
# -----------------------------------------------------------------------------

def _bbox(points):
    """Retourne (x_min, y_min, x_max, y_max) d'une liste de points."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


# -----------------------------------------------------------------------------
# Intersections d'une ligne horizontale avec un contour
# -----------------------------------------------------------------------------

def _intersections_horizontales(y, points):
    """
    Retourne la liste triée des abscisses x où la ligne horizontale y
    intersecte le contour (liste de points, fermé implicitement).
    
    Règle : on ne compte pas les intersections aux sommets (ça évite
    les doublons). On utilise une comparaison stricte (>) pour le Y_min
    et (<=) pour le Y_max, comme dans l'algorithme standard de scanline.
    """
    intersections = []
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]  # boucle fermée

        if y1 == y2:
            # Segment horizontal : on ignore (traité par les autres segments)
            continue

        # On ordonne (y_min, y_max) pour la comparaison
        if y1 < y2:
            y_min, y_max = y1, y2
            x_min_y, x_max_y = x1, x2
        else:
            y_min, y_max = y2, y1
            x_min_y, x_max_y = x2, x1

        # Règle standard : on prend y_min <= y < y_max (inclut le bas,
        # exclut le haut) pour éviter de compter 2 fois aux sommets.
        if y_min <= y < y_max:
            # Interpolation linéaire pour trouver x à l'ordonnée y
            t = (y - y_min) / (y_max - y_min)
            x_intersect = x_min_y + t * (x_max_y - x_min_y)
            intersections.append(x_intersect)

    intersections.sort()
    return intersections


# -----------------------------------------------------------------------------
# Fonction principale
# -----------------------------------------------------------------------------

def generer_scanline(contours, espacement_mm, angle_deg=0.0,
                     sens="aller_retour"):
    """
    Génère les segments de remplissage (scanline).

    Accepte DEUX formats :
      - Un SEUL contour : liste de tuples (x, y), ex. [(x1,y1), (x2,y2), ...]
      - PLUSIEURS contours : liste de listes de tuples, ex. [[(x1,y1),...], [(x2,y2),...]]
        -> Les contours supplémentaires sont traités comme des TROUS
           (règle even-odd).

    Arguments :
        contours       : un contour OU une liste de contours
        espacement_mm  : distance entre les lignes de balayage (en mm)
        angle_deg      : angle des lignes de balayage en degrés
        sens           : "aller" ou "aller_retour"

    Retourne :
        Liste de segments [(x1, y1, x2, y2), ...] en coordonnées ORIGINALES.
    """
    if not contours:
        return []

    # --- Normalisation : on transforme toujours en liste de contours ---
    # Si contours est une liste de tuples -> c'est UN SEUL contour
    # Si contours est une liste de listes -> c'est PLUSIEURS contours
    if isinstance(contours[0], (tuple, list)) and len(contours[0]) == 2 \
            and isinstance(contours[0][0], (int, float)):
        # contours = [(x1,y1), (x2,y2), ...] -> un seul contour
        liste_contours = [contours]
    else:
        # contours = [[(x1,y1),...], [(x2,y2),...]] -> plusieurs contours
        liste_contours = list(contours)

    # Filtrer les contours trop petits
    liste_contours = [c for c in liste_contours if c and len(c) >= 3]
    if not liste_contours:
        return []

    if espacement_mm <= 0:
        return []

    # --- 1. Fermer chaque contour si nécessaire ---
    contours_fermes = []
    for c in liste_contours:
        pts = list(c)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        pts = pts[:-1]  # enlève le doublon
        contours_fermes.append(pts)

    # --- 2. Rotation : -angle pour ramener à un balayage horizontal ---
    angle_rad = math.radians(angle_deg)
    contours_tournes = [_tourner_points(pts, -angle_rad)
                        for pts in contours_fermes]

    # --- 3. Bounding box GLOBALE (sur tous les contours) ---
    xs_tous = []
    ys_tous = []
    for pts in contours_tournes:
        for (x, y) in pts:
            xs_tous.append(x)
            ys_tous.append(y)
    if not xs_tous:
        return []
    x_min_t = min(xs_tous)
    x_max_t = max(xs_tous)
    y_min_t = min(ys_tous)
    y_max_t = max(ys_tous)

    # --- 4. Génération des lignes horizontales ---
    nb_lignes = int(math.floor((y_max_t - y_min_t) / espacement_mm)) + 1

    segments_tournes = []

    for i in range(nb_lignes):
        y_ligne = y_min_t + (i + 0.5) * espacement_mm
        if y_ligne >= y_max_t:
            break

        # Intersections avec TOUS les contours
        xs = []
        for pts in contours_tournes:
            xs.extend(_intersections_horizontales(y_ligne, pts))
        xs.sort()

        if len(xs) < 2:
            continue

        # Appariement 2 par 2 (even-odd rule) :
        # - Si 2 intersections -> 1 segment (cas normal)
        # - Si 4 intersections -> 2 segments (contour + trou)
        # - Si 6 -> 3 segments, etc.
        for j in range(0, len(xs) - 1, 2):
            x_start = xs[j]
            x_end = xs[j + 1]

            if x_end <= x_start:
                continue

            if sens == "aller_retour" and (i % 2 == 1):
                segments_tournes.append((x_end, y_ligne, x_start, y_ligne))
            else:
                segments_tournes.append((x_start, y_ligne, x_end, y_ligne))

    # --- 5. Rotation inverse : +angle pour ramener aux coordonnées originales ---
    segments = []
    for (x1, y1, x2, y2) in segments_tournes:
        # Rotation de chaque extrémité
        x1r, y1r = _tourner_point(x1, y1, angle_rad)
        x2r, y2r = _tourner_point(x2, y2, angle_rad)
        segments.append((x1r, y1r, x2r, y2r))

    return segments


# -----------------------------------------------------------------------------
# Test rapide si lancé directement
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Carré de 100x100
    carre = [(0, 0), (100, 0), (100, 100), (0, 100)]
    segs = generer_scanline(carre, espacement_mm=10.0, angle_deg=0.0)
    print(f"Carré 100x100, espacement 10 mm -> {len(segs)} segments")
    for s in segs[:5]:
        print(f"  {s}")
    print("  ...")