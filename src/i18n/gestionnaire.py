# =============================================================================
# src/i18n/gestionnaire.py
# -----------------------------------------------------------------------------
# Rôle : Gestion de l'internationalisation (i18n) de Nala.
#
# Principe :
#   - Au démarrage, on lit la langue depuis QSettings (défaut : français).
#   - On charge le fichier .qm correspondant (src/i18n/nala_fr.qm ou nala_en.qm).
#   - Si le fichier n'existe pas, on reste en français (textes originaux).
#
# Ce module N'AFFICHE RIEN et NE PARLE PAS À LA MACHINE.
# =============================================================================

import os
from pathlib import Path
from PySide6.QtCore import QTranslator, QSettings, QLocale


# Langues supportées
LANGUES_DISPONIBLES = [
    ("fr", "Français"),
    ("en", "English"),
]

LANGUE_DEFAUT = "fr"


def dossier_i18n():
    """Retourne le chemin du dossier src/i18n/."""
    return Path(__file__).parent


def charger_langue(app):
    """
    Charge la langue sauvegardée dans QSettings et installe le traducteur.

    Args:
        app : l'instance QApplication

    Retourne : le code de la langue chargée ("fr" ou "en")
    """
    settings = QSettings("Nala", "LaserCNC")
    langue = settings.value("apparence/langue", LANGUE_DEFAUT)

    # Vérifier que la langue est supportée
    codes_valides = [code for code, _ in LANGUES_DISPONIBLES]
    if langue not in codes_valides:
        langue = LANGUE_DEFAUT

    # Si c'est le français (langue de base), pas besoin de traducteur
    if langue == "fr":
        return "fr"

    # Charger le fichier .qm pour les autres langues
    chemin_qm = dossier_i18n() / f"nala_{langue}.qm"
    if not chemin_qm.exists():
        print(f"[i18n] Fichier de traduction introuvable : {chemin_qm}")
        print(f"[i18n] La langue reste en français par défaut.")
        return "fr"

    traducteur = QTranslator()
    if traducteur.load(str(chemin_qm)):
        app.installTranslator(traducteur)
        print(f"[i18n] Langue chargée : {langue}")
        app._traducteur_nala = traducteur
        return langue
    else:
        print(f"[i18n] Échec du chargement de {chemin_qm}")
        return "fr"


def sauvegarder_langue(langue):
    """Sauvegarde la langue dans QSettings."""
    settings = QSettings("Nala", "LaserCNC")
    settings.setValue("apparence/langue", langue)


def obtenir_langue():
    """Retourne la langue actuellement sauvegardée."""
    settings = QSettings("Nala", "LaserCNC")
    langue = settings.value("apparence/langue", LANGUE_DEFAUT)
    codes_valides = [code for code, _ in LANGUES_DISPONIBLES]
    if langue not in codes_valides:
        langue = LANGUE_DEFAUT
    return langue