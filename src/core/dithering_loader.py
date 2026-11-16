# =============================================================================
# src/core/dithering_loader.py
# -----------------------------------------------------------------------------
# Rôle : Préparer une image pour la gravure photo (dithering).
#
# Principe :
#   1. Chargement de l'image (Pillow) et passage en niveaux de gris.
#   2. Redimensionnement selon la largeur cible (mm) et la résolution (mm/px).
#   3. Application du dithering (Floyd-Steinberg) -> matrice de 0 (noir) et 1 (blanc).
#   4. Génération du G-code ligne par ligne (scanlines) avec modulation de puissance.
#
# ⚠️ La modulation de puissance nécessite le mode M4 (rampes GRBL).
# =============================================================================

import numpy as np
from PIL import Image


def _charger_et_redimensionner(chemin, largeur_mm, resolution_mm,
                                inverser=False):
    """
    Charge l'image, la passe en niveaux de gris et la redimensionne.

    Arguments :
        chemin       : chemin de l'image
        largeur_mm   : largeur cible en mm
        resolution_mm: taille d'un pixel en mm (ex: 0.1 mm)
        inverser     : si True, inverse les gris (utile si fond noir/sujet clair)

    Retourne : (np.ndarray uint8 2D, largeur_px, hauteur_px, hauteur_mm)
    """
    img = Image.open(chemin).convert("L")

    # Calcul de la taille en pixels
    largeur_px = int(round(largeur_mm / resolution_mm))
    if largeur_px < 1:
        largeur_px = 1

    # Hauteur proportionnelle
    ratio = img.height / img.width
    hauteur_px = int(round(largeur_px * ratio))
    if hauteur_px < 1:
        hauteur_px = 1

    hauteur_mm = hauteur_px * resolution_mm

    # Redimensionnement (BICUBIC est un bon compromis)
    img_redim = img.resize((largeur_px, hauteur_px), Image.Resampling.BICUBIC)

    tableau = np.array(img_redim, dtype=np.uint8)

    if inverser:
        tableau = 255 - tableau

    return tableau, largeur_px, hauteur_px, hauteur_mm


def _dithering_jarvis(tableau_gris):
    """Applique l'algorithme de Jarvis, Judice & Ninke."""
    img = tableau_gris.astype(np.float32)
    h, w = img.shape
    for y in range(h):
        for x in range(w):
            ancien = img[y, x]
            nouveau = 255.0 if ancien > 127.0 else 0.0
            img[y, x] = nouveau
            erreur = ancien - nouveau
            if x + 1 < w: img[y, x + 1] += erreur * 7 / 48
            if x + 2 < w: img[y, x + 2] += erreur * 5 / 48
            if y + 1 < h:
                if x > 0: img[y + 1, x - 1] += erreur * 3 / 48
                if x < w: img[y + 1, x] += erreur * 5 / 48
                if x + 1 < w: img[y + 1, x + 1] += erreur * 7 / 48
                if x + 2 < w: img[y + 1, x + 2] += erreur * 5 / 48
            if y + 2 < h:
                if x > 0: img[y + 2, x - 1] += erreur * 1 / 48
                if x < w: img[y + 2, x] += erreur * 3 / 48
                if x + 1 < w: img[y + 2, x + 1] += erreur * 5 / 48
                if x + 2 < w: img[y + 2, x + 2] += erreur * 3 / 48
    return img < 128.0

def _dithering_stucki(tableau_gris):
    """Applique l'algorithme de Stucki."""
    img = tableau_gris.astype(np.float32)
    h, w = img.shape
    for y in range(h):
        for x in range(w):
            ancien = img[y, x]
            nouveau = 255.0 if ancien > 127.0 else 0.0
            img[y, x] = nouveau
            erreur = ancien - nouveau
            if x + 1 < w: img[y, x + 1] += erreur * 8 / 42
            if x + 2 < w: img[y, x + 2] += erreur * 4 / 42
            if y + 1 < h:
                if x > 0: img[y + 1, x - 1] += erreur * 2 / 42
                if x < w: img[y + 1, x] += erreur * 4 / 42
                if x + 1 < w: img[y + 1, x + 1] += erreur * 8 / 42
                if x + 2 < w: img[y + 1, x + 2] += erreur * 4 / 42
            if y + 2 < h:
                if x > 0: img[y + 2, x - 1] += erreur * 1 / 42
                if x < w: img[y + 2, x] += erreur * 2 / 42
                if x + 1 < w: img[y + 2, x + 1] += erreur * 4 / 42
                if x + 2 < w: img[y + 2, x + 2] += erreur * 2 / 42
    return img < 128.0

def _dithering_atkinson(tableau_gris):
    """Applique l'algorithme d'Atkinson."""
    img = tableau_gris.astype(np.float32)
    h, w = img.shape
    for y in range(h):
        for x in range(w):
            ancien = img[y, x]
            nouveau = 255.0 if ancien > 127.0 else 0.0
            img[y, x] = nouveau
            erreur = ancien - nouveau
            if x + 1 < w: img[y, x + 1] += erreur * 1 / 8
            if x + 2 < w: img[y, x + 2] += erreur * 1 / 8
            if y + 1 < h:
                if x > 0: img[y + 1, x - 1] += erreur * 1 / 8
                if x < w: img[y + 1, x] += erreur * 1 / 8
                if x + 1 < w: img[y + 1, x + 1] += erreur * 1 / 8
            if y + 2 < h:
                if x < w: img[y + 2, x] += erreur * 1 / 8
    return img < 128.0

def _dithering_bayer(tableau_gris):
    """Applique l'algorithme de Bayer (ordonné)."""
    img = tableau_gris.astype(np.float32)
    h, w = img.shape
    # Matrice de Bayer 4x4
    matrice_bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) / 16.0
    for y in range(h):
        for x in range(w):
            seuil = matrice_bayer[y % 4, x % 4] * 255.0
            img[y, x] = 255.0 if img[y, x] > seuil else 0.0
    return img < 128.0

def _dithering_floyd_steinberg(tableau_gris):
    """
    Applique l'algorithme de Floyd-Steinberg sur un tableau de niveaux de gris.

    Arguments :
        tableau_gris : np.ndarray uint8 (2D)

    Retourne : np.ndarray bool (2D) — True = pixel noir (à graver), False = blanc.
    """
    # On travaille en float pour propager les erreurs
    img = tableau_gris.astype(np.float32)
    h, w = img.shape

    for y in range(h):
        for x in range(w):
            ancien = img[y, x]
            nouveau = 255.0 if ancien > 127.0 else 0.0
            img[y, x] = nouveau
            erreur = ancien - nouveau

            # Propagation de l'erreur (Floyd-Steinberg)
            if x + 1 < w:
                img[y, x + 1] += erreur * 7 / 16
            if y + 1 < h:
                if x > 0:
                    img[y + 1, x - 1] += erreur * 3 / 16
                img[y + 1, x] += erreur * 5 / 16
                if x + 1 < w:
                    img[y + 1, x + 1] += erreur * 1 / 16

    # True = noir (à graver)
    return img < 128.0


def generer_gcode_photo(chemin, largeur_mm=100.0, resolution_mm=0.1,
                        vitesse=1500, puissance_max=1000, puissance_min=0,
                        inverser=False, algo="floyd"):
    """
    Pipeline complet : chargement -> redimensionnement -> dithering -> G-code.

    Arguments :
        chemin         : chemin de l'image
        largeur_mm     : largeur cible en mm
        resolution_mm  : taille d'un pixel en mm
        vitesse        : vitesse d'avance en mm/min
        puissance_max  : S max (ex: 1000 pour $30=1000)
        puissance_min  : S min (0 pour laser éteint)
        inverser       : inverse noir/blanc

    Retourne : (liste de lignes G-code, warnings)
    """
    warnings = []

    # 1. Chargement et redimensionnement
    tableau, largeur_px, hauteur_px, hauteur_mm = _charger_et_redimensionner(
        chemin, largeur_mm, resolution_mm, inverser
    )

    # 2. Dithering
    if algo == "jarvis":
        matrice = _dithering_jarvis(tableau)
    elif algo == "stucki":
        matrice = _dithering_stucki(tableau)
    elif algo == "atkinson":
        matrice = _dithering_atkinson(tableau)
    elif algo == "bayer":
        matrice = _dithering_bayer(tableau)
    else:
        matrice = _dithering_floyd_steinberg(tableau)

    # 3. Génération du G-code (optimisée)
    lignes = []

    # En-tête
    lignes.append("; Genere par Nala (Gravure Photo - Dithering)")
    lignes.append(f"; Largeur : {largeur_mm} mm, Hauteur : {hauteur_mm:.2f} mm")
    lignes.append(f"; Resolution : {resolution_mm} mm/px")
    lignes.append(f"; Vitesse : {vitesse} mm/min")
    lignes.append("G21 ; mm")
    lignes.append("G90 ; absolu")
    lignes.append(f"M4 S{puissance_max} ; mode laser dynamique, puissance initiale")

    y_mm = 0.0
    for y in range(hauteur_px):
        # Ligne impaire : on va de droite a gauche (serpentin)
        if y % 2 == 1:
            x_range = range(largeur_px - 1, -1, -1)
        else:
            x_range = range(largeur_px)

        # --- Debut de la ligne : on se positionne au premier point ---
        x_premier = list(x_range)[0]
        x_mm_premier = x_premier * resolution_mm
        
        # Puissance du premier pixel (pour ne pas faire de mouvement inutile)
        est_noir_premier = matrice[y, x_premier]
        puissance_premier = puissance_max if est_noir_premier else puissance_min
        
        # On se deplace au debut de la ligne (laser eteint, G0)
        lignes.append(f"G0 X{x_mm_premier:.3f} Y{y_mm:.3f}")

        # --- Parcours de la ligne ---
        # On stocke la position x du dernier changement de couleur
        x_mm_changement = x_mm_premier
        etat_precedent = est_noir_premier

        # On parcourt a partir du 2eme pixel
        for x in list(x_range)[1:]:
            x_mm = x * resolution_mm
            est_noir = matrice[y, x]

            # Si on change de couleur, on trace le segment du changement
            if est_noir != etat_precedent:
                # On finit le segment precedent avec l'ancienne puissance
                puissance = puissance_max if etat_precedent else puissance_min
                lignes.append(
                    f"G1 X{x_mm:.3f} Y{y_mm:.3f} S{puissance} F{vitesse}"
                )
                
                # On commence le nouveau segment
                x_mm_changement = x_mm
                etat_precedent = est_noir

        # --- Fin de la ligne : on ferme le dernier segment ---
        x_fin = list(x_range)[-1]
        x_mm_fin = x_fin * resolution_mm
        puissance_fin = puissance_max if etat_precedent else puissance_min
        lignes.append(f"G1 X{x_mm_fin:.3f} Y{y_mm:.3f} S{puissance_fin} F{vitesse}")

        # On eteint le laser en fin de ligne SANS desactiver M4.
        # Important : M5 desactive le mode laser dans GRBL, et les S des
        # lignes suivantes seraient ignores. On utilise S0 a la place.
        lignes.append("S0")
        y_mm += resolution_mm

    # Fin
    lignes.append("M5")
    lignes.append("G0 X0 Y0")
    lignes.append("M2 ; fin")

    # Debug : compter les pixels noirs
    nb_pixels_noirs = int(np.sum(matrice))
    total_pixels = int(matrice.size)
    
    warnings.append(f"Dimensions : {largeur_px} x {hauteur_px} pixels.")
    warnings.append(f"Taille : {largeur_mm} x {hauteur_mm:.2f} mm.")
    warnings.append(f"Pixels a graver : {nb_pixels_noirs} / {total_pixels}.")
    warnings.append(f"Lignes G-code (optimisees) : {len(lignes)}.")

    return lignes, warnings


def estimer_temps_photo(largeur_mm, hauteur_mm, vitesse, temps_par_ligne=0.05):
    """
    Estime le temps de gravure (très approximatif).
    """
    nb_lignes = int(hauteur_mm)  # approximation
    temps_aller = (largeur_mm / vitesse) * 60.0  # en secondes
    temps_total = nb_lignes * (temps_aller + temps_par_ligne)
    return temps_total