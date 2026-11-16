# =============================================================================
# src/core/generateur_gcode.py
# -----------------------------------------------------------------------------
# Rôle : Générer un fichier G-code à partir d'un projet LaserCNC.
#
# ⚠️ PRINCIPE :
#   1. Les masques sont parcourus DANS L'ORDRE de la liste (le premier masque
#      de la liste est coupé/gravé en premier).
#   2. Pour chaque masque :
#      - On récupère toutes les entités rattachées à ce masque
#      - Pour chaque entité, on fait :
#          G0 vers le premier point (rapide, laser éteint)
#          S0 (éteindre explicitement)
#          G1 entre tous les points (marche, laser allumé)
#          S<valeur> (allumer avant le G1)
#      - Si N passes > 1, on répète tout le masque N fois
#   3. À la fin, on coupe le laser et on retourne à l'origine.
#
# ⚠️ DÉTECTION DES POLYLIGNES OUVERTES :
#   Une polyligne est "ouverte" si son premier point est différent de son
#   dernier point. Avant génération, on demande à l'utilisateur s'il veut
#   les graver ou les ignorer.
#
# ⚠️ CONVERSION PUISSANCE :
#   Les masques stockent leur puissance en % (0-100).
#   Le G-code utilise la valeur S dans la plage de la carte ($30 dans GRBL).
#   On lit $30 depuis le contrôleur GRBL connecté, ou on utilise 1000 par
#   défaut si le contrôleur n'est pas disponible.
#
# Ce module N'AFFICHE RIEN et NE PARLE PAS À LA MACHINE.
# Il lit un projet, génère du texte, l'écrit dans un fichier.
# =============================================================================


# --- Import du module de scanline (remplissage) -----------------------------
try:
    from src.core.scanline import generer_scanline
except ImportError:
    # Fallback si le module n'est pas disponible : on ne fait pas de fill
    generer_scanline = None


# --- Puissance max par défaut (si on n'a pas accès à $30 de la carte) --------
S_MAX_DEFAUT = 1000

# --- Tolérance pour considérer que 2 points sont identiques (mm) ------------
TOLERANCE_FERMETURE = 0.01


# =============================================================================
# Détection des polylignes ouvertes
# =============================================================================

def _distance_carree(p1, p2):
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return dx * dx + dy * dy


def est_polyligne_ouverte(points, tolerance=TOLERANCE_FERMETURE):
    """
    Retourne True si la polyligne est ouverte (premier point != dernier point).
    Une polyligne fermée commence et finit au meme point.
    """
    if len(points) < 2:
        return True
    d2 = _distance_carree(points[0], points[-1])
    return d2 > (tolerance * tolerance)


def compter_polylignes_ouvertes(entites):
    """
    Compte le nombre d'entités qui sont des polylignes ouvertes.
    Retourne un tuple (nb_ouvertes, nb_total).
    """
    nb_ouvertes = 0
    for ent in entites:
        if est_polyligne_ouverte(ent.points):
            nb_ouvertes += 1
    return nb_ouvertes, len(entites)


# =============================================================================
# Génération du G-code
# =============================================================================

def _generer_polyligne(lignes, chemins, s_valeur, vitesse):
    """
    Genere les lignes de G-code pour parcourir un groupe de chemins (contour + trous).

    Pour chaque chemin du groupe :
      S0           (laser eteint)
      G0 X Y       (deplacement rapide au 1er point)
      M3 S<valeur> (allumage consigne)
      G1 F<vitesse>(activation PWM + vitesse)
      G1 X Y ...   (parcours des points suivants)
      M5           (extinction consigne)
      G0           (mouvement qui force la coupure PWM)
    """
    if not chemins:
        return

    for points in chemins:
        if len(points) < 2:
            continue

        # Deplacement rapide vers le 1er point
        lignes.append("S0")
        x0, y0 = points[0]
        lignes.append(f"G0 X{x0:.3f} Y{y0:.3f}")

        # Allumage du laser
        lignes.append(f"M4 S{s_valeur}")

        # Parcours des points : le F est collé au premier G1
        premier = True
        for (x, y) in points[1:]:
            if premier:
                lignes.append(f"G1 X{x:.3f} Y{y:.3f} F{vitesse:.0f}")
                premier = False
            else:
                lignes.append(f"G1 X{x:.3f} Y{y:.3f}")

        # Extinction du laser
        lignes.append("M5")
        lignes.append("G0")


def _generer_fill_entites(lignes, entites, s_valeur, vitesse,
                          espacement, angle, sens):
    """
    Genere le remplissage (scanline) pour un GROUPE d'entites.

    Si plusieurs entites sont passees, elles sont traitees comme des
    contours d'une meme forme (even-odd rule) : la 1ere est le contour
    exterieur, les suivantes sont des TROUS.

    Cas particulier : quand on traite les entites individuellement, on
    peut appeler cette fonction avec une seule entite dans la liste
    -> comportement identique a avant.

    Chaque segment devient un deplacement G-code :
      S0
      G0 X Y      (debut du segment)
      M3 S<val>   (allumage)
      G1 F<vit>   (vitesse)
      G1 X Y      (fin du segment)
      M5          (extinction)
      G0          (mouvement de coupure PWM)
    """
    if generer_scanline is None:
        return

    if not entites:
        return

    # Recuperer les contours (tous les sous-chemins de chaque entite)
    contours = []
    for ent in entites:
        if hasattr(ent, "tous_les_chemins"):
            chemins = ent.tous_les_chemins()
        else:
            chemins = [ent.points] if ent.points else []
        for pts in chemins:
            if pts and len(pts) >= 3:
                contours.append(pts)

    if not contours:
        return

    # Si un seul contour, on peut le passer directement ; sinon, on
    # passe la liste de contours
    arg = contours if len(contours) > 1 else contours[0]

    # Calcul des segments de remplissage
    try:
        segments = generer_scanline(
            arg,
            espacement_mm=espacement,
            angle_deg=angle,
            sens=sens,
        )
    except Exception:
        return

    if not segments:
        return

    # Tolerance pour considerer que deux points sont identiques (mm)
    TOL_PROXIMITE = 0.01

    # Memorise la fin du segment precedent pour detecter l'enchainement
    # (mode "aller_retour" : le debut du segment suivant correspond a la
    # fin du precedent, a un decalage Y pres).
    dernier_point = None

    for (x1, y1, x2, y2) in segments:
        # On est deja au bon endroit si le debut du segment est proche
        # de la fin du segment precedent.
        deja_sur_place = False
        if dernier_point is not None:
            dx = abs(dernier_point[0] - x1)
            dy = abs(dernier_point[1] - y1)
            if dx <= TOL_PROXIMITE and dy <= TOL_PROXIMITE:
                deja_sur_place = True

        # Deplacement au debut du segment.
        # - Le M5 precedent a deja eteint le laser (consigne).
        # - Le G0 (avec coordonnees) force la coupure PWM au prochain
        #   mouvement, donc le "G0 vide" intermediaire est inutile.
        # - Le "S0" est redondant avec le M5 precedent, donc supprime.
        lignes.append(f"G0 X{x1:.3f} Y{y1:.3f}")

        # Gravure du segment.
        lignes.append(f"M4 S{s_valeur}")
        lignes.append(f"G1 F{vitesse:.0f}")
        lignes.append(f"G1 X{x2:.3f} Y{y2:.3f}")
        lignes.append("M5")

        # Memoriser la fin du segment pour le suivant
        dernier_point = (x2, y2)


def _bbox_entites(entites, marge=0.0):
    """
    Retourne (x_min, y_min, x_max, y_max) de la bbox des entites,
    etendue d'une marge. Retourne None si aucune entite n'a de points.
    """
    x_min = y_min = None
    x_max = y_max = None
    for ent in entites:
        for (x, y) in ent.points:
            if x_min is None or x < x_min: x_min = x
            if x_max is None or x > x_max: x_max = x
            if y_min is None or y < y_min: y_min = y
            if y_max is None or y > y_max: y_max = y
    if x_min is None:
        return None
    return (x_min - marge, y_min - marge, x_max + marge, y_max + marge)


def _rectangle_depuis_bbox(bbox):
    """
    Retourne une polyligne fermee (5 points) representant le rectangle
    (x_min, y_min, x_max, y_max).
    """
    if bbox is None:
        return []
    x_min, y_min, x_max, y_max = bbox
    return [
        (x_min, y_min),
        (x_max, y_min),
        (x_max, y_max),
        (x_min, y_max),
        (x_min, y_min),
    ]


def generer_gcode(masques, entites, s_max=S_MAX_DEFAUT,
                  graver_ouvertes=True):
    """
    Génère la liste des lignes de G-code pour le projet.

    Arguments :
        masques           : liste des masques (dans l'ordre de coupe)
        entites           : liste de TOUTES les entités du projet
                            (chacune a un attribut .calque = nom du masque)
        s_max             : valeur maximale de S (issue de $30 de GRBL)
        graver_ouvertes   : si False, on ignore les polylignes ouvertes

    Retourne : une liste de chaînes (une ligne de G-code par élément).

    ⚠️ Chaque masque = un groupe d'entités avec sa propre puissance,
       sa propre vitesse, et son propre nombre de passes.
    """
    lignes = []

    # --- En-tête du fichier ---
    lignes.append("; ============================================")
    lignes.append("; Fichier généré par LaserCNC")
    lignes.append("; ============================================")
    lignes.append("G21  ; unités en mm")
    lignes.append("G90  ; mode absolu")
    lignes.append("S0   ; laser éteint au démarrage")
    lignes.append("")

    # --- Parcours des masques dans l'ordre ---
    for masque in masques:
        # Entités rattachées à ce masque
        entites_masque = [e for e in entites if e.calque == masque.nom]

        if not entites_masque:
            continue  # rien à faire pour ce masque

        # --- Parametres LINE (contour) ---
        s_line = int(round(masque.puissance_line / 100.0 * s_max))
        s_line = max(0, min(s_max, s_line))
        vitesse_line = masque.vitesse_line if masque.vitesse_line > 0 else 500.0
        passes_line = max(1, masque.passes_line)

        # --- Parametres FILL (remplissage) ---
        s_fill = int(round(masque.puissance_fill / 100.0 * s_max))
        s_fill = max(0, min(s_max, s_fill))
        vitesse_fill = masque.vitesse_fill if masque.vitesse_fill > 0 else 3000.0
        passes_fill = max(1, masque.passes_fill)
        espacement_fill = masque.espacement_fill
        angle_fill = masque.angle_fill
        sens_fill = masque.sens_fill

        # --- Recuperation du mode de rendu ---
        mode_rendu = getattr(masque, "mode_rendu", "line")

        faire_fill = mode_rendu in ("fill", "line+fill")
        faire_line = mode_rendu in ("line", "line+fill")

        # En-tête du masque
        lignes.append(f"; === Masque : {masque.nom} (mode: {mode_rendu}) ===")
        if faire_line:
            lignes.append(f"; [LINE] P={masque.puissance_line}% (S{s_line}) "
                          f"V={vitesse_line} mm/min N={passes_line}")
        if faire_fill:
            lignes.append(f"; [FILL] P={masque.puissance_fill}% (S{s_fill}) "
                          f"V={vitesse_fill} mm/min N={passes_fill} "
                          f"espacement={espacement_fill}mm "
                          f"angle={angle_fill}deg sens={sens_fill}")
        lignes.append("")

        # --- Ordre d'execution en line+fill : FILL d'abord, LINE ensuite ---

        # 1) FILL
        if faire_fill:
            inverser = getattr(masque, "inverser_fill", False)
            marge_inverse = getattr(masque, "marge_fill_inverse", 5.0)

            # --- MODE FILL INVERSE : un seul "groupe" englobant ---
            if inverser:
                # 1. Calculer la bbox du masque + marge
                bbox = _bbox_entites(entites_masque, marge=marge_inverse)
                if bbox is None:
                    lignes.append("; [FILL INVERSE] Aucune entite avec points.")
                else:
                    # 2. Construire un rectangle ferme
                    rectangle = _rectangle_depuis_bbox(bbox)

                    # 3. Grouper : [rectangle (contour exterieur)]
                    #             + [toutes les entites (trous)]
                    groupe_inverse = [type("Faux", (), {"points": rectangle})()]
                    for ent in entites_masque:
                        if len(ent.points) >= 3:
                            groupe_inverse.append(ent)

                    # 4. Generer le fill inverse pour chaque passe
                    for num_passe in range(passes_fill):
                        if passes_fill > 1:
                            lignes.append(
                                f"; --- [FILL INVERSE] Passe {num_passe + 1}/"
                                f"{passes_fill} ---"
                            )
                        _generer_fill_entites(
                            lignes, groupe_inverse, s_fill, vitesse_fill,
                            espacement_fill, angle_fill, sens_fill
                        )
                        lignes.append("")
            else:
                # --- MODE FILL NORMAL (inchange) ---
                groupes = []
                textes_vus = {}

                for ent in entites_masque:
                    if len(ent.points) < 3:
                        continue
                    type_orig = getattr(ent, "type_origine", "")
                    if type_orig.startswith("TEXT_"):
                        parts = type_orig.split("_")
                        if len(parts) >= 3:
                            id_texte = parts[1]
                            if id_texte in textes_vus:
                                idx_groupe = textes_vus[id_texte]
                                groupes[idx_groupe].append(ent)
                            else:
                                textes_vus[id_texte] = len(groupes)
                                groupes.append([ent])
                            continue
                    groupes.append([ent])

                for num_passe in range(passes_fill):
                    if passes_fill > 1:
                        lignes.append(f"; --- [FILL] Passe {num_passe + 1}/"
                                      f"{passes_fill} ---")
                    for groupe in groupes:
                        _generer_fill_entites(
                            lignes, groupe, s_fill, vitesse_fill,
                            espacement_fill, angle_fill, sens_fill
                        )
                    lignes.append("")

        # 2) LINE (contour)
        if faire_line:
            for num_passe in range(passes_line):
                if passes_line > 1:
                    lignes.append(f"; --- [LINE] Passe {num_passe + 1}/"
                                  f"{passes_line} ---")
                for ent in entites_masque:
                    points = ent.points
                    if len(points) < 2:
                        continue

                    # Polyligne ouverte ?
                    ouverte = est_polyligne_ouverte(points)
                    if ouverte and not graver_ouvertes:
                        continue

                    if hasattr(ent, "tous_les_chemins"):
                        chemins = ent.tous_les_chemins()
                    else:
                        chemins = [ent.points] if ent.points else []
                    _generer_polyligne(lignes, chemins, s_line, vitesse_line)

                lignes.append("")  # ligne vide entre les passes

        # Fin du masque : laser éteint proprement
        lignes.append("M5")
        lignes.append("G0")
        lignes.append("")

    # --- Fin de programme ---
    lignes.append("; ============================================")
    lignes.append("; Fin de programme")
    lignes.append("; ============================================")
    lignes.append("M5     ; laser éteint (consigne)")
    lignes.append("G0 X0 Y0  ; retour à l'origine (force la coupure PWM)")
    lignes.append("M30    ; fin de programme")

    return lignes


# =============================================================================
# Écriture dans un fichier
# =============================================================================

def ecrire_fichier(chemin, lignes):
    """
    Écrit la liste de lignes dans un fichier texte (encodage UTF-8).
    Retourne le nombre de lignes écrites.
    """
    with open(chemin, "w", encoding="utf-8") as f:
        for ligne in lignes:
            f.write(ligne + "\n")
    return len(lignes)