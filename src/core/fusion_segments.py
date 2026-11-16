# =============================================================================
# src/core/fusion_segments.py
# -----------------------------------------------------------------------------
# Rôle : Fusionner les segments connectés d'un DXF en polylignes continues.
#
# ⚠️ PROBLÈME RÉSOLU :
#   Les DXF issus d'Inkscape découpent souvent une courbe en des CENTAINES
#   de micro-segments. Visuellement, c'est UN dessin, mais dans le modèle
#   ce sont des centaines d'entités séparées. Résultat :
#     - Interface lourde
#     - Manipulation difficile (il faut sélectionner chaque segment)
#     - G-code énorme (Étape 5)
#
#   Cet algorithme recolle les segments bout à bout pour reconstituer des
#   polylignes continues, comme ce que LightBurn ou AutoCAD feraient.
#
# ⚠️ ALGORITHME :
#   1. On indexe tous les points de début/fin de chaque segment (arrondis
#      pour permettre une tolérance)
#   2. On cherche les connexions entre segments (2 segments partagent un
#      point avec tolérance TOLERANCE_FUSION)
#   3. On chaîne les segments bout à bout tant qu'il y a une seule
#      continuation possible
#   4. En cas d'embranchement (plus de 2 segments sur un point), on choisit
#      la continuation la plus ALIGNÉE (celle dont l'angle est le plus proche
#      de 180°, donc la plus "droite")
#   5. En fin de chaînage, on a une polyligne. On recommence tant qu'il
#      reste des segments non traités.
#
# ⚠️ CAS GÉRÉS :
#   - Boucles fermées (le dernier point rejoint le premier)
#   - Segments isolés (rien à fusionner, restent tels quels)
#   - Embranchements (traitement pragmatique, cf. étape 4)
#   - Polylignes déjà longues (rien à faire, elles restent)
# =============================================================================

import math


# --- Tolérance de fusion (mm) ------------------------------------------------
# Deux points sont considérés identiques si leur distance est < TOLERANCE.
# 0.01 mm est la valeur standard (précision typique d'un laser).
TOLERANCE_FUSION = 0.01


def _cle_point(x, y, tolerance):
    """
    Retourne une clé de hachage pour un point, arrondi à la tolérance.
    Deux points à moins de `tolerance` l'un de l'autre auront la même clé.
    """
    return (round(x / tolerance), round(y / tolerance))


def _distance_carree(p1, p2):
    """Distance au carré entre deux points (x, y). Pas de racine carrée."""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return dx * dx + dy * dy


def _angle_entre(v1, v2):
    """
    Retourne l'angle (en radians) entre deux vecteurs 2D (dx, dy).
    Renvoie 0 si l'un des vecteurs est nul.
    """
    n1 = math.hypot(v1[0], v1[1])
    n2 = math.hypot(v2[0], v2[1])
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cos_a = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    # Bornage pour éviter les erreurs numériques sur acos
    cos_a = max(-1.0, min(1.0, cos_a))
    return math.acos(cos_a)


def fusionner_segments(liste_points, tolerance=TOLERANCE_FUSION):
    """
    Fusionne une liste de polylignes (chacune = liste de points (x, y))
    en polylignes plus longues.

    Arguments :
        liste_points : liste de polylignes (listes de tuples (x, y))
        tolerance    : distance max (mm) pour considérer deux points comme
                       identiques

    Retourne : une nouvelle liste de polylignes, potentiellement plus courtes
               que l'entrée (des segments ont été fusionnés).

    ⚠️ IMPORTANT :
        - Les polylignes d'origine ne sont pas modifiées (on en crée des
          nouvelles).
        - L'ordre d'apparition des polylignes de sortie n'est pas garanti
          identique à celui d'entrée.
    """
    # -------------------------------------------------------------------------
    # 1) Préparation : on ne fusionne QUE les polylignes à 2 points
    # -------------------------------------------------------------------------
    # Les polylignes déjà plus longues (3 points et plus) sont considérées
    # comme "déjà fusionnées" et ne sont pas retouchées. Ça évite de casser
    # des structures déjà valides et ça accélère l'algo.
    segments_simples = []     # polylignes à 2 points (à fusionner)
    polylignes_gardees = []   # polylignes à 3+ points (conservées telles quelles)

    for pts in liste_points:
        if len(pts) < 2:
            # Polyligne dégénérée : on la garde quand même (rare)
            polylignes_gardees.append(list(pts))
        elif len(pts) == 2:
            segments_simples.append(list(pts))
        else:
            polylignes_gardees.append(list(pts))

    if not segments_simples:
        # Rien à fusionner
        return polylignes_gardees

    # -------------------------------------------------------------------------
    # 2) Indexation des extrémités
    # -------------------------------------------------------------------------
    # Pour chaque extrémité (arrondie à la tolérance), on stocke la liste des
    # segments qui y sont connectés, avec leur index et quel bout (0 ou 1).
    #
    # Utilisation d'un dict : clé = (x_round, y_round), valeur = liste de
    # tuples (index_segment, quel_bout).
    index_extremites = {}

    for i, seg in enumerate(segments_simples):
        cle_d = _cle_point(seg[0][0], seg[0][1], tolerance)
        cle_f = _cle_point(seg[1][0], seg[1][1], tolerance)
        index_extremites.setdefault(cle_d, []).append((i, 0))
        index_extremites.setdefault(cle_f, []).append((i, 1))

    # -------------------------------------------------------------------------
    # 3) Chaînage des segments
    # -------------------------------------------------------------------------
    utilises = [False] * len(segments_simples)
    polylignes_fusionnees = []

    for i_depart in range(len(segments_simples)):
        if utilises[i_depart]:
            continue

        # On démarre une nouvelle polyligne avec le segment i_depart
        chaine = list(segments_simples[i_depart])
        utilises[i_depart] = True

        # On essaie d'étendre la chaîne DANS LES DEUX SENS tant qu'on trouve
        # un seul segment connecté à l'extrémité libre.
        # On fait deux passes : une vers la fin de la chaîne, une vers le début.

        # --- Extension vers la FIN de la chaîne ---
        while True:
            dernier_point = chaine[-1]
            cle = _cle_point(dernier_point[0], dernier_point[1], tolerance)
            voisins = index_extremites.get(cle, [])

            # On cherche un segment voisin NON utilisé
            # S'il y en a plusieurs, on prend le plus aligné (cf. embranchement)
            candidats = []
            for (j, bout) in voisins:
                if j == i_depart or not utilises[j]:
                    if not utilises[j]:
                        candidats.append((j, bout))

            if not candidats:
                break

            # Cas 1 : un seul candidat → on le chaîne
            if len(candidats) == 1:
                j, bout = candidats[0]
                seg_j = segments_simples[j]
                # On doit retourner le segment si son extrémité qui touche
                # est son PREMIER point (bout == 0)
                if bout == 0:
                    # bout[0] touche la fin de notre chaîne → on ajoute
                    # bout[1] (l'autre extrémité) à la chaîne
                    chaine.append(seg_j[1])
                else:
                    # bout[1] touche la fin → on ajoute bout[0]
                    chaine.append(seg_j[0])
                utilises[j] = True
                continue

            # Cas 2 : plusieurs candidats → on choisit le plus aligné
            meilleur = None
            meilleur_penalite = None
            for (j, bout) in candidats:
                seg_j = segments_simples[j]
                # Extrémité de seg_j qui touche la chaîne, et l'autre bout
                if bout == 0:
                    p_touche = seg_j[0]
                    p_suivant = seg_j[1]
                else:
                    p_touche = seg_j[1]
                    p_suivant = seg_j[0]

                # Direction actuelle de la chaîne (du point avant-dernier
                # vers le dernier point)
                if len(chaine) >= 2:
                    avant = chaine[-2]
                    direction_chain = (dernier_point[0] - avant[0],
                                       dernier_point[1] - avant[1])
                else:
                    direction_chain = (0, 0)

                # Direction du candidat
                direction_cand = (p_suivant[0] - p_touche[0],
                                  p_suivant[1] - p_touche[1])

                # On veut que direction_cand soit dans le PROLONGEMENT de
                # direction_chain → angle entre les deux proche de 0 (car
                # on veut qu'ils aillent "dans le même sens")
                angle = _angle_entre(direction_chain, direction_cand)

                if meilleur_penalite is None or angle < meilleur_penalite:
                    meilleur_penalite = angle
                    meilleur = (j, bout, p_suivant)

            if meilleur is None:
                break

            j, bout, p_suivant = meilleur
            chaine.append(p_suivant)
            utilises[j] = True

        # --- Extension vers le DÉBUT de la chaîne ---
        while True:
            premier_point = chaine[0]
            cle = _cle_point(premier_point[0], premier_point[1], tolerance)
            voisins = index_extremites.get(cle, [])

            candidats = []
            for (j, bout) in voisins:
                if not utilises[j]:
                    candidats.append((j, bout))

            if not candidats:
                break

            if len(candidats) == 1:
                j, bout = candidats[0]
                seg_j = segments_simples[j]
                if bout == 0:
                    # bout[0] touche le début → on insère bout[1] au début
                    chaine.insert(0, seg_j[1])
                else:
                    chaine.insert(0, seg_j[0])
                utilises[j] = True
                continue

            # Plusieurs candidats : on choisit celui le plus aligné en sens
            # INVERSE (on veut prolonger la chaîne vers l'arrière)
            meilleur = None
            meilleur_penalite = None
            for (j, bout) in candidats:
                seg_j = segments_simples[j]
                if bout == 0:
                    p_touche = seg_j[0]
                    p_suivant = seg_j[1]
                else:
                    p_touche = seg_j[1]
                    p_suivant = seg_j[0]

                if len(chaine) >= 2:
                    apres = chaine[1]
                    direction_chain = (premier_point[0] - apres[0],
                                       premier_point[1] - apres[1])
                else:
                    direction_chain = (0, 0)

                direction_cand = (p_touche[0] - p_suivant[0],
                                  p_touche[1] - p_suivant[1])

                angle = _angle_entre(direction_chain, direction_cand)

                if meilleur_penalite is None or angle < meilleur_penalite:
                    meilleur_penalite = angle
                    meilleur = (j, bout, p_suivant)

            if meilleur is None:
                break

            j, bout, p_suivant = meilleur
            chaine.insert(0, p_suivant)
            utilises[j] = True

        polylignes_fusionnees.append(chaine)

    # -------------------------------------------------------------------------
    # 4) Résultat : polylignes fusionnées + polylignes déjà longues
    # -------------------------------------------------------------------------
    return polylignes_fusionnees + polylignes_gardees