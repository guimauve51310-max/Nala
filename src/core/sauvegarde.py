# =============================================================================
# src/core/sauvegarde.py
# -----------------------------------------------------------------------------
# Rôle : Sauvegarde et chargement d'un projet Nala au format JSON (.nala).
#
# Structure du fichier JSON :
#   {
#     "version": 1,
#     "largeur_zone": 520.0,
#     "hauteur_zone": 420.0,
#     "origine_zone": "fond_gauche",
#     "masques": [ {...}, {...}, ... ],
#     "entites": [ {...}, {...}, ... ]
#   }
#
# Chaque Entite devient :
#   {
#     "type_origine": "PATH",
#     "points": [[x1,y1], [x2,y2], ...],
#     "calque": "Import",
#     "couleur_aci": null,
#     "groupe_id": null
#   }
#
# Chaque Masque devient :
#   {
#     "nom": "Import",
#     "couleur": "#000000",
#     "visible": true,
#     "puissance_line": 0.0, ...,
#     "puissance_fill": 0.0, ...,
#     "mode_rendu": "line",
#     "espacement_fill": 0.10,
#     "angle_fill": 0.0,
#     "sens_fill": "aller_retour",
#     "inverser_fill": false,
#     "marge_fill_inverse": 5.0
#   }
#
# ⚠️ Compatibilité future : le champ "version" permet de détecter les
# anciens fichiers si on change de format plus tard.
# =============================================================================

import json
import os


FORMAT_VERSION = 1
EXTENSION = ".nala"


# =============================================================================
# Sérialisation
# =============================================================================

def _serialiser_entite(entite):
    """Convertit une Entite en dict JSON-compatible."""
    return {
        "type_origine": getattr(entite, "type_origine", "?"),
        "points": [(float(x), float(y)) for (x, y) in entite.points],
        "calque": getattr(entite, "calque", "0"),
        "couleur_aci": getattr(entite, "couleur_aci", None),
        "groupe_id": getattr(entite, "groupe_id", None),
    }


def _serialiser_masque(masque):
    """Convertit un Masque en dict JSON-compatible."""
    return {
        "nom": masque.nom,
        "couleur": masque.couleur_hex(),
        "visible": bool(getattr(masque, "visible", True)),
        "puissance_line": float(masque.puissance_line),
        "vitesse_line": float(masque.vitesse_line),
        "passes_line": int(masque.passes_line),
        "puissance_fill": float(masque.puissance_fill),
        "vitesse_fill": float(masque.vitesse_fill),
        "passes_fill": int(masque.passes_fill),
        "mode_rendu": masque.mode_rendu,
        "espacement_fill": float(masque.espacement_fill),
        "angle_fill": float(masque.angle_fill),
        "sens_fill": masque.sens_fill,
        "inverser_fill": bool(getattr(masque, "inverser_fill", False)),
        "marge_fill_inverse": float(getattr(masque, "marge_fill_inverse", 5.0)),
    }


# =============================================================================
# Désérialisation
# =============================================================================

def _deserialiser_entite(data):
    """Convertit un dict JSON en Entite."""
    from src.core.dxf_loader import Entite

    points = [(float(p[0]), float(p[1])) for p in data.get("points", [])]
    ent = Entite(
        type_origine=data.get("type_origine", "?"),
        points=points,
        calque=data.get("calque", "0"),
        couleur_aci=data.get("couleur_aci", None),
    )
    ent.groupe_id = data.get("groupe_id", None)
    return ent


def _deserialiser_masque(data):
    """Convertit un dict JSON en Masque."""
    from src.core.masque import Masque

    masque = Masque(
        nom=data["nom"],
        couleur=data.get("couleur", "#000000"),
    )
    masque.visible = bool(data.get("visible", True))
    masque.puissance_line = float(data.get("puissance_line", 0.0))
    masque.vitesse_line = float(data.get("vitesse_line", 0.0))
    masque.passes_line = int(data.get("passes_line", 1))
    masque.puissance_fill = float(data.get("puissance_fill", 0.0))
    masque.vitesse_fill = float(data.get("vitesse_fill", 0.0))
    masque.passes_fill = int(data.get("passes_fill", 1))
    masque.mode_rendu = data.get("mode_rendu", "line")
    masque.espacement_fill = float(data.get("espacement_fill", 0.10))
    masque.angle_fill = float(data.get("angle_fill", 0.0))
    masque.sens_fill = data.get("sens_fill", "aller_retour")
    masque.inverser_fill = bool(data.get("inverser_fill", False))
    masque.marge_fill_inverse = float(data.get("marge_fill_inverse", 5.0))
    return masque


# =============================================================================
# API publique
# =============================================================================

def sauvegarder_projet(chemin, projet):
    """
    Sauvegarde un projet complet dans un fichier .nala (JSON).

    Arguments :
        chemin : chemin du fichier (sans ou avec .nala)
        projet : dict {largeur_zone, hauteur_zone, origine_zone,
                       masques, entites}

    Retourne : True si succès, lève une exception sinon.
    """
    data = {
        "version": FORMAT_VERSION,
        "largeur_zone": float(projet.get("largeur_zone", 520.0)),
        "hauteur_zone": float(projet.get("hauteur_zone", 420.0)),
        "origine_zone": projet.get("origine_zone", "fond_gauche"),
        "masques": [_serialiser_masque(m) for m in projet.get("masques", [])],
        "entites": [_serialiser_entite(e) for e in projet.get("entites", [])],
    }

    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return True


def charger_projet(chemin):
    """
    Charge un projet depuis un fichier .nala (JSON).

    Retourne un dict :
        {largeur_zone, hauteur_zone, origine_zone, masques, entites}

    Lève une exception si le fichier est illisible ou corrompu.
    """
    with open(chemin, "r", encoding="utf-8") as f:
        data = json.load(f)

    version = data.get("version", 1)
    if version > FORMAT_VERSION:
        raise RuntimeError(
            f"Fichier trop recent (version {version}, "
            f"ce logiciel supporte jusqu'a {FORMAT_VERSION})."
        )

    return {
        "largeur_zone": float(data.get("largeur_zone", 520.0)),
        "hauteur_zone": float(data.get("hauteur_zone", 420.0)),
        "origine_zone": data.get("origine_zone", "fond_gauche"),
        "masques": [_deserialiser_masque(m) for m in data.get("masques", [])],
        "entites": [_deserialiser_entite(e) for e in data.get("entites", [])],
    }


# =============================================================================
# Derniers fichiers récents (QSettings)
# =============================================================================

CLE_RECENTS = "nala/fichiers_recents"
MAX_RECENTS = 10


def ajouter_fichier_recent(chemin):
    """Ajoute un chemin en tête de la liste des récents (QSettings)."""
    from PySide6.QtCore import QSettings

    settings = QSettings("Nala", "LaserCNC")
    recents = settings.value(CLE_RECENTS, [])
    if isinstance(recents, str):
        recents = [recents]
    if not recents:
        recents = []

    # Retirer le chemin s'il y est déjà (pour le remettre en tête)
    chemin = os.path.abspath(chemin)
    recents = [c for c in recents if os.path.abspath(c) != chemin]

    # Ajouter en tête
    recents.insert(0, chemin)

    # Tronquer à MAX_RECENTS
    recents = recents[:MAX_RECENTS]

    settings.setValue(CLE_RECENTS, recents)


def obtenir_fichiers_recents():
    """Retourne la liste des derniers fichiers (filtrés : existants seulement)."""
    from PySide6.QtCore import QSettings

    settings = QSettings("Nala", "LaserCNC")
    recents = settings.value(CLE_RECENTS, [])
    if isinstance(recents, str):
        recents = [recents]
    if not recents:
        return []

    # Filtrer : ne garder que les fichiers qui existent toujours
    return [c for c in recents if os.path.isfile(c)]


def nettoyer_recents():
    """Supprime tous les fichiers récents de QSettings."""
    from PySide6.QtCore import QSettings

    settings = QSettings("Nala", "LaserCNC")
    settings.remove(CLE_RECENTS)