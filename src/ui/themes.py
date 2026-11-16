# =============================================================================
# src/ui/themes.py
# -----------------------------------------------------------------------------
# Rôle : Gestion des thèmes visuels de l'application Nala.
#
# Principe :
#   3 thèmes (clair, sombre, coloré) × 3 accents (bleu, vert, orange)
#   × 3 contrastes (léger, marqué, fort) = 27 combinaisons possibles.
#
#   Le thème est stocké dans QSettings et appliqué au démarrage.
#
# Ce module N'AFFICHE RIEN et NE PARLE PAS À LA MACHINE.
# =============================================================================

from PySide6.QtCore import QSettings


# =============================================================================
# Thèmes de base (couleurs principales)
# =============================================================================

THEMES = {
    "clair": {
        "nom": "Clair",
        "fond": "#fafafa",
        "fond_secondaire": "#f0f0f0",
        "fond_tertiaire": "#e8e8e8",
        "texte": "#222222",
        "texte_secondaire": "#555555",
        "bordure": "#cccccc",
        "bordure_forte": "#999999",
        "alerte": "#c0392b",
        "alerte_fond": "#fadbd8",
        "scene_fond": "#ffffff",
        "scene_zone": "#d35400",
    },
    "sombre": {
        "nom": "Sombre",
        "fond": "#52565c",
        "fond_secondaire": "#5d6167",
        "fond_tertiaire": "#6b6f75",
        "texte": "#ffffff",
        "texte_secondaire": "#d0d3d8",
        "bordure": "#3a3c40",
        "bordure_forte": "#80848a",
        "alerte": "#ff7b7b",
        "alerte_fond": "#4e3b3b",
        "scene_fond": "#3a3d42",
        "scene_zone": "#ffaa55",
    },
    "colore": {
        "nom": "Coloré",
        # Sera généré dynamiquement en fonction de la teinte choisie
    },
}

# Teintes de fond pour le thème Coloré
TEINTES_FOND = {
    "lavande": {
        "nom": "Lavande",
        "fond": "#f5f0ff", "fond_secondaire": "#ede4ff", "fond_tertiaire": "#e0d4f5",
        "texte": "#1a1a2a", "texte_secondaire": "#4a4a6a",
        "bordure": "#b8a8d8", "bordure_forte": "#8a7aa8",
        "alerte": "#c0392b", "alerte_fond": "#f5d0d0",
        "scene_fond": "#ffffff", "scene_zone": "#d35400",
    },
    "bleu": {
        "nom": "Bleu ciel",
        "fond": "#f0f8ff", "fond_secondaire": "#e1f0fa", "fond_tertiaire": "#d0e4f5",
        "texte": "#1a2a3a", "texte_secondaire": "#4a6a8a",
        "bordure": "#a8c8e8", "bordure_forte": "#7aa8d0",
    },
    "vert": {
        "nom": "Menthe",
        "fond": "#f0fff4", "fond_secondaire": "#e1fae8", "fond_tertiaire": "#d0f0db",
        "texte": "#1a3a2a", "texte_secondaire": "#4a8a6a",
        "bordure": "#a8e8c8", "bordure_forte": "#7ad0a0",
    },
    "rose": {
        "nom": "Rose poudré",
        "fond": "#fff0f5", "fond_secondaire": "#fae1eb", "fond_tertiaire": "#f0d0de",
        "texte": "#3a1a2a", "texte_secondaire": "#8a4a6a",
        "bordure": "#e8a8c8", "bordure_forte": "#d07aa0",
    },
    "peche": {
        "nom": "Pêche",
        "fond": "#fff5f0", "fond_secondaire": "#fae8e1", "fond_tertiaire": "#f5dcd0",
        "texte": "#3a2a1a", "texte_secondaire": "#8a6a4a",
        "bordure": "#e8c8a8", "bordure_forte": "#d0a87a",
    },
}


# =============================================================================
# Accents (couleur principale : boutons, onglet actif, focus)
# =============================================================================

ACCENTS = {
    "bleu": {
        "nom": "Bleu",
        "principal": "#2073a6",  # Bleu un peu plus profond
        "survol": "#2980b9",
        "presse": "#155c8a",
        "texte": "#ffffff",
    },
    "vert": {
        "nom": "Vert",
        "principal": "#1f8b4c",  # Vert un peu plus profond
        "survol": "#27ae60",
        "presse": "#166b39",
        "texte": "#ffffff",
    },
    "orange": {
        "nom": "Orange",
        "principal": "#c4671b",  # Orange un peu plus profond
        "survol": "#e67e22",
        "presse": "#9e5113",
        "texte": "#ffffff",
    },
}


# =============================================================================
# Contrastes (intensité de l'accent)
# =============================================================================

CONTRASTES = {
    "leger": {
        "nom": "Léger",
        "epaisseur_bordure": 1,
        "opacite_fond": 0.15,   # opacité du fond coloré (boutons, onglet actif)
        "opacite_accent": 0.7,  # opacité de l'accent en mode léger
    },
    "marque": {
        "nom": "Marqué",
        "epaisseur_bordure": 1,
        "opacite_fond": 0.25,
        "opacite_accent": 1.0,
    },
    "fort": {
        "nom": "Fort",
        "epaisseur_bordure": 2,
        "opacite_fond": 0.35,
        "opacite_accent": 1.0,
    },
}


# =============================================================================
# Combinaison par défaut
# =============================================================================

THEME_DEFAUT = "clair"
ACCENT_DEFAUT = "bleu"
CONTRASTE_DEFAUT = "marque"


# =============================================================================
# Construction de la feuille de style
# =============================================================================

def _hex_avec_alpha(couleur_hex, alpha):
    """
    Convertit un code #rrggbb + une opacité (0.0-1.0) en rgba(r, g, b, a).
    """
    if not couleur_hex.startswith("#") or len(couleur_hex) != 7:
        return couleur_hex
    r = int(couleur_hex[1:3], 16)
    g = int(couleur_hex[3:5], 16)
    b = int(couleur_hex[5:7], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def obtenir_couleurs_scene(theme, teinte_fond="lavande"):
    """Retourne les couleurs spécifiques pour la scène (fond, zone)."""
    if theme == "colore" and teinte_fond in TEINTES_FOND:
        t = TEINTES_FOND[teinte_fond]
    else:
        t = THEMES.get(theme, THEMES[THEME_DEFAUT])
    
    return {
        "fond": t.get("scene_fond", "#ffffff"),
        "zone": t.get("scene_zone", "#d35400"),
    }

def obtenir_stylesheet(theme, accent, contraste, teinte_fond="lavande"):
    """
    Retourne une chaîne QSS complète pour la combinaison demandée.
    
    Args:
        theme : clé de THEMES (clair / sombre / colore)
        accent : clé de ACCENTS (bleu / vert / orange)
        contraste : clé de CONTRASTES (leger / marque / fort)
    
    Retourne : str (QSS)
    """
    # Si on est en mode Coloré, on charge la palette de la teinte choisie
    if theme == "colore" and teinte_fond in TEINTES_FOND:
        t = dict(TEINTES_FOND[teinte_fond])
        t["nom"] = "Coloré"
        t["alerte"] = "#c0392b"
        t["alerte_fond"] = "#f5d0d0"
    else:
        t = THEMES.get(theme, THEMES[THEME_DEFAUT])
        if theme not in THEMES:
             t = THEMES[THEME_DEFAUT]

    a = ACCENTS.get(accent, ACCENTS[ACCENT_DEFAUT])
    c = CONTRASTES.get(contraste, CONTRASTES[CONTRASTE_DEFAUT])

    # Couleurs dérivées
    accent_principal = _hex_avec_alpha(a["principal"], c["opacite_accent"])
    accent_survol = _hex_avec_alpha(a["survol"], c["opacite_accent"])
    accent_presse = _hex_avec_alpha(a["presse"], c["opacite_accent"])
    accent_fond_leger = _hex_avec_alpha(a["principal"], c["opacite_fond"])
    accent_fond_survol = _hex_avec_alpha(a["survol"], c["opacite_fond"])

    bordure = t["bordure"]
    bordure_forte = t["bordure_forte"]
    ep = c["epaisseur_bordure"]

    qss = f"""
/* ===== Fenêtre principale ===== */
QMainWindow {{
    font-family: "Inter";
    background-color: {t['fond']};
}}
QWidget {{
    background-color: {t['fond']};
    color: {t['texte']};
}}

/* ===== Onglets ===== */
QTabWidget::pane {{
    border: {ep}px solid {bordure};
    background-color: {t['fond']};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {t['fond_secondaire']};
    color: {t['texte_secondaire']};
    padding: 6px 14px;
    border: {ep}px solid {bordure};
    border-bottom: none;
    margin-right: 2px;
}}
QTabBar::tab:hover {{
    background-color: {accent_fond_survol};
    color: {t['texte']};
}}
QTabBar::tab:selected {{
    background-color: {accent_fond_leger};
    color: {t['texte']};
    border-bottom: {ep}px solid {accent_principal};
    font-weight: bold;
}}

/* ===== Boutons ===== */
QPushButton {{
    background-color: {t['fond_secondaire']};
    color: {t['texte']};
    border: {ep}px solid {bordure};
    border-radius: 4px;
    padding: 4px 10px;
}}
QPushButton:hover {{
    background-color: {accent_fond_survol};
    border: {ep}px solid {accent_principal};
}}
QPushButton:pressed {{
    background-color: {accent_presse};
    color: {a['texte']};
}}
QPushButton:disabled {{
    color: {t['texte_secondaire']};
    border: {ep}px solid {bordure};
}}

/* ===== Champs de saisie ===== */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {t['fond_secondaire']};
    color: {t['texte']};
    border: {ep}px solid {bordure};
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: {accent_principal};
    selection-color: {a['texte']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: {ep}px solid {accent_principal};
}}
QComboBox::drop-down {{
    border: none;
}}
QComboBox QAbstractItemView {{
    background-color: {t['fond_secondaire']};
    color: {t['texte']};
    border: {ep}px solid {bordure};
    selection-background-color: {accent_principal};
    selection-color: {a['texte']};
}}

/* ===== Listes ===== */
QListWidget {{
    background-color: {t['fond_secondaire']};
    color: {t['texte']};
    border: {ep}px solid {bordure};
    border-radius: 3px;
}}
QListWidget::item:selected {{
    background-color: {accent_principal};
    color: {a['texte']};
}}

/* ===== Groupes ===== */
QGroupBox {{
    background-color: {t['fond']};
    border: {ep}px solid {bordure};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
    color: {t['texte']};
}}

/* ===== Cases à cocher / radios ===== */
QCheckBox, QRadioButton {{
    color: {t['texte']};
    background-color: transparent;
}}

/* ===== Barres de défilement ===== */
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {t['fond_secondaire']};
    border: none;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {bordure_forte};
    border-radius: 3px;
    min-height: 20px;
    min-width: 20px;
}}
QScrollBar::handle:hover {{
    background: {accent_principal};
}}

/* ===== Labels ===== */
QLabel {{
    color: {t['texte']};
    background-color: transparent;
}}
"""

    # Règles spécifiques (avertissements, zones, boutons d'action)
    qss += f"""
/* ===== Avertissements ===== */
QLabel[class="avertissement"] {{
    color: {t['alerte']};
    background-color: {t['alerte_fond']};
    padding: 8px;
    border-radius: 4px;
    border-left: 4px solid {t['alerte']};
}}

/* ===== Zones d'aperçu (images, etc.) ===== */
QLabel[class="zone_apercu"] {{
    background-color: {t['fond_tertiaire']};
    border: {ep}px solid {bordure};
    border-radius: 4px;
}}

/* ===== Boutons d'action (Générer, Envoyer, etc.) ===== */
QPushButton[class="action"] {{
    background-color: {accent_principal};
    color: {a['texte']};
    font-weight: bold;
    border: {ep}px solid {accent_presse};
    border-radius: 4px;
    padding: 8px 16px;
}}
QPushButton[class="action"]:hover {{
    background-color: {accent_survol};
}}
QPushButton[class="action"]:pressed {{
    background-color: {accent_presse};
}}
QPushButton[class="action"]:disabled {{
    background-color: {accent_principal};
    color: {a['texte']};
    border: {ep}px solid {accent_presse};
    opacity: 0.5;
}}
"""

    # Règle spécifique pour les boutons de danger/sécurité (ex: Point Laser)
    qss += f"""
QPushButton[class="danger"] {{
    background-color: #e67e22;
    color: white;
    font-weight: bold;
    border: {ep}px solid #d35400;
    border-radius: 4px;
    padding: 4px 10px;
}}
QPushButton[class="danger"]:hover {{
    background-color: #f39c12;
}}
QPushButton[class="danger"]:pressed {{
    background-color: #c0681a;
}}
QPushButton[class="danger"]:disabled {{
    background-color: #7f8c8d;
    border: {ep}px solid #555555;
    color: #aaaaaa;
}}
"""

    return qss.strip()


# =============================================================================
# Lecture / écriture des préférences
# =============================================================================

def charger_preferences():
    """
    Lit les préférences de thème depuis QSettings.
    Retourne un tuple (theme, accent, contraste).
    """
    settings = QSettings("Nala", "LaserCNC")
    theme = settings.value("apparence/theme", THEME_DEFAUT)
    accent = settings.value("apparence/accent", ACCENT_DEFAUT)
    contraste = settings.value("apparence/contraste", CONTRASTE_DEFAUT)
    teinte = settings.value("apparence/teinte_fond", "lavande")

    # Sécurités : si une clé invalide a été écrite, on retombe sur le défaut
    if theme not in THEMES:
        theme = THEME_DEFAUT
    if accent not in ACCENTS:
        accent = ACCENT_DEFAUT
    if contraste not in CONTRASTES:
        contraste = CONTRASTE_DEFAUT

    return theme, accent, contraste, teinte


def sauvegarder_preferences(theme, accent, contraste, teinte_fond="lavande"):
    """
    Sauvegarde les préférences de thème dans QSettings.
    """
    settings = QSettings("Nala", "LaserCNC")
    settings.setValue("apparence/theme", theme)
    settings.setValue("apparence/accent", accent)
    settings.setValue("apparence/contraste", contraste)
    settings.setValue("apparence/teinte_fond", teinte_fond)