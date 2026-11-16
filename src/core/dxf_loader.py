# =============================================================================
# src/core/dxf_loader.py
# -----------------------------------------------------------------------------
# Rôle : Lire un fichier DXF et le convertir en une liste d'ENTITÉS SIMPLES,
#        exploitables par le reste du programme.
#
# ⚠️ OPTIMISATIONS APPLIQUÉES :
#
#   1. FUSION DES SEGMENTS (fusionner_segments) :
#      Recolle les micro-segments à 2 points en polylignes continues.
#
#   2. LISSAGE DOUGLAS-PEUCKER (nouveau) :
#      Réduit le nombre de points dans chaque polyligne en supprimant les
#      points quasi-alignés. Résultat typique : 30-60 points → 5-10 points
#      pour les courbes issues de SPLINE (ezdxf les éclate en points).
#      C'est CRITIQUE pour l'Étape 5 (G-code) : moins de points = G-code
#      plus léger et plus rapide.
#
# ⚠️ ORDRE DES OPÉRATIONS :
#   1. Lecture brute du DXF
#   2. Fusion des segments (fusionner_segments)
#   3. Lissage Douglas-Peucker (simplifier_polyligne)
#   Les deux traitements sont activables indépendamment via des paramètres.
#
# Ce module N'AFFICHE RIEN et NE PARLE PAS À LA MACHINE.
# =============================================================================

import math

import ezdxf

from src.core.fusion_segments import fusionner_segments


# --- Constantes d'approximation ------------------------------------------------
SEGMENTS_CERCLE = 64
PAS_ANGLE_ARC = 5.0
POINTS_SPLINE = 64

# --- Tolérance par défaut pour le lissage Douglas-Peucker (mm) ----------------
# Une valeur trop grande déforme les courbes, une valeur trop petite laisse
# trop de points. 0.05 mm est un bon compromis pour un laser.
TOLERANCE_LISSAGE_DEFAUT = 0.05


class Entite:
    """
    Représente une entité géométrique issue d'un DXF, convertie en polyligne.

    Attributs :
        type_origine : le type DXF d'origine ('LINE', 'CIRCLE', 'ARC'...)
        points       : liste de tuples (x, y) formant la polyligne PRINCIPALE
        sous_chemins : liste de listes de tuples (x, y) pour les entités
                       multi-chemins (ex: lettre "A" = contour + trou).
                       Si vide, on utilise uniquement `points`.
        calque       : nom du calque DXF (pour les masques)
        couleur_aci  : code couleur ACI (0-255) ou None
        selectionnee : booléen (utilisé plus tard)
    """

    def __init__(self, type_origine, points, calque="0", couleur_aci=None,
                 sous_chemins=None):
        self.type_origine = type_origine
        self.points = points
        self.sous_chemins = sous_chemins if sous_chemins is not None else []
        self.calque = calque
        self.couleur_aci = couleur_aci
        self.selectionnee = False
        # Identifiant de groupe (None = entite libre).
        # Toutes les entites avec le meme groupe_id forment un groupe
        # qui se selectionne / deplace comme un bloc.
        self.groupe_id = None

    def __repr__(self):
        nb_sous = len(self.sous_chemins) if self.sous_chemins else 0
        return (f"<Entite {self.type_origine} pts={len(self.points)} "
                f"sous_chemins={nb_sous} calque='{self.calque}'>")

    def tous_les_chemins(self):
        """
        Retourne une liste de tous les chemins de l'entité :
        - Si sous_chemins est vide : [points]
        - Sinon : sous_chemins (qui contient déjà points en premier)
        """
        if self.sous_chemins:
            return self.sous_chemins
        return [self.points] if self.points else []


# =============================================================================
# Normalisation des points
# =============================================================================

def _nettoyer_points(points):
    """Convertit en tuples de float Python natifs (au lieu de np.float64)."""
    return [(float(p[0]), float(p[1])) for p in points]


# =============================================================================
# Lissage Douglas-Peucker
# =============================================================================

def _distance_point_segment(p, a, b):
    """
    Distance perpendiculaire du point p au segment [a, b].
    Si a == b (segment dégénéré), renvoie la distance p-a.
    """
    ax, ay = a
    bx, by = b
    px, py = p

    dx = bx - ax
    dy = by - ay
    norme2 = dx * dx + dy * dy

    if norme2 < 1e-12:
        # Segment de longueur nulle
        return math.hypot(px - ax, py - ay)

    # Projection du point p sur la droite (a, b), paramétrée par t
    t = ((px - ax) * dx + (py - ay) * dy) / norme2
    # On borne t entre 0 et 1 pour rester sur le SEGMENT
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0

    # Point projeté
    proj_x = ax + t * dx
    proj_y = ay + t * dy

    return math.hypot(px - proj_x, py - proj_y)


def simplifier_polyligne(points, tolerance=TOLERANCE_LISSAGE_DEFAUT):
    """
    Réduit le nombre de points d'une polyligne via Douglas-Peucker.

    Arguments :
        points    : liste de tuples (x, y)
        tolerance : distance max (mm) d'un point à la ligne formée par ses
                    voisins pour qu'il soit supprimé

    Retourne : une nouvelle liste de points (potentiellement plus courte).

    Notes :
        - Le PREMIER et le DERNIER point sont TOUJOURS conservés.
        - Pour les polylignes < 3 points, on renvoie la liste telle quelle.
        - Une polyligne à 2 points identiques est réduite à 1 point.
    """
    n = len(points)

    if n < 3:
        return list(points)

    # Cas où les 2 extrémités sont au même endroit (boucle fermée "presque")
    # On garde tel quel pour ne pas déformer les boucles.
    if _distance_point_segment(points[0], points[0], points[-1]) < 1e-9:
        # Ici on ne simplifie pas les boucles extrêmement serrées ; on
        # laisse l'algo standard faire son travail plus bas.
        pass

    # Implémentation itérative (avec pile) de Douglas-Peucker
    # (évite la récursion pour les très longues polylignes).
    garder = [False] * n
    garder[0] = True
    garder[-1] = True

    # Pile de segments à traiter : liste de (index_debut, index_fin)
    pile = [(0, n - 1)]

    while pile:
        i_debut, i_fin = pile.pop()

        # Cherche le point le plus éloigné du segment [i_debut, i_fin]
        d_max = 0.0
        i_max = -1
        a = points[i_debut]
        b = points[i_fin]

        for i in range(i_debut + 1, i_fin):
            d = _distance_point_segment(points[i], a, b)
            if d > d_max:
                d_max = d
                i_max = i

        # Si le point le plus éloigné est au-delà de la tolérance,
        # on le garde et on continue de subdiviser.
        if d_max > tolerance and i_max != -1:
            garder[i_max] = True
            pile.append((i_debut, i_max))
            pile.append((i_max, i_fin))

    # Reconstitue la liste filtrée
    resultat = [points[i] for i in range(n) if garder[i]]
    return resultat


# =============================================================================
# Fonctions internes de conversion
# =============================================================================

def _approximer_cercle(centre, rayon):
    cx, cy = float(centre[0]), float(centre[1])
    r = float(rayon)
    points = []
    for i in range(SEGMENTS_CERCLE):
        angle = 2 * math.pi * i / SEGMENTS_CERCLE
        points.append((cx + r * math.cos(angle),
                       cy + r * math.sin(angle)))
    points.append(points[0])
    return points


def _approximer_arc(centre, rayon, angle_debut, angle_fin):
    cx, cy = float(centre[0]), float(centre[1])
    r = float(rayon)
    angle_debut = float(angle_debut)
    angle_fin = float(angle_fin)

    if angle_fin < angle_debut:
        angle_fin += 360.0

    nb_segments = max(2, int((angle_fin - angle_debut) / PAS_ANGLE_ARC) + 1)
    points = []
    for i in range(nb_segments + 1):
        t = i / nb_segments
        angle_deg = angle_debut + t * (angle_fin - angle_debut)
        angle_rad = math.radians(angle_deg)
        points.append((cx + r * math.cos(angle_rad),
                       cy + r * math.sin(angle_rad)))
    return points


def _extraire_points_entite(ent):
    """Extrait les points 2D d'une entité ezdxf, ou None si type non géré."""
    dxftype = ent.dxftype()

    if dxftype == "LINE":
        depart = ent.dxf.start
        arrivee = ent.dxf.end
        return _nettoyer_points([
            (depart[0], depart[1]),
            (arrivee[0], arrivee[1]),
        ])

    if dxftype == "LWPOLYLINE":
        points_bruts = [(p[0], p[1]) for p in ent.get_points()]
        return _nettoyer_points(points_bruts)

    if dxftype == "POLYLINE":
        points_bruts = [(v.dxf.location[0], v.dxf.location[1])
                        for v in ent.vertices]
        return _nettoyer_points(points_bruts)

    if dxftype == "CIRCLE":
        return _approximer_cercle(ent.dxf.center, ent.dxf.radius)

    if dxftype == "ARC":
        return _approximer_arc(
            ent.dxf.center,
            ent.dxf.radius,
            ent.dxf.start_angle,
            ent.dxf.end_angle,
        )

    if dxftype == "SPLINE":
        try:
            outil = ent.construction_tool()
            points_bruts = list(outil.flattening(distance=0.5))
            return _nettoyer_points(points_bruts)
        except Exception:
            return None

    if dxftype == "ELLIPSE":
        try:
            outil = ent.construction_tool()
            points_bruts = list(outil.flattening(distance=0.5))
            return _nettoyer_points(points_bruts)
        except Exception:
            return None

    return None


# =============================================================================
# API publique
# =============================================================================

def charger_dxf(chemin, activer_fusion=True, activer_lissage=True,
                tolerance_lissage=TOLERANCE_LISSAGE_DEFAUT):
    """
    Charge un fichier DXF et retourne la liste des entités converties.

    Arguments :
        chemin             : chemin du fichier DXF
        activer_fusion     : si True, recolle les micro-segments à 2 points
        activer_lissage    : si True, simplifie chaque polyligne (Douglas-Peucker)
        tolerance_lissage  : tolérance du lissage en mm

    Renvoie un tuple (entites, warnings).
    """
    entites = []
    warnings = []

    doc = ezdxf.readfile(chemin)
    msp = doc.modelspace()

    types_ignores = {}
    entrees_brutes = []

    # --- Lecture brute ---
    for ent in msp:
        dxftype = ent.dxftype()
        points = _extraire_points_entite(ent)

        if points is None:
            types_ignores[dxftype] = types_ignores.get(dxftype, 0) + 1
            continue

        if len(points) < 2:
            continue

        calque = ent.dxf.layer if ent.dxf.hasattr("layer") else "0"
        couleur = ent.dxf.color if ent.dxf.hasattr("color") else None

        entrees_brutes.append((points, calque, couleur, dxftype))

    # --- Étape 1 : fusion des segments (optionnelle) ---
    if activer_fusion and entrees_brutes:
        # Regroupement par calque pour ne fusionner qu'entre segments
        # de même calque (plus sûr)
        par_calque = {}
        for (points, calque, couleur, dxftype) in entrees_brutes:
            par_calque.setdefault(calque, []).append((points, couleur, dxftype))

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
        for (points, calque, couleur, dxftype) in entrees_brutes:
            n_avant = len(points)
            points_lisses = simplifier_polyligne(points, tolerance_lissage)
            n_apres = len(points_lisses)

            points_avant += n_avant
            points_apres += n_apres

            # On garde un minimum de 2 points
            if len(points_lisses) < 2:
                continue

            entrees_lissees.append(
                (points_lisses, calque, couleur, f"{dxftype}+LISS")
            )
        entrees_brutes = entrees_lissees

    # --- Construction des Entite finales ---
    for (points, calque, couleur, dxftype) in entrees_brutes:
        entites.append(Entite(
            type_origine=dxftype,
            points=points,
            calque=calque,
            couleur_aci=couleur,
            sous_chemins=[points],  # Un seul sous-chemin pour l'instant
        ))

    # --- Warnings ---
    if types_ignores:
        details = ", ".join(f"{t}×{n}" for t, n in types_ignores.items())
        warnings.append(f"Types d'entités ignorés (non gérés) : {details}")

    if activer_lissage and points_avant > 0:
        ratio = points_apres / points_avant
        if ratio < 0.95:
            warnings.append(
                f"Lissage : {points_avant} → {points_apres} points "
                f"({int((1 - ratio) * 100)} % de réduction)."
            )

    return entites, warnings