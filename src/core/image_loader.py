# =============================================================================
# src/core/image_loader.py
# -----------------------------------------------------------------------------
# Rôle : Lire une image bitmap (JPG, PNG, BMP...) et la convertir en liste
#        d'ENTITÉS (contours vectorisés) exploitables par le reste du programme.
#
# Principe :
#   1. Pillow charge l'image et la convertit en niveaux de gris.
#   2. On seuille (noir/blanc) pour obtenir un masque binaire.
#   3. potracer (portage Python pur de Potrace) vectorise ce masque
#      en courbes de Bézier.
#   4. On récupère les points échantillonnés (decomposition_points),
#      on les nettoie, on les lisse (Douglas-Peucker) comme pour DXF/SVG.
#   5. Chaque contour fermé devient une Entite.
#
# ⚠️ ORIENTATION :
#   Les images ont Y vers le BAS. Le repère machine a Y vers le HAUT.
#   On inverse Y à l'import (option flipper_y=True par défaut) pour que
#   l'image apparaisse "dans le bon sens" dans la zone de travail.
#
# ⚠️ SEUILLAGE :
#   - seuil=None  → seuil automatique (méthode d'Otsu)
#   - seuil=0..255 → seuil manuel (pixels < seuil = noir = à vectoriser)
#
# Ce module N'AFFICHE RIEN et NE PARLE PAS À LA MACHINE.
# =============================================================================

import math

import numpy as np
from PIL import Image, ImageOps

from potrace import Bitmap

from src.core.dxf_loader import Entite, simplifier_polyligne, TOLERANCE_LISSAGE_DEFAUT


# Seuil par défaut (mi-chemin noir/blanc, robuste pour de la vectorisation nette)
SEUIL_DEFAUT = 128


# --- Nombre max de points pour une courbe Potrace donnée ---------------------
# potracer fournit decomposition_points déjà échantillonnés ; on ne fait
# qu'un nettoyage + lissage ensuite.
# (Pas de constante nécessaire ici, potrace choisit lui-même.)


# =============================================================================
# Seuillage automatique (méthode d'Otsu)
# =============================================================================

def _seuil_otsu(tableau_gris):
    """
    Calcule le seuil optimal (0-255) via la méthode d'Otsu.

    Arguments :
        tableau_gris : np.ndarray uint8 (2D), image en niveaux de gris

    Retourne : int (seuil entre 0 et 255)

    Notes :
        Méthode classique : on cherche le seuil qui maximise la variance
        inter-classes (fond vs forme). Robuste pour la plupart des images.
    """
    # Histogramme des niveaux de gris (256 bins)
    hist = np.bincount(tableau_gris.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 128  # image vide → seuil neutre

    # Probabilités et moyennes cumulées
    prob = hist / total
    omega = np.cumsum(prob)              # poids cumulé classe 0
    mu = np.cumsum(prob * np.arange(256))  # moyenne cumulée classe 0

    mu_total = mu[-1]

    # Variance inter-classes pour chaque seuil t
    # (on évite les divisions par zéro aux extrémités)
    denom = omega * (1.0 - omega)
    # On protège les t où denom == 0
    with np.errstate(divide='ignore', invalid='ignore'):
        sigma_b = (mu_total * omega - mu) ** 2 / denom
    sigma_b = np.nan_to_num(sigma_b, nan=0.0, posinf=0.0, neginf=0.0)

    seuil = int(np.argmax(sigma_b))
    return seuil


# =============================================================================
# Chargement + préparation du masque binaire
# =============================================================================

def _preparer_masque_binaire(chemin, seuil=SEUIL_DEFAUT, inverser=False):
    """
    Charge l'image, la convertit en niveaux de gris, la seuille.

    Arguments :
        chemin    : chemin de l'image
        seuil     : int (0-255), "otsu" (auto), ou None (=SEUIL_DEFAUT)
        inverser  : si True, inverse noir/blanc avant vectorisation

    Retourne : (np.ndarray bool binaire, seuil_utilise, largeur_px, hauteur_px)
               - binaire : True = à vectoriser (noir), False = fond
    """
    img = Image.open(chemin)
    img_gris = img.convert("L")
    tableau = np.array(img_gris, dtype=np.uint8)

    # Résolution du seuil
    if seuil is None:
        seuil_utilise = SEUIL_DEFAUT
    elif isinstance(seuil, str) and seuil.lower() == "otsu":
        seuil_utilise = _seuil_otsu(tableau)
    else:
        seuil_utilise = int(seuil)

    # Pixel < seuil → True (à graver), sinon False
    binaire = (tableau < seuil_utilise)

    if inverser:
        binaire = ~binaire

    largeur_px = binaire.shape[1]
    hauteur_px = binaire.shape[0]

    return binaire, seuil_utilise, largeur_px, hauteur_px


# =============================================================================
# Vectorisation via potracer
# =============================================================================

def _vectoriser_masque(binaire, largeur_px, hauteur_px):
    """
    Vectorise un masque binaire via potracer.

    Arguments :
        binaire      : np.ndarray bool (2D), True = à vectoriser
        largeur_px   : largeur de l'image (pour filtrer le contour du bord)
        hauteur_px   : hauteur de l'image

    Retourne : (liste de contours en pixels, nb_contours_ignores)

    Notes :
        - potracer exige un tableau **bool** (pas uint32/uint8).
        - Potrace trace aussi le contour du fond blanc (bord de l'image).
          On l'ignore : si la bbox d'un contour couvre >95% de l'image,
          c'est le contour du bord, on le rejette.
    """
    bmp = Bitmap(binaire)  # ⚠️ bool obligatoire
    chemin_potrace = bmp.trace()

    contours = []
    contours_ignores = 0

    for courbe in chemin_potrace:
        points_bruts = courbe.decomposition_points

        points = [(float(p.x), float(p.y)) for p in points_bruts]

        if len(points) < 3:
            continue

        # Filtre : rejeter le contour du bord (bbox ≈ image entière)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        largeur_bbox = max(xs) - min(xs)
        hauteur_bbox = max(ys) - min(ys)

        if (largeur_bbox > 0.95 * largeur_px and
                hauteur_bbox > 0.95 * hauteur_px):
            contours_ignores += 1
            continue

        contours.append(points)

    return contours, contours_ignores


# =============================================================================
# Conversion pixels → millimètres
# =============================================================================

def _convertir_en_mm(contours_px, largeur_px, hauteur_px,
                     taille_mm=None, flipper_y=True):
    """
    Convertit une liste de contours des pixels vers les millimètres.

    Arguments :
        contours_px : liste de listes de tuples (x_px, y_px)
        largeur_px  : largeur de l'image en pixels
        hauteur_px  : hauteur de l'image en pixels
        taille_mm   : si fourni, largeur cible en mm (hauteur auto proportionnelle)
                      si None, on garde l'échelle 1 px = 1 mm (rare, à éviter)
        flipper_y   : si True, inverse Y (image → repère machine)

    Retourne : liste de contours en mm.
    """
    if taille_mm is not None and taille_mm > 0:
        echelle = taille_mm / float(largeur_px)  # mm par pixel
    else:
        echelle = 1.0  # 1 px = 1 mm (fallback, à utiliser consciemment)

    hauteur_mm = hauteur_px * echelle

    contours_mm = []
    for contour in contours_px:
        nouveau = []
        for (x_px, y_px) in contour:
            x_mm = x_px * echelle
            if flipper_y:
                # Y image (bas) → Y machine (haut)
                y_mm = hauteur_mm - y_px * echelle
            else:
                y_mm = y_px * echelle
            nouveau.append((x_mm, y_mm))
        contours_mm.append(nouveau)

    return contours_mm


# =============================================================================
# API publique
# =============================================================================

def charger_image(chemin, seuil=SEUIL_DEFAUT, taille_mm=None, inverser=False,
                  flipper_y=True, activer_lissage=True,
                  tolerance_lissage=TOLERANCE_LISSAGE_DEFAUT,
                  detourage_auto=False, seuil_detourage=0.05):
    """
    Charge une image bitmap et retourne la liste des entités vectorisées.

    Arguments :
        chemin             : chemin de l'image (JPG, PNG, BMP...)
        seuil              : int 0-255 (défaut 128), "otsu" (auto), ou None (=128)
        taille_mm          : largeur cible en mm (None = 1 px = 1 mm)
        inverser           : si True, inverse noir/blanc avant vectorisation
        flipper_y          : si True (défaut), inverse Y à l'import
        activer_lissage    : si True, simplifie chaque contour (Douglas-Peucker)
        tolerance_lissage  : tolérance du lissage en mm

    Renvoie un tuple (entites, warnings).

    Notes :
        - Chaque contour fermé devient une Entite indépendante.
        - type_origine = "IMAGE_PATH"
        - calque = "IMAGE"
        - Les coordonnées sont en mm, origine (0,0) = coin bas-gauche de l'image.
    """
    entites = []
    warnings = []

    # --- 1. Préparation du masque binaire ---
    try:
        binaire, seuil_utilise, largeur_px, hauteur_px = _preparer_masque_binaire(
            chemin, seuil=seuil, inverser=inverser
        )
    except Exception as e:
        return [], [f"Échec du chargement de l'image : {e}"]

    if largeur_px == 0 or hauteur_px == 0:
        return [], ["Image vide (largeur ou hauteur nulle)."]

    # --- 2. Vectorisation ---
    try:
        contours_px, contours_ignores = _vectoriser_masque(
            binaire, largeur_px, hauteur_px
        )
    except Exception as e:
        return [], [f"Échec de la vectorisation : {e}"]

    if not contours_px:
        return [], ["Aucun contour détecté (image uniforme ou seuil inadapté)."]

    # --- 2bis. Détourage automatique (filtre de surface RÉELLE) ---
    if detourage_auto and contours_px:
        # Calcul de la surface totale de l'image
        surface_totale = largeur_px * hauteur_px
        seuil_surface = surface_totale * seuil_detourage
        
        def surface_polygone(points):
            # Formule de Shoelace pour la surface réelle
            n = len(points)
            if n < 3:
                return 0
            area = 0
            for i in range(n):
                j = (i + 1) % n
                area += points[i][0] * points[j][1]
                area -= points[j][0] * points[i][1]
            return abs(area) / 2.0

        contours_filtres = []
        for contour in contours_px:
            surf = surface_polygone(contour)
            if surf >= seuil_surface:
                contours_filtres.append(contour)
        
        if not contours_filtres:
            warnings.append("Détourage : aucun contour n'a passé le filtre de surface. Essayez de baisser le seuil.")
            contours_px = []
        else:
            contours_px = contours_filtres
            warnings.append(f"Détourage : {len(contours_px)} contours conservés (surface > {seuil_detourage*100}%).")

    # --- 3. Conversion en mm ---
    contours_mm = _convertir_en_mm(
        contours_px, largeur_px, hauteur_px,
        taille_mm=taille_mm, flipper_y=flipper_y
    )

    # --- 4. Lissage Douglas-Peucker (optionnel) ---
    points_avant = 0
    points_apres = 0

    if activer_lissage:
        contours_lisses = []
        for contour in contours_mm:
            n_avant = len(contour)
            contour_lisse = simplifier_polyligne(contour, tolerance_lissage)
            n_apres = len(contour_lisse)

            points_avant += n_avant
            points_apres += n_apres

            if len(contour_lisse) >= 3:  # garder les contours fermés valides
                contours_lisses.append(contour_lisse)
        contours_mm = contours_lisses

    # --- 5. Construction des Entite ---
    for contour in contours_mm:
        if len(contour) < 3:
            continue
        entites.append(Entite(
            type_origine="IMAGE_PATH",
            points=contour,
            calque="IMAGE",
            couleur_aci=None,
            sous_chemins=[contour],  # Un seul chemin pour l'instant
        ))

    # --- 6. Warnings ---
    warnings.append(f"Seuil utilisé : {seuil_utilise}")
    if contours_ignores > 0:
        warnings.append(
            f"{contours_ignores} contour(s) ignoré(s) (bord d'image)."
        )

    if activer_lissage and points_avant > 0:
        ratio = points_apres / points_avant
        if ratio < 0.95:
            warnings.append(
                f"Lissage : {points_avant} → {points_apres} points "
                f"({int((1 - ratio) * 100)} % de réduction)."
            )

    warnings.append(f"{len(entites)} contour(s) vectorisé(s).")

    return entites, warnings

def detourer_image(chemin, seuil=SEUIL_DEFAUT, seuil_surface=0.05, taille_mm=None, inverser=False, flipper_y=True):
    """
    Détoure automatiquement une image en ne gardant que les plus grands contours.
    
    Arguments :
        chemin : chemin de l'image
        seuil : seuil de binarisation (0-255 ou "otsu")
        seuil_surface : pourcentage de la surface totale (0.05 = 5%)
        taille_mm : largeur cible en mm
        inverser : inverse noir/blanc
        flipper_y : inverse Y
        
    Retourne : (entites, warnings)
    """
    # Appel de la fonction originale avec detourage_auto=True
    return charger_image(
        chemin=chemin,
        seuil=seuil,
        taille_mm=taille_mm,
        inverser=inverser,
        flipper_y=flipper_y,
        detourage_auto=True,
        seuil_detourage=seuil_surface
    )
