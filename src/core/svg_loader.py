# =============================================================================
# src/core/svg_loader.py
# -----------------------------------------------------------------------------
# Rôle : Lire un fichier SVG et le convertir en une liste d'ENTITÉS SIMPLES,
#        exploitables par le reste du programme (mêmes Entite que le DXF).
#
# ⚠️ COHÉRENCE AVEC LE DXF :
#   - Même signature : charger_svg(chemin, activer_fusion=False,
#                                  activer_lissage=True, tolerance_lissage=...)
#   - Même retour : (entites, warnings)
#   - Lissage Douglas-Peucker via simplifier_polyligne (même que DXF)
#
# ⚠️ FUSION DES SEGMENTS PAR DÉFAUT : DÉSACTIVÉE (False)
#   Raison : fusionner_segments() est calibré pour des micro-segments DXF.
#   Sur un SVG vectorisé complexe (ex. cheval Inkscape, 24819 pts répartis
#   sur 882 sous-chemins), il regroupe tout en UNE SEULE entité, ce qui
#   produit des segments aberrants qui traversent le dessin.
#   La fusion reste activable : charger_svg(..., activer_fusion=True)
#
# ⚠️ ÉCLATEMENT DES PATH EN SOUS-CHEMINS :
#   Inkscape (entre autres) met souvent TOUS les traits d'un dessin dans
#   UN SEUL <path> avec des centaines de sous-chemins (M...Z).
#   On utilise Path.as_subpaths() pour éclater chaque sous-chemin en une
#   entité indépendante. Sans ça, as_points() relierait la fin d'un trait
#   au début du suivant par des lignes aberrantes.
#
# ⚠️ CONVERSION DES UNITÉS :
#   svgelements renvoie les coordonnées en pixels CSS (1 px = 1/96 pouce).
#   On DIVISE par PX_VERS_MM pour obtenir des millimètres (cohérent avec
#   le reste du projet : DXF en mm, machine en mm).
#
# ⚠️ REPÈRE :
#   - SVG : origine en haut à gauche, Y vers le bas (comme le "fond-gauche").
#   - On garde donc les coordonnées telles quelles, sans inversion Y.
#
# DÉPENDANCE : svgelements (pip install svgelements)
#
# Ce module N'AFFICHE RIEN et NE PARLE PAS À LA MACHINE.
# =============================================================================

import math

from src.core.dxf_loader import (
    Entite,
    simplifier_polyligne,
    TOLERANCE_LISSAGE_DEFAUT,
)
from src.core.fusion_segments import fusionner_segments


# --- Constantes --------------------------------------------------------------
# Nombre de points pour échantillonner cercles et ellipses.
NPATH_POINTS_DEFAUT = 64

# Conversion px CSS -> mm (1 px = 1/96 pouce, 1 pouce = 25.4 mm).
PX_VERS_MM = 25.4 / 96.0     # ≈ 0.264583333...


# =============================================================================
# Extraction des sous-chemins depuis un SVG
# =============================================================================

def _extraire_points_svg(chemin):
    """
    Charge un SVG via svgelements et retourne une liste de tuples :
        (points, calque, couleur_rgb, type_origine)

    - points    : liste de tuples (x, y) en MILLIMÈTRES
    - calque    : nom du groupe SVG (g) ou "0"
    - couleur   : tuple (r, g, b) ou None
    - type_origine : string ("PATH", "CIRCLE", "RECT", ...)
    """
    import svgelements

    resultats = []

    try:
        svg = svgelements.SVG.parse(chemin)
    except Exception as e:
        raise RuntimeError(f"Erreur de lecture SVG : {e}")

    # Parcours récursif : le SVG racine est un conteneur (comme un Group).
    _parcourir_element(svg, resultats, calque_courant="0",
                       couleur_courante=None)

    return resultats


def _parcourir_element(element, resultats, calque_courant, couleur_courante):
    """
    Parcours récursif d'un élément SVG (SVG racine, groupe ou forme).

    - Si c'est un conteneur (SVG, Group) : on descend dedans.
    - Si c'est une forme : on l'aplatit (1 ou plusieurs polylignes) et
      on ajoute chaque polyligne comme entrée indépendante.
    - Sinon (texte, image...) : on ignore.
    """
    import svgelements

    # --- Conteneurs : on descend, en héritant du nom et de la couleur ---
    if isinstance(element, (svgelements.SVG, svgelements.Group)):
        nom = _nom_groupe(element) if isinstance(element, svgelements.Group) \
              else None
        nouveau_calque = nom if nom else calque_courant
        nouvelle_couleur = _extraire_couleur(element) or couleur_courante

        try:
            for enfant in element:
                _parcourir_element(enfant, resultats, nouveau_calque,
                                   nouvelle_couleur)
        except TypeError:
            pass
        return

    # --- Formes géométriques ---
    types_formes = (
        svgelements.Path,
        svgelements.Circle,
        svgelements.Ellipse,
        svgelements.Rect,
        svgelements.Line,
        svgelements.Polyline,
        svgelements.Polygon,
        svgelements.SimpleLine,
    )
    if isinstance(element, types_formes):
        # _aplatir_forme retourne une LISTE de polylignes :
        #   - 1 seule pour les formes simples (Rect, Circle, Line...)
        #   - plusieurs pour un Path avec sous-chemins multiples
        polylignes = _aplatir_forme(element)
        if not polylignes:
            return

        couleur = _extraire_couleur(element) or couleur_courante
        type_origine = type(element).__name__.upper()

        # Chaque polyligne (sous-chemin pour un Path) devient une entité
        # indépendante. Le type_origine n'est pas utilisé dans l'UI ni
        # pour la géométrie, donc on garde le même pour toutes.
        for points in polylignes:
            if points is None or len(points) < 2:
                continue
            points_mm = [(x * PX_VERS_MM, y * PX_VERS_MM) for (x, y) in points]
            resultats.append((points_mm, calque_courant, couleur, type_origine))
        return

    # Autres types : ignorés
    return


def _nom_groupe(groupe):
    """Retourne le nom d'un groupe SVG (inkscape:label prioritaire, sinon id)."""
    try:
        if hasattr(groupe, "values") and groupe.values:
            for k, v in groupe.values.items():
                if k == "inkscape:label" and v:
                    return str(v)
        if hasattr(groupe, "id") and groupe.id:
            return str(groupe.id)
    except Exception:
        pass
    return None


def _extraire_couleur(element):
    """
    Retourne la couleur d'un élément SVG sous forme de tuple (r, g, b)
    entiers 0-255, ou None si non définie.
    """
    try:
        for attr in ("stroke", "fill"):
            valeur = getattr(element, attr, None)
            if valeur is None:
                continue
            if hasattr(valeur, "red"):
                if hasattr(valeur, "alpha") and valeur.alpha == 0:
                    continue
                r = int(valeur.red)
                g = int(valeur.green)
                b = int(valeur.blue)
                return (r, g, b)
    except Exception:
        pass
    return None


def _aplatir_forme(element):
    """
    Transforme une forme SVG en une LISTE de polylignes.

    Retourne : list[list[tuple]] (chaque élément = une polyligne de (x, y)).

    - Path : on utilise as_subpaths() pour éclater les sous-chemins.
             Chaque sous-chemin devient une polyligne indépendante.
             Pour chaque sous-chemin, on itère sur ses segments et on prend
             seg.end (méthode B, validée : ~864 pts sur le subpath 0 d'un
             cheval Inkscape, contre 3259 pts avec as_points()).
    - Circle / Ellipse : 1 seule polyligne (échantillonnée)
    - Rect : 1 seule polyligne (4 coins + fermeture)
    - Line : 1 seule polyligne (2 points)
    - Polyline / Polygon : 1 seule polyligne
    """
    import svgelements

    try:
        # --- Path : on éclate en sous-chemins ---
        if isinstance(element, svgelements.Path):
            polylignes = []
            try:
                subpaths = list(element.as_subpaths())
            except Exception:
                subpaths = []

            if subpaths:
                for sp in subpaths:
                    pts = _points_depuis_subpath(sp)
                    if pts is not None and len(pts) >= 2:
                        polylignes.append(pts)
                return polylignes

            # Fallback : as_subpaths absent ou vide -> as_points sur tout
            if hasattr(element, "as_points"):
                try:
                    pts = _points_vers_tuples(list(element.as_points()))
                    if pts and len(pts) >= 2:
                        return [pts]
                except Exception:
                    pass
            return []

        # --- Circle ---
        if isinstance(element, svgelements.Circle):
            pts = _echantillonner_ellipse(
                cx=element.cx, cy=element.cy,
                rx=element.rx, ry=element.ry,
                n=NPATH_POINTS_DEFAUT,
            )
            return [pts] if pts and len(pts) >= 2 else []

        # --- Ellipse ---
        if isinstance(element, svgelements.Ellipse):
            pts = _echantillonner_ellipse(
                cx=element.cx, cy=element.cy,
                rx=element.rx, ry=element.ry,
                n=NPATH_POINTS_DEFAUT,
            )
            return [pts] if pts and len(pts) >= 2 else []

        # --- Rect : 4 coins + fermeture ---
        if isinstance(element, svgelements.Rect):
            x0 = element.x
            y0 = element.y
            x1 = element.x + element.width
            y1 = element.y + element.height
            return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]

        # --- Line / SimpleLine ---
        if isinstance(element, (svgelements.Line, svgelements.SimpleLine)):
            return [[(element.x1, element.y1), (element.x2, element.y2)]]

        # --- Polyline / Polygon ---
        if isinstance(element, (svgelements.Polyline, svgelements.Polygon)):
            pts = [(p.x, p.y) for p in element.points]
            if isinstance(element, svgelements.Polygon) and len(pts) >= 2:
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
            return [pts] if len(pts) >= 2 else []

    except Exception:
        return []

    return []


def _points_depuis_subpath(subpath):
    """
    Extrait les points d'un sous-chemin (Subpath ou Path).
    Méthode : itérer sur les segments et prendre seg.end (méthode B).
    Retourne None si moins de 2 points.
    """
    pts = []
    try:
        for seg in subpath:
            try:
                pts.append((float(seg.end.x), float(seg.end.y)))
            except (AttributeError, ValueError, TypeError):
                continue
    except Exception:
        return None
    return pts if len(pts) >= 2 else None


def _points_vers_tuples(points):
    """Convertit une liste de points svgelements en tuples (x, y)."""
    resultat = []
    for p in points:
        try:
            resultat.append((float(p.x), float(p.y)))
        except (AttributeError, ValueError, TypeError):
            try:
                resultat.append((float(p[0]), float(p[1])))
            except (IndexError, ValueError, TypeError):
                continue
    return resultat if len(resultat) >= 2 else None


def _echantillonner_ellipse(cx, cy, rx, ry, n):
    """
    Échantillonne une ellipse (ou cercle si rx == ry) en n+1 points.
    Le dernier point = le premier (fermeture).
    """
    cx = float(cx)
    cy = float(cy)
    rx = float(rx)
    ry = float(ry)
    points = []
    for i in range(n):
        angle = 2.0 * math.pi * i / n
        points.append((cx + rx * math.cos(angle),
                       cy + ry * math.sin(angle)))
    points.append(points[0])
    return points


# =============================================================================
# API publique
# =============================================================================

def charger_svg(chemin, activer_fusion=False, activer_lissage=True,
                tolerance_lissage=TOLERANCE_LISSAGE_DEFAUT):
    """
    Charge un fichier SVG et retourne la liste des entités converties.

    Arguments :
        chemin             : chemin du fichier SVG
        activer_fusion     : si True, recolle les micro-segments à 2 points
                             (défaut : False, car inadapté aux SVG complexes)
        activer_lissage    : si True, simplifie chaque polyligne (Douglas-Peucker)
        tolerance_lissage  : tolérance du lissage (en MM, après conversion)

    Renvoie un tuple (entites, warnings).
    """
    entites = []
    warnings = []

    try:
        entrees_brutes = _extraire_points_svg(chemin)
    except Exception as e:
        raise RuntimeError(f"Impossible de lire le SVG : {e}")

    if not entrees_brutes:
        warnings.append(
            "Aucune forme exploitable trouvée dans le SVG.\n"
            "Si le SVG contient une image bitmap (photo, dessin raster), "
            "il faut d'abord la vectoriser (Inkscape : Chemin → Vectoriser "
            "un objet matriciel)."
        )
        return entites, warnings

    # --- Étape 1 : fusion des segments (optionnelle) ---
    if activer_fusion and entrees_brutes:
        par_calque = {}
        for (points, calque, couleur, type_orig) in entrees_brutes:
            par_calque.setdefault(calque, []).append(
                (points, couleur, type_orig)
            )

        entrees_apres_fusion = []

        for calque, liste in par_calque.items():
            points_liste = [item[0] for item in liste]
            couleurs = [item[1] for item in liste]
            types_orig = [item[2] for item in liste]

            fusionnees = fusionner_segments(points_liste)

            type_commun = types_orig[0] if types_orig else "FUSION"
            couleur_commune = couleurs[0] if couleurs else None

            for pts in fusionnees:
                entrees_apres_fusion.append(
                    (pts, calque, couleur_commune, f"{type_commun}+FUSION")
                )

        entrees_brutes = entrees_apres_fusion

    # --- Étape 2 : lissage Douglas-Peucker (optionnel) ---
    points_avant = 0
    points_apres = 0

    if activer_lissage:
        entrees_lissees = []
        for (points, calque, couleur, type_orig) in entrees_brutes:
            n_avant = len(points)
            points_lisses = simplifier_polyligne(points, tolerance_lissage)
            n_apres = len(points_lisses)

            points_avant += n_avant
            points_apres += n_apres

            if len(points_lisses) < 2:
                continue

            entrees_lissees.append(
                (points_lisses, calque, couleur, f"{type_orig}+LISS")
            )
        entrees_brutes = entrees_lissees

    # --- Construction des Entite finales ---
    for (points, calque, couleur, type_orig) in entrees_brutes:
        entites.append(Entite(
            type_origine=type_orig,
            points=points,
            calque=calque,
            couleur_aci=None,
            sous_chemins=[points],  # Un seul sous-chemin pour l'instant
        ))

    # --- Warnings ---
    if activer_lissage and points_avant > 0:
        ratio = points_apres / points_avant
        if ratio < 0.95:
            warnings.append(
                f"Lissage : {points_avant} → {points_apres} points "
                f"({int((1 - ratio) * 100)} % de réduction)."
            )

    return entites, warnings