# =============================================================================
# LaserCNC.py
# -----------------------------------------------------------------------------
# Rôle : Fenêtre principale de l'application LaserCNC.
#
# Version 17 : ajout de l'onglet "Mise en page"
#   - Nouvel onglet Mise en page (étape 1 : affichage DXF)
#   - Aucune autre modification sur les onglets existants
# =============================================================================

import sys
import os
import glob
import time
from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLabel, QTabWidget, QGroupBox,
    QTextEdit, QLineEdit, QGridLayout, QDoubleSpinBox, QSpinBox, QMessageBox,
    QFormLayout, QCheckBox,
    QFormLayout,
    QFileDialog, QPlainTextEdit, QListWidget, QListWidgetItem
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.grbl.controller import GrblController
from src.grbl.envoi_thread import EnvoiGcodeThread
from src.grbl.statut_thread import StatutThread
from src.ui.apercu import ApercuWidget
from src.ui.mise_en_page import MiseEnPageWidget
from src.i18n import gestionnaire as i18n_gestionnaire
from src.ui.themes import (
    obtenir_stylesheet, charger_preferences, sauvegarder_preferences,
    THEMES, ACCENTS, CONTRASTES, TEINTES_FOND, obtenir_couleurs_scene,
)
from src.core import sauvegarde as module_sauvegarde
from serial.tools import list_ports


# --- Constantes de configuration du jog ---------------------------------------
PAS_DISPONIBLES = [0.1, 1.0, 10.0, 100.0]
VITESSES_DISPONIBLES = [100.0, 500.0, 1000.0, 2000.0]
VITESSE_DEFAUT = 500.0
PAS_DEFAUT = 1.0

# --- Protection anti-double-STOP ----------------------------------------------
STOP_COOLDOWN = 2

# --- Bornes du "Aller à X,Y" --------------------------------------------------
DEPLACEMENT_MIN = -500.0
DEPLACEMENT_MAX = 500.0

# --- Filtres de fichiers G-code -----------------------------------------------
FILTRES_GCODE = "Fichiers G-code (*.nc *.gcode *.ngc *.tap *.txt);;Tous les fichiers (*.*)"

# --- Modes machine disponibles -------------------------------------------------
MODES_MACHINE = [
    ("Laser",     "laser"),
    ("Fraiseuse", "fraiseuse"),
]
MODE_DEFAUT = "laser"


class MainWindow(QMainWindow):
    """Fenêtre principale de LaserCNC."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tr("Nala"))
        self.resize(1100, 750)
        self.setMinimumSize(800, 600)

        # --- Application du thème (lu depuis QSettings) ---
        theme, accent, contraste, teinte = charger_preferences()
        self.setStyleSheet(obtenir_stylesheet(theme, accent, contraste, teinte))

        self.grbl = GrblController()
        self.dernier_wco = (0.0, 0.0, 0.0)
        self.fichier_charge = None

        self.thread_envoi = None
        self.est_en_pause = False

        # Thread de statut permanent (approche GRBL officielle).
        # Seul lecteur du port serie pendant qu'il tourne.
        self.statut_thread = None
        # Dernier rapport de statut brut recu (pour info/debug).
        self.dernier_statut_brut = ""

        # Valeurs reelles des overrides lues dans "Ov:" (rapport GRBL).
        # 100 = nominal. Mises a jour a chaque statut recu.
        self.override_feed_grbl = 100
        self.override_spindle_grbl = 100

        self.mode_machine = MODE_DEFAUT

        # --- Etat de l'onglet Photo ---
        self.photo_chemin = None
        self.photo_lignes_gcode = None

        # Chemin du projet actuel (None si non sauvegarde)
        self.chemin_projet_actuel = None

        self.stop_restant = 0
        self.timer_stop = QTimer(self)
        self.timer_stop.setInterval(1000)
        self.timer_stop.timeout.connect(self.decrementer_stop)

        racine = QWidget()
        layout_racine = QVBoxLayout(racine)
        layout_racine.setContentsMargins(6, 6, 6, 6)
        layout_racine.setSpacing(6)

        # --- Barre supérieure : sélecteur de mode ---
        barre_mode = QHBoxLayout()
        barre_mode.addWidget(QLabel("Mode machine :"))
        self.combo_mode = QComboBox()
        for libelle, cle in MODES_MACHINE:
            self.combo_mode.addItem(libelle, cle)
        for idx, (_, cle) in enumerate(MODES_MACHINE):
            if cle == MODE_DEFAUT:
                self.combo_mode.setCurrentIndex(idx)
                break
        self.combo_mode.setMinimumWidth(140)
        self.combo_mode.currentIndexChanged.connect(self.changer_mode)
        barre_mode.addWidget(self.combo_mode)

        self.label_avert_mode = QLabel("")
        self.label_avert_mode.setStyleSheet(
            "color: white; background-color: #c0392b; "
            "font-weight: bold; padding: 4px 10px; border-radius: 3px;"
        )
        barre_mode.addWidget(self.label_avert_mode)

        barre_mode.addStretch()
        layout_racine.addLayout(barre_mode)

        # --- Onglets ---
        tabs = QTabWidget()
        tabs.setStyleSheet("QTabBar::tab { min-width: 80px; max-width: 150px; height: 28px; }")
        tabs.addTab(self.construire_onglet_connexion(), self.tr("Connexion"))
        tabs.addTab(self.construire_onglet_console(), self.tr("Console"))
        tabs.addTab(self.construire_onglet_jog(), self.tr("Jog"))
        tabs.addTab(self.construire_onglet_calibration(), self.tr("Calibration"))
        tabs.addTab(self.construire_onglet_photo(), self.tr("Photo"))
        tabs.addTab(self.construire_onglet_fichier(), self.tr("Fichier"))
        tabs.addTab(self.construire_onglet_apercu(), self.tr("Aperçu"))
        tabs.addTab(self.construire_onglet_mise_en_page(), self.tr("Mise en page"))
        tabs.addTab(self.construire_onglet_parametres(), self.tr("Paramètres"))
        layout_racine.addWidget(tabs)

        self.setCentralWidget(racine)
        self.appliquer_avertissement_mode()

    # -------------------------------------------------------------------------
    # Gestion du mode machine
    # -------------------------------------------------------------------------

    def changer_mode(self):
        cle = self.combo_mode.currentData()
        self.mode_machine = cle
        self.afficher_console(f"— Mode machine : {self.combo_mode.currentText()} —")
        self.appliquer_avertissement_mode()

    def appliquer_avertissement_mode(self):
        if self.mode_machine == "fraiseuse":
            self.label_avert_mode.setText(
                "⚠ FRISEUSE : la pause n'arrête PAS la broche "
                "(limitation GRBL). Gardez la main sur l'arrêt d'urgence."
            )
        else:
            self.label_avert_mode.setText("")

    # -------------------------------------------------------------------------
    # ONGLET 1 : Connexion
    # -------------------------------------------------------------------------

    def construire_onglet_connexion(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        groupe = QGroupBox(self.tr("Connexion à la machine"))
        groupe.setMaximumHeight(100)
        ligne = QHBoxLayout(groupe)

        ligne.addWidget(QLabel(self.tr("Port :")))
        self.combo_ports = QComboBox()
        self.combo_ports.setMinimumWidth(300)
        self.combo_ports.setToolTip(
            self.tr("Sélectionne le port série de la machine (souvent COM6)")
        )
        ligne.addWidget(self.combo_ports)

        self.btn_rafraichir = QPushButton(self.tr("Rafraîchir"))
        self.btn_rafraichir.setToolTip(
            self.tr("Relance la détection des ports USB disponibles")
        )
        self.btn_rafraichir.clicked.connect(self.rafraichir_ports)
        ligne.addWidget(self.btn_rafraichir)

        self.btn_connecter = QPushButton(self.tr("Connecter"))
        self.btn_connecter.setToolTip(
            self.tr("Connecte / déconnecte la machine via le port sélectionné")
        )
        self.btn_connecter.clicked.connect(self.basculer_connexion)
        ligne.addWidget(self.btn_connecter)

        layout.addWidget(groupe)

        self.label_statut = QLabel(self.tr("Déconnecté"))
        self.label_statut.setStyleSheet("font-size: 16px; padding: 10px;")
        layout.addWidget(self.label_statut)

        layout.addStretch()
        self.rafraichir_ports()
        return widget

    # -------------------------------------------------------------------------
    # ONGLET 2 : Console
    # -------------------------------------------------------------------------

    def construire_onglet_console(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        layout.addWidget(self.console)

        ligne = QHBoxLayout()
        self.champ_commande = QLineEdit()
        self.champ_commande.setPlaceholderText(self.tr("Tapez une commande GRBL (ex : $$ , $X , $H ...)"))
        self.champ_commande.returnPressed.connect(self.envoyer_commande_manuelle)
        ligne.addWidget(self.champ_commande)

        self.btn_envoyer = QPushButton(self.tr("Envoyer"))
        self.btn_envoyer.setToolTip(self.tr("Envoie la commande tapée à la machine"))
        self.btn_envoyer.clicked.connect(self.envoyer_commande_manuelle)
        ligne.addWidget(self.btn_envoyer)

        self.btn_effacer = QPushButton(self.tr("Effacer"))
        self.btn_effacer.setToolTip(self.tr("Efface le contenu de la console"))
        self.btn_effacer.clicked.connect(self.effacer_console)
        ligne.addWidget(self.btn_effacer)

        layout.addLayout(ligne)
        return widget

    # -------------------------------------------------------------------------
    # ONGLET 3 : Jog
    # -------------------------------------------------------------------------

    def construire_onglet_jog(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        groupe_position = QGroupBox(self.tr("Position travail"))
        ligne_position = QHBoxLayout(groupe_position)
        style_pos = "font-family: Consolas, monospace; font-size: 22px; font-weight: bold; padding: 4px 12px;"

        self.label_pos_x = QLabel("X :   ---.---")
        self.label_pos_x.setStyleSheet(style_pos)
        ligne_position.addWidget(self.label_pos_x)

        self.label_pos_y = QLabel("Y :   ---.---")
        self.label_pos_y.setStyleSheet(style_pos)
        ligne_position.addWidget(self.label_pos_y)

        ligne_position.addStretch()

        self.label_etat = QLabel(self.tr("État : ---"))
        self.label_etat.setStyleSheet("font-family: Consolas, monospace; font-size: 18px; padding: 4px 12px;")
        ligne_position.addWidget(self.label_etat)

        layout.addWidget(groupe_position)

        groupe_reglages = QGroupBox(self.tr("Réglages du jog"))
        ligne_reglages = QHBoxLayout(groupe_reglages)

        ligne_reglages.addWidget(QLabel(self.tr("Pas (mm) :")))
        self.combo_pas = QComboBox()
        for pas in PAS_DISPONIBLES:
            self.combo_pas.addItem(f"{pas} mm", pas)
        self.combo_pas.setCurrentIndex(PAS_DISPONIBLES.index(PAS_DEFAUT))
        ligne_reglages.addWidget(self.combo_pas)

        ligne_reglages.addSpacing(20)
        ligne_reglages.addWidget(QLabel(self.tr("Vitesse (mm/min) :")))
        self.combo_vitesse = QComboBox()
        for v in VITESSES_DISPONIBLES:
            self.combo_vitesse.addItem(f"{v}", v)
        self.combo_vitesse.setCurrentIndex(VITESSES_DISPONIBLES.index(VITESSE_DEFAUT))
        ligne_reglages.addWidget(self.combo_vitesse)

        ligne_reglages.addStretch()
        layout.addWidget(groupe_reglages)

        groupe_jog = QGroupBox(self.tr("Déplacement manuel"))
        grid = QGridLayout(groupe_jog)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(4, 1)

        self.btn_y_plus = QPushButton("Y +")
        self.btn_y_plus.setToolTip(self.tr("Déplace la tête vers le haut (Y+)"))
        self.btn_y_plus.setMinimumSize(80, 50)
        self.btn_y_plus.clicked.connect(lambda: self.jog("Y", +1))
        grid.addWidget(self.btn_y_plus, 0, 2)

        self.btn_x_moins = QPushButton("X -")
        self.btn_x_moins.setToolTip(self.tr("Déplace la tête vers la gauche (X-)"))
        self.btn_x_moins.setMinimumSize(80, 50)
        self.btn_x_moins.clicked.connect(lambda: self.jog("X", -1))
        grid.addWidget(self.btn_x_moins, 1, 1)

        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setToolTip(
            self.tr("ARRÊT D'URGENCE : envoie Ctrl-X à GRBL (arrêt immédiat)")
        )
        self.btn_stop.setMinimumSize(100, 50)
        self.btn_stop.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        self.btn_stop.clicked.connect(self.stop_urgence)
        grid.addWidget(self.btn_stop, 1, 2)

        self.btn_x_plus = QPushButton("X +")
        self.btn_x_plus.setToolTip(self.tr("Déplace la tête vers la droite (X+)"))
        self.btn_x_plus.setMinimumSize(80, 50)
        self.btn_x_plus.clicked.connect(lambda: self.jog("X", +1))
        grid.addWidget(self.btn_x_plus, 1, 3)

        self.btn_y_moins = QPushButton("Y -")
        self.btn_y_moins.setToolTip(self.tr("Déplace la tête vers le bas (Y-)"))
        self.btn_y_moins.setMinimumSize(80, 50)
        self.btn_y_moins.clicked.connect(lambda: self.jog("Y", -1))
        grid.addWidget(self.btn_y_moins, 2, 2)

        layout.addWidget(groupe_jog)

        groupe_origine = QGroupBox(self.tr("Origine travail"))
        ligne_origine = QHBoxLayout(groupe_origine)

        self.btn_definir_origine = QPushButton(self.tr("Définir origine ici"))
        self.btn_definir_origine.setToolTip(
            self.tr("Définit la position actuelle comme origine travail (0,0)")
        )
        self.btn_definir_origine.setMinimumHeight(40)
        self.btn_definir_origine.clicked.connect(self.definir_origine_ici)
        ligne_origine.addWidget(self.btn_definir_origine)

        self.btn_retour_origine = QPushButton(self.tr("Retour origine (0,0)"))
        self.btn_retour_origine.setToolTip(
            self.tr("Déplace la tête à l'origine travail (0,0)")
        )
        self.btn_retour_origine.setMinimumHeight(40)
        self.btn_retour_origine.clicked.connect(self.retour_origine)
        ligne_origine.addWidget(self.btn_retour_origine)

        self.btn_deverrouiller = QPushButton(self.tr("Déverrouiller ($X)"))
        self.btn_deverrouiller.setToolTip(
            self.tr("Déverrouille GRBL (après une alarme). Tape $X en interne.")
        )
        self.btn_deverrouiller.setMinimumHeight(40)
        self.btn_deverrouiller.clicked.connect(self.deverrouiller)
        ligne_origine.addWidget(self.btn_deverrouiller)

        layout.addWidget(groupe_origine)

        groupe_aller = QGroupBox(self.tr("Aller à (position absolue)"))
        ligne_aller = QHBoxLayout(groupe_aller)

        ligne_aller.addWidget(QLabel(self.tr("X (mm) :")))
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(DEPLACEMENT_MIN, DEPLACEMENT_MAX)
        self.spin_x.setDecimals(1)
        self.spin_x.setSingleStep(1.0)
        self.spin_x.setValue(0.0)
        ligne_aller.addWidget(self.spin_x)

        ligne_aller.addWidget(QLabel(self.tr("Y (mm) :")))
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(DEPLACEMENT_MIN, DEPLACEMENT_MAX)
        self.spin_y.setDecimals(1)
        self.spin_y.setSingleStep(1.0)
        self.spin_y.setValue(0.0)
        ligne_aller.addWidget(self.spin_y)

        self.btn_aller = QPushButton(self.tr("Aller à ce point"))
        self.btn_aller.setToolTip(
            self.tr("Déplace la tête à la position absolue X/Y indiquée")
        )
        self.btn_aller.setMinimumHeight(40)
        self.btn_aller.clicked.connect(self.aller_a_position)
        ligne_aller.addWidget(self.btn_aller)

        ligne_aller.addStretch()
        layout.addWidget(groupe_aller)

        # --- Point laser (appui maintenu) ---
        groupe_point_laser = QGroupBox(self.tr("Point laser (voir où frappe le laser)"))
        ligne_point = QHBoxLayout(groupe_point_laser)

        ligne_point.addWidget(QLabel(self.tr("Puissance :")))
        self.spin_puissance_point = QDoubleSpinBox()
        self.spin_puissance_point.setRange(0.1, 10.0)     # limite securite a 10 %
        self.spin_puissance_point.setDecimals(1)
        self.spin_puissance_point.setSingleStep(0.5)
        self.spin_puissance_point.setValue(1.0)           # defaut 1 %
        self.spin_puissance_point.setSuffix(" %")
        self.spin_puissance_point.setMinimumWidth(80)
        ligne_point.addWidget(self.spin_puissance_point)

        self.btn_point_laser = QPushButton(self.tr("🔴 Maintenir pour allumer"))
        self.btn_point_laser.setToolTip(self.tr("Maintiens appuyé pour allumer le laser (voir où il frappe)"))
        self.btn_point_laser.setMinimumHeight(40)
        self.btn_point_laser.setProperty("class", "danger")
        self.btn_point_laser.setEnabled(False)            # active a la connexion
        self.btn_point_laser.pressed.connect(self.allumer_point_laser)
        self.btn_point_laser.released.connect(self.eteindre_point_laser)
        ligne_point.addWidget(self.btn_point_laser)

        ligne_point.addStretch()
        layout.addWidget(groupe_point_laser)

        info = QLabel(self.tr("⚠️  STOP = Ctrl-X GRBL (arrêt immédiat). "
                      "Toujours avoir la main sur l'alimentation physique de la machine."))
        info.setProperty("class", "avertissement")
        layout.addWidget(info)

        layout.addStretch()
        return widget

    # -------------------------------------------------------------------------
    # ONGLET 3bis : Calibration (test rapide + mini-matrice)
    # -------------------------------------------------------------------------

    def construire_onglet_calibration(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Test rapide : gravure d'un carre de test ------------------------
        groupe_test_rapide = QGroupBox(self.tr("Test rapide (carre)"))
        ligne_test = QHBoxLayout(groupe_test_rapide)

        ligne_test.addWidget(QLabel(self.tr("Taille (mm) :")))
        self.spin_test_taille = QDoubleSpinBox()
        self.spin_test_taille.setRange(1.0, 200.0)
        self.spin_test_taille.setDecimals(1)
        self.spin_test_taille.setSingleStep(1.0)
        self.spin_test_taille.setValue(10.0)
        self.spin_test_taille.setMinimumWidth(80)
        ligne_test.addWidget(self.spin_test_taille)

        ligne_test.addSpacing(15)
        ligne_test.addWidget(QLabel(self.tr("Puissance :")))
        self.spin_test_puissance = QDoubleSpinBox()
        self.spin_test_puissance.setRange(0.1, 100.0)
        self.spin_test_puissance.setDecimals(1)
        self.spin_test_puissance.setSingleStep(1.0)
        self.spin_test_puissance.setValue(10.0)
        self.spin_test_puissance.setSuffix(" %")
        self.spin_test_puissance.setMinimumWidth(80)
        ligne_test.addWidget(self.spin_test_puissance)

        ligne_test.addSpacing(15)
        ligne_test.addWidget(QLabel(self.tr("Vitesse (mm/min) :")))
        self.spin_test_vitesse = QDoubleSpinBox()
        self.spin_test_vitesse.setRange(1.0, 5000.0)
        self.spin_test_vitesse.setDecimals(0)
        self.spin_test_vitesse.setSingleStep(50.0)
        self.spin_test_vitesse.setValue(500.0)
        self.spin_test_vitesse.setMinimumWidth(90)
        ligne_test.addWidget(self.spin_test_vitesse)

        ligne_test.addSpacing(15)
        ligne_test.addWidget(QLabel(self.tr("Passes :")))
        self.spin_test_passes = QSpinBox()
        self.spin_test_passes.setRange(1, 20)
        self.spin_test_passes.setValue(1)
        self.spin_test_passes.setMinimumWidth(60)
        ligne_test.addWidget(self.spin_test_passes)

        ligne_test.addSpacing(15)
        self.btn_test_rapide = QPushButton(self.tr("Graver le carre"))
        self.btn_test_rapide.setToolTip(
            self.tr("Grave un carré de test à la position actuelle"
            " (avec les paramètres taille/puissance/vitesse/passes)")
        )
        self.btn_test_rapide.setMinimumHeight(40)
        self.btn_test_rapide.setStyleSheet(
            "background-color: #2980b9; color: white; font-weight: bold;"
        )
        self.btn_test_rapide.clicked.connect(self.graver_carre_test)
        ligne_test.addWidget(self.btn_test_rapide)

        ligne_test.addStretch()
        layout.addWidget(groupe_test_rapide)

        # --- Mini-matrice : grille de tests P x V ---------------------------
        groupe_matrice = QGroupBox(self.tr("Mini-matrice (P x V)"))
        layout_matrice = QVBoxLayout(groupe_matrice)

        # --- Ligne 1 : dimensions de la grille ---
        ligne_m1 = QHBoxLayout()
        ligne_m1.addWidget(QLabel(self.tr("Colonnes (P) :")))
        self.spin_matrice_cols = QSpinBox()
        self.spin_matrice_cols.setRange(2, 10)
        self.spin_matrice_cols.setValue(5)
        self.spin_matrice_cols.setMinimumWidth(50)
        ligne_m1.addWidget(self.spin_matrice_cols)

        ligne_m1.addSpacing(10)
        ligne_m1.addWidget(QLabel(self.tr("Lignes (V) :")))
        self.spin_matrice_rows = QSpinBox()
        self.spin_matrice_rows.setRange(2, 10)
        self.spin_matrice_rows.setValue(5)
        self.spin_matrice_rows.setMinimumWidth(50)
        ligne_m1.addWidget(self.spin_matrice_rows)

        ligne_m1.addSpacing(20)
        ligne_m1.addWidget(QLabel(self.tr("Taille case (mm) :")))
        self.spin_matrice_taille = QDoubleSpinBox()
        self.spin_matrice_taille.setRange(1.0, 50.0)
        self.spin_matrice_taille.setDecimals(1)
        self.spin_matrice_taille.setValue(5.0)
        self.spin_matrice_taille.setMinimumWidth(70)
        ligne_m1.addWidget(self.spin_matrice_taille)

        ligne_m1.addSpacing(10)
        ligne_m1.addWidget(QLabel(self.tr("Espacement (mm) :")))
        self.spin_matrice_espace = QDoubleSpinBox()
        self.spin_matrice_espace.setRange(0.0, 20.0)
        self.spin_matrice_espace.setDecimals(1)
        self.spin_matrice_espace.setValue(2.0)
        self.spin_matrice_espace.setMinimumWidth(70)
        ligne_m1.addWidget(self.spin_matrice_espace)

        ligne_m1.addStretch()
        layout_matrice.addLayout(ligne_m1)

        # --- Ligne 2 : plages P et V ---
        ligne_m2 = QHBoxLayout()
        ligne_m2.addWidget(QLabel("Puissance min (%):"))
        self.spin_matrice_p_min = QDoubleSpinBox()
        self.spin_matrice_p_min.setRange(0.1, 100.0)
        self.spin_matrice_p_min.setDecimals(1)
        self.spin_matrice_p_min.setValue(20.0)
        self.spin_matrice_p_min.setMinimumWidth(70)
        ligne_m2.addWidget(self.spin_matrice_p_min)

        ligne_m2.addWidget(QLabel("max (%):"))
        self.spin_matrice_p_max = QDoubleSpinBox()
        self.spin_matrice_p_max.setRange(0.1, 100.0)
        self.spin_matrice_p_max.setDecimals(1)
        self.spin_matrice_p_max.setValue(100.0)
        self.spin_matrice_p_max.setMinimumWidth(70)
        ligne_m2.addWidget(self.spin_matrice_p_max)

        ligne_m2.addSpacing(20)
        ligne_m2.addWidget(QLabel("Vitesse min (mm/min):"))
        self.spin_matrice_v_min = QDoubleSpinBox()
        self.spin_matrice_v_min.setRange(1.0, 5000.0)
        self.spin_matrice_v_min.setDecimals(0)
        self.spin_matrice_v_min.setValue(100.0)
        self.spin_matrice_v_min.setMinimumWidth(80)
        ligne_m2.addWidget(self.spin_matrice_v_min)

        ligne_m2.addWidget(QLabel("max (mm/min):"))
        self.spin_matrice_v_max = QDoubleSpinBox()
        self.spin_matrice_v_max.setRange(1.0, 5000.0)
        self.spin_matrice_v_max.setDecimals(0)
        self.spin_matrice_v_max.setValue(1000.0)
        self.spin_matrice_v_max.setMinimumWidth(80)
        ligne_m2.addWidget(self.spin_matrice_v_max)

        ligne_m2.addStretch()
        layout_matrice.addLayout(ligne_m2)

        # --- Ligne 3 : bouton graver + label temps estimé ---
        ligne_m3 = QHBoxLayout()
        self.btn_matrice_graver = QPushButton(self.tr("Graver la matrice"))
        self.btn_matrice_graver.setToolTip(
            self.tr("Grave une grille de tests P×V pour calibrer la machine")
        )
        self.btn_matrice_graver.setMinimumHeight(40)
        self.btn_matrice_graver.setStyleSheet(
            "background-color: #8e44ad; color: white; font-weight: bold;"
        )
        self.btn_matrice_graver.clicked.connect(self.graver_matrice)
        ligne_m3.addWidget(self.btn_matrice_graver)

        ligne_m3.addSpacing(15)
        self.label_matrice_estime = QLabel("")
        self.label_matrice_estime.setStyleSheet(
            "font-family: Consolas, monospace; color: #555; padding: 4px;"
        )
        ligne_m3.addWidget(self.label_matrice_estime)

        ligne_m3.addStretch()
        layout_matrice.addLayout(ligne_m3)

        # --- Mise à jour live du label d'estimation ---
        self.spin_matrice_cols.valueChanged.connect(self._maj_estimation_matrice)
        self.spin_matrice_rows.valueChanged.connect(self._maj_estimation_matrice)
        self.spin_matrice_taille.valueChanged.connect(self._maj_estimation_matrice)
        self.spin_matrice_espace.valueChanged.connect(self._maj_estimation_matrice)
        self.spin_matrice_p_min.valueChanged.connect(self._maj_estimation_matrice)
        self.spin_matrice_p_max.valueChanged.connect(self._maj_estimation_matrice)
        self.spin_matrice_v_min.valueChanged.connect(self._maj_estimation_matrice)
        self.spin_matrice_v_max.valueChanged.connect(self._maj_estimation_matrice)
        self._maj_estimation_matrice()

        layout.addWidget(groupe_matrice)

        info = QLabel(self.tr("⚠️  STOP = Ctrl-X GRBL (arrêt immédiat). "
                      "Toujours avoir la main sur l'alimentation physique de la machine."))
        info.setProperty("class", "avertissement")
        layout.addWidget(info)

        layout.addStretch()
        return widget

    # -------------------------------------------------------------------------
    # ONGLET 4 : Fichier
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # ONGLET 3ter : Photo (dithering)
    # -------------------------------------------------------------------------

    def construire_onglet_photo(self):
        """Onglet de gravure photo (dithering Floyd-Steinberg)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Groupe Source ---
        groupe_source = QGroupBox(self.tr("Image source"))
        layout_source = QVBoxLayout(groupe_source)

        ligne_fichier = QHBoxLayout()
        self.btn_photo_charger = QPushButton(self.tr("Charger une image..."))
        self.btn_photo_charger.setToolTip(self.tr("Charger une image pour la gravure photo"))
        self.btn_photo_charger.setMinimumHeight(36)
        self.btn_photo_charger.clicked.connect(self.charger_image_photo)
        ligne_fichier.addWidget(self.btn_photo_charger)

        self.label_photo_fichier = QLabel(self.tr("Aucune image chargée"))
        self.label_photo_fichier.setStyleSheet(
            "font-family: Consolas, monospace; padding: 4px;"
        )
        ligne_fichier.addWidget(self.label_photo_fichier, stretch=1)

        layout_source.addLayout(ligne_fichier)

        self.label_photo_apercu = QLabel("")
        self.label_photo_apercu.setFixedHeight(120)
        self.label_photo_apercu.setProperty("class", "zone_apercu")
        self.label_photo_apercu.setAlignment(Qt.AlignCenter)
        layout_source.addWidget(self.label_photo_apercu)

        layout.addWidget(groupe_source)

        # --- Groupe Parametres ---
        groupe_params = QGroupBox(self.tr("Paramètres de gravure"))
        form_params = QFormLayout(groupe_params)

        self.spin_photo_largeur = QDoubleSpinBox()
        self.spin_photo_largeur.setRange(1.0, 5000.0)
        self.spin_photo_largeur.setDecimals(1)
        self.spin_photo_largeur.setSingleStep(10.0)
        self.spin_photo_largeur.setValue(100.0)
        self.spin_photo_largeur.setSuffix(" mm")
        form_params.addRow(self.tr("Largeur cible :"), self.spin_photo_largeur)

        self.spin_photo_resolution = QDoubleSpinBox()
        self.spin_photo_resolution.setRange(0.05, 1.0)
        self.spin_photo_resolution.setDecimals(2)
        self.spin_photo_resolution.setSingleStep(0.05)
        self.spin_photo_resolution.setValue(0.10)
        self.spin_photo_resolution.setSuffix(" mm/px")
        form_params.addRow(self.tr("Résolution :"), self.spin_photo_resolution)

        self.spin_photo_vitesse = QDoubleSpinBox()
        self.spin_photo_vitesse.setRange(100.0, 5000.0)
        self.spin_photo_vitesse.setDecimals(0)
        self.spin_photo_vitesse.setSingleStep(100.0)
        self.spin_photo_vitesse.setValue(1500.0)
        self.spin_photo_vitesse.setSuffix(" mm/min")
        form_params.addRow(self.tr("Vitesse :"), self.spin_photo_vitesse)

        self.spin_photo_puissance = QDoubleSpinBox()
        self.spin_photo_puissance.setRange(1.0, 100.0)
        self.spin_photo_puissance.setDecimals(1)
        self.spin_photo_puissance.setSingleStep(5.0)
        self.spin_photo_puissance.setValue(100.0)
        self.spin_photo_puissance.setSuffix(" %")
        form_params.addRow(self.tr("Puissance max :"), self.spin_photo_puissance)

        self.check_photo_inverser = QCheckBox(self.tr("Inverser noir/blanc"))
        form_params.addRow(self.check_photo_inverser)

        # --- Nouveau : Menu algorithme de dithering ---
        self.combo_photo_algo = QComboBox()
        self.combo_photo_algo.addItem(self.tr("Floyd-Steinberg"), "floyd")
        self.combo_photo_algo.addItem(self.tr("Jarvis"), "jarvis")
        self.combo_photo_algo.addItem(self.tr("Stucki"), "stucki")
        self.combo_photo_algo.addItem(self.tr("Atkinson"), "atkinson")
        self.combo_photo_algo.addItem(self.tr("Bayer"), "bayer")
        form_params.addRow(self.tr("Algorithme :"), self.combo_photo_algo)
        
        self.check_detourage = QCheckBox(self.tr("Détourage automatique"))
        self.check_detourage.setToolTip(self.tr("Ne garder que les plus grands contours (supprime le fond)"))
        form_params.addRow(self.check_detourage)
        
        self.spin_seuil_detourage = QDoubleSpinBox()
        self.spin_seuil_detourage.setRange(1.0, 50.0)
        self.spin_seuil_detourage.setValue(5.0)
        self.spin_seuil_detourage.setSuffix(" %")
        self.spin_seuil_detourage.setEnabled(False)
        form_params.addRow(self.tr("Seuil de surface :"), self.spin_seuil_detourage)
        
        self.check_detourage.toggled.connect(self.spin_seuil_detourage.setEnabled)

        layout.addWidget(groupe_params)

        # --- Groupe Estimation / Actions ---
        groupe_actions = QGroupBox(self.tr("Actions"))
        layout_actions = QVBoxLayout(groupe_actions)

        self.label_photo_estimation = QLabel("")
        self.label_photo_estimation.setStyleSheet(
            "font-family: Consolas, monospace; color: #555; padding: 4px;"
        )
        layout_actions.addWidget(self.label_photo_estimation)

        ligne_boutons = QHBoxLayout()
        self.btn_photo_generer = QPushButton(self.tr("Générer le G-code..."))
        self.btn_photo_generer.setToolTip(self.tr("Générer le G-code à partir de l'image chargée"))
        self.btn_photo_generer.setMinimumHeight(40)
        self.btn_photo_generer.setProperty("class", "action")
        self.btn_photo_generer.clicked.connect(self.generer_gcode_photo)
        ligne_boutons.addWidget(self.btn_photo_generer)

        self.btn_photo_envoyer = QPushButton(self.tr("▶  Envoyer à la machine"))
        self.btn_photo_envoyer.setToolTip(self.tr("Envoyer le G-code généré à la machine"))
        self.btn_photo_envoyer.setMinimumHeight(40)
        self.btn_photo_envoyer.setProperty("class", "action")
        self.btn_photo_envoyer.setEnabled(False)
        self.btn_photo_envoyer.clicked.connect(self.envoyer_gcode_photo)
        ligne_boutons.addWidget(self.btn_photo_envoyer)

        layout_actions.addLayout(ligne_boutons)

        layout.addWidget(groupe_actions)

        # Connexions pour mise à jour de l'estimation
        self.spin_photo_largeur.valueChanged.connect(self._maj_estimation_photo)
        self.spin_photo_resolution.valueChanged.connect(self._maj_estimation_photo)
        self.spin_photo_vitesse.valueChanged.connect(self._maj_estimation_photo)

        info = QLabel(self.tr(
            "⚠️  Gravure photo = temps de travail TRÈS LONG (plusieurs heures). "
            "Vérifier l'estimation avant de lancer."
        ))
        info.setProperty("class", "avertissement")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        return widget

    def charger_image_photo(self):
        """Charge une image pour la gravure photo."""
        from PySide6.QtGui import QPixmap
        
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp);;Tous les fichiers (*.*)"
        )
        if not chemin:
            return

        self.photo_chemin = chemin
        self.photo_lignes_gcode = None
        self.btn_photo_envoyer.setEnabled(False)

        nom = os.path.basename(chemin)
        self.label_photo_fichier.setText(nom)

        # Miniature
        pixmap = QPixmap(chemin)
        if not pixmap.isNull():
            pixmap = pixmap.scaledToHeight(
                110, Qt.SmoothTransformation
            )
            self.label_photo_apercu.setPixmap(pixmap)
        else:
            self.label_photo_apercu.setText("(aperçu indisponible)")

        self._maj_estimation_photo()
        self.afficher_console(f"— Photo chargée : {chemin} —")

    def _maj_estimation_photo(self):
        """Met à jour l'estimation du temps de gravure photo."""
        if self.photo_chemin is None:
            self.label_photo_estimation.setText("")
            return

        try:
            from PIL import Image
            from src.core.dithering_loader import estimer_temps_photo
            
            img = Image.open(self.photo_chemin)
            ratio = img.height / img.width
            
            largeur_mm = self.spin_photo_largeur.value()
            resolution = self.spin_photo_resolution.value()
            vitesse = self.spin_photo_vitesse.value()
            
            hauteur_mm = largeur_mm * ratio
            
            nb_lignes = int(hauteur_mm / resolution)
            temps_aller_s = (largeur_mm / vitesse) * 60.0
            temps_total_s = nb_lignes * (temps_aller_s + 0.05)
            
            # Format
            if temps_total_s < 60:
                txt = f"{temps_total_s:.0f} s"
            elif temps_total_s < 3600:
                m = int(temps_total_s // 60)
                s = int(temps_total_s % 60)
                txt = f"{m} min {s:02d} s"
            else:
                h = int(temps_total_s // 3600)
                m = int((temps_total_s % 3600) // 60)
                txt = f"{h} h {m:02d} min"
            
            self.label_photo_estimation.setText(
                f"Dimensions : {largeur_mm:.0f} × {hauteur_mm:.1f} mm  |  "
                f"Temps estimé : ~{txt}"
            )
        except Exception as e:
            self.label_photo_estimation.setText(f"(estimation indisponible : {e})")

    def generer_gcode_photo(self):
        """Génère le G-code de dithering et le sauvegarde."""
        if self.photo_chemin is None:
            QMessageBox.warning(self, "Aucune image",
                                "Charge une image avant de générer.")
            return

        # Récupérer S_MAX depuis GRBL si connecté
        s_max = 1000
        if self.grbl.est_connecte:
            self._suspendre_statut()
            try:
                reponses = self.grbl.envoyer("$$", timeout=2.0)
                for r in reponses:
                    if r.startswith("$30="):
                        s_max = int(r.split("=")[1])
                        break
            except Exception:
                pass
            self._reprendre_statut()

        puissance_pct = self.spin_photo_puissance.value()
        puissance_max = int(round(puissance_pct / 100.0 * s_max))

        try:
            from src.core.dithering_loader import generer_gcode_photo as gen_photo
            
            QApplication.setOverrideCursor(Qt.WaitCursor)
            lignes, warnings = gen_photo(
                self.photo_chemin,
                largeur_mm=self.spin_photo_largeur.value(),
                resolution_mm=self.spin_photo_resolution.value(),
                vitesse=self.spin_photo_vitesse.value(),
                puissance_max=puissance_max,
                puissance_min=0,
                inverser=self.check_photo_inverser.isChecked(),
                algo=self.combo_photo_algo.currentData(),
            )
            QApplication.restoreOverrideCursor()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Erreur de génération",
                                 f"Impossible de générer le G-code :\n{e}")
            return

        self.photo_lignes_gcode = lignes

        # Demander où sauvegarder
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le G-code sous...",
            "photo.nc",
            "Fichiers G-code (*.nc *.gcode *.txt);;Tous les fichiers (*.*)"
        )
        if not chemin:
            return

        try:
            with open(chemin, "w", encoding="utf-8") as f:
                f.write("\n".join(lignes))
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'écriture",
                                 f"Impossible d'écrire :\n{e}")
            return

        QMessageBox.information(
            self, "G-code généré",
            f"Fichier : {chemin}\n\n"
            f"{len(lignes)} lignes écrites.\n\n" +
            "\n".join(warnings)
        )

        self.afficher_console(f"— G-code photo généré : {chemin} ({len(lignes)} lignes) —")

        # Active le bouton d'envoi
        self.btn_photo_envoyer.setEnabled(True)
        
        # Propose d'envoyer directement
        rep = QMessageBox.question(
            self, "Envoyer à la machine ?",
            "Le G-code a été sauvegardé.\n\n"
            "Veux-tu l'envoyer maintenant à la machine ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if rep == QMessageBox.Yes:
            self._envoyer_lignes_photo(lignes)

    def envoyer_gcode_photo(self):
        """Envoie le G-code photo déjà généré."""
        if self.photo_lignes_gcode is None:
            QMessageBox.warning(self, "Aucun G-code",
                                "Génère le G-code d'abord.")
            return
        self._envoyer_lignes_photo(self.photo_lignes_gcode)

    def _envoyer_lignes_photo(self, lignes):
        """Envoie une liste de lignes G-code à la machine (threadé)."""
        if not self.grbl.est_connecte:
            QMessageBox.warning(self, "Non connecté",
                                "Connecte la machine avant d'envoyer.")
            return
        if self.thread_envoi is not None and self.thread_envoi.isRunning():
            QMessageBox.information(self, "Envoi en cours",
                                    "Un envoi est déjà en cours.")
            return

        total = len(lignes)
        
        reponse = QMessageBox.question(
            self,
            "Confirmer l'envoi",
            f"Envoyer {total} lignes de G-code à la machine ?\n\n"
            f"Rappels :\n"
            f"  • l'origine doit être définie\n"
            f"  • la trajectoire doit être libre\n"
            f"  • ayez la main sur l'alimentation physique",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reponse != QMessageBox.Yes:
            return

        self.est_en_pause = False
        self.btn_pause.setText("⏸  PAUSE")
        self._reset_overrides()
        self.mettre_interface_en_envoi(True)
        
        self.label_progression.setText(f"Envoi : 0 / {total}")
        self.label_temps_restant.setText("Estimation…")
        self.temps_debut_envoi = time.time()
        self.temps_ecoule_avant_pause = 0.0
        self.temps_pause_debut = None
        self.mesures_temps_restant = []
        
        self.thread_envoi = EnvoiGcodeThread(self.grbl, lignes)
        self.thread_envoi.ligne_envoyee.connect(self.on_envoi_ligne)
        self.thread_envoi.termine.connect(self.on_envoi_termine)
        self.thread_envoi.start()

    def construire_onglet_fichier(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        groupe_haut = QGroupBox(self.tr("Fichier G-code"))
        ligne_haut = QHBoxLayout(groupe_haut)

        self.btn_charger = QPushButton(self.tr("Charger un fichier…"))
        self.btn_charger.setToolTip(self.tr("Charger un fichier G-code"))
        self.btn_charger.setMinimumHeight(40)
        self.btn_charger.clicked.connect(self.charger_fichier)
        ligne_haut.addWidget(self.btn_charger)

        ligne_haut.addSpacing(20)
        self.label_fichier = QLabel(self.tr("Aucun fichier chargé"))
        self.label_fichier.setStyleSheet("font-family: Consolas, monospace; padding: 4px;")
        ligne_haut.addWidget(self.label_fichier)

        ligne_haut.addSpacing(20)
        self.label_temps_fichier = QLabel("")
        self.label_temps_fichier.setStyleSheet(
            "font-family: Consolas, monospace; padding: 4px; color: #555;"
        )
        ligne_haut.addWidget(self.label_temps_fichier)

        ligne_haut.addStretch()
        layout.addWidget(groupe_haut)

        self.apercu_gcode = QPlainTextEdit()
        self.apercu_gcode.setReadOnly(True)
        self.apercu_gcode.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        layout.addWidget(self.apercu_gcode)

        groupe_bas = QGroupBox(self.tr("Envoi à la machine"))
        ligne_bas = QHBoxLayout(groupe_bas)

        self.btn_envoyer_fichier = QPushButton(self.tr("▶  ENVOYER À LA MACHINE"))
        self.btn_envoyer_fichier.setToolTip(self.tr("Envoyer le fichier G-code à la machine"))
        self.btn_envoyer_fichier.setMinimumHeight(50)
        self.btn_envoyer_fichier.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; font-size: 14px;"
        )
        self.btn_envoyer_fichier.clicked.connect(self.envoyer_fichier)
        ligne_bas.addWidget(self.btn_envoyer_fichier)

        self.btn_pause = QPushButton(self.tr("⏸  PAUSE"))
        self.btn_pause.setToolTip(self.tr("Mettre en pause ou reprendre l'envoi"))
        self.btn_pause.setMinimumHeight(50)
        self.btn_pause.setStyleSheet(
            "background-color: #e67e22; color: white; font-weight: bold; font-size: 14px;"
        )
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.basculer_pause)
        ligne_bas.addWidget(self.btn_pause)

        self.label_progression = QLabel(self.tr("En attente"))
        self.label_progression.setStyleSheet("font-family: Consolas, monospace; padding: 4px 12px;")
        ligne_bas.addWidget(self.label_progression)

        # Label "Temps restant" (compte a rebours pendant l'envoi)
        self.label_temps_restant = QLabel("")
        self.label_temps_restant.setStyleSheet(
            "font-family: Consolas, monospace; padding: 4px 12px; "
            "color: #2980b9; font-weight: bold;"
        )
        ligne_bas.addWidget(self.label_temps_restant)

        ligne_bas.addStretch()

        # --- Overrides temps reel (vitesse + puissance) ---
        ligne_override = QHBoxLayout()

        ligne_override.addWidget(QLabel(self.tr("Vitesse :")))
        self.btn_vitesse_moins = QPushButton("◀")
        self.btn_vitesse_moins.setMinimumSize(40, 32)
        self.btn_vitesse_moins.setToolTip("Reduire la vitesse de 10 %")
        self.btn_vitesse_moins.clicked.connect(self._override_vitesse_moins)
        ligne_override.addWidget(self.btn_vitesse_moins)

        self.label_override_vitesse = QLabel("100 %")
        self.label_override_vitesse.setAlignment(Qt.AlignCenter)
        self.label_override_vitesse.setMinimumWidth(60)
        self.label_override_vitesse.setStyleSheet(
            "font-family: Consolas, monospace; font-weight: bold;"
        )
        ligne_override.addWidget(self.label_override_vitesse)

        self.btn_vitesse_plus = QPushButton("▶")
        self.btn_vitesse_plus.setMinimumSize(40, 32)
        self.btn_vitesse_plus.setToolTip("Augmenter la vitesse de 10 %")
        self.btn_vitesse_plus.clicked.connect(self._override_vitesse_plus)
        ligne_override.addWidget(self.btn_vitesse_plus)

        ligne_override.addSpacing(30)

        ligne_override.addWidget(QLabel(self.tr("Puissance :")))
        self.btn_puissance_moins = QPushButton("◀")
        self.btn_puissance_moins.setMinimumSize(40, 32)
        self.btn_puissance_moins.setToolTip("Reduire la puissance de 10 %")
        self.btn_puissance_moins.clicked.connect(self._override_puissance_moins)
        ligne_override.addWidget(self.btn_puissance_moins)

        self.label_override_puissance = QLabel("100 %")
        self.label_override_puissance.setAlignment(Qt.AlignCenter)
        self.label_override_puissance.setMinimumWidth(60)
        self.label_override_puissance.setStyleSheet(
            "font-family: Consolas, monospace; font-weight: bold;"
        )
        ligne_override.addWidget(self.label_override_puissance)

        self.btn_puissance_plus = QPushButton("▶")
        self.btn_puissance_plus.setMinimumSize(40, 32)
        self.btn_puissance_plus.setToolTip("Augmenter la puissance de 10 %")
        self.btn_puissance_plus.clicked.connect(self._override_puissance_plus)
        ligne_override.addWidget(self.btn_puissance_plus)

        ligne_override.addStretch()
        ligne_bas.addLayout(ligne_override)

        # NOTE : les valeurs d'override ne sont plus stockees en local.
        # Elles sont lues dans "Ov:" du rapport GRBL (voir on_statut_recu).

        layout.addWidget(groupe_bas)

        avert = QLabel(self.tr("⚠️  Avant d'envoyer : s'assurer que l'origine est définie, "
                       "que la trajectoire est libre, et avoir la main sur l'alimentation."))
        avert.setProperty("class", "avertissement")
        layout.addWidget(avert)

        return widget

    # -------------------------------------------------------------------------
    # ONGLET 5 : Aperçu (parcours + suivi temps réel)
    # -------------------------------------------------------------------------

    def construire_onglet_apercu(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.apercu = ApercuWidget()
        layout.addWidget(self.apercu)

        note = QLabel(self.tr("Astuce : molette = zoom • clic-glisser = déplacer la vue • "
                      "« Recentrer » recadre sur le parcours"))
        note.setStyleSheet("color: #888; padding: 4px 8px; font-size: 11px;")
        layout.addWidget(note)

        return widget

    # -------------------------------------------------------------------------
    # ONGLET 6 : Mise en page (étape 1 : affichage DXF)
    # -------------------------------------------------------------------------

    def construire_onglet_mise_en_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.mise_en_page = MiseEnPageWidget()
        self.mise_en_page.widget_parent = self
        
        # Application des couleurs de scène au démarrage
        theme_init, _, _, teinte_init = charger_preferences()
        couleurs_init = obtenir_couleurs_scene(theme_init, teinte_init)
        self.mise_en_page.changer_couleurs_scene(couleurs_init["fond"], couleurs_init["zone"])
        layout.addWidget(self.mise_en_page)

        return widget

    # -------------------------------------------------------------------------
    # ONGLET 7 : Parametres (sauvegarde / chargement / raccourcis)
    # -------------------------------------------------------------------------

    def construire_onglet_parametres(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- Section Projet ---
        groupe_projet = QGroupBox(self.tr("Projet"))
        layout_projet = QVBoxLayout(groupe_projet)

        self.label_chemin_projet = QLabel(self.tr("Projet non sauvegardé"))
        self.label_chemin_projet.setStyleSheet(
            "font-family: Consolas, monospace; padding: 4px; "
            "color: #333; font-weight: bold;"
        )
        layout_projet.addWidget(self.label_chemin_projet)

        ligne_btn_projet = QHBoxLayout()

        self.btn_sauvegarder = QPushButton(self.tr("Sauvegarder"))
        self.btn_sauvegarder.setToolTip(self.tr("Sauvegarder le projet actuel"))
        self.btn_sauvegarder.setMinimumHeight(36)
        self.btn_sauvegarder.clicked.connect(self.sauvegarder_projet_action)
        ligne_btn_projet.addWidget(self.btn_sauvegarder)

        self.btn_sauvegarder_sous = QPushButton(self.tr("Sauvegarder sous..."))
        self.btn_sauvegarder_sous.setToolTip(self.tr("Sauvegarder le projet sous un nouveau nom"))
        self.btn_sauvegarder_sous.setMinimumHeight(36)
        self.btn_sauvegarder_sous.clicked.connect(self.sauvegarder_sous_action)
        ligne_btn_projet.addWidget(self.btn_sauvegarder_sous)

        self.btn_charger_projet = QPushButton(self.tr("Charger un projet..."))
        self.btn_charger_projet.setToolTip(self.tr("Charger un projet Nala existant"))
        self.btn_charger_projet.setMinimumHeight(36)
        self.btn_charger_projet.clicked.connect(self.charger_projet_action)
        ligne_btn_projet.addWidget(self.btn_charger_projet)

        layout_projet.addLayout(ligne_btn_projet)
        layout.addWidget(groupe_projet)

        # --- Section Fichiers recents ---
        groupe_recents = QGroupBox(self.tr("Fichiers récents"))
        layout_recents = QVBoxLayout(groupe_recents)

        self.liste_recents = QListWidget()
        self.liste_recents.setMinimumHeight(100)
        self.liste_recents.setMaximumHeight(180)
        self.liste_recents.itemDoubleClicked.connect(
            self._on_recent_double_clic
        )
        layout_recents.addWidget(self.liste_recents)

        ligne_btn_recents = QHBoxLayout()
        self.btn_effacer_recents = QPushButton(self.tr("Effacer la liste"))
        self.btn_effacer_recents.setToolTip(self.tr("Effacer la liste des fichiers récents"))
        self.btn_effacer_recents.clicked.connect(self._effacer_recents)
        ligne_btn_recents.addWidget(self.btn_effacer_recents)
        ligne_btn_recents.addStretch()
        layout_recents.addLayout(ligne_btn_recents)

        layout.addWidget(groupe_recents)

        # --- Section Raccourcis clavier ---
        groupe_raccourcis = QGroupBox(self.tr("Raccourcis clavier"))
        layout_raccourcis = QVBoxLayout(groupe_raccourcis)

        liste_raccourcis = QListWidget()
        raccourcis = [
            self.tr("Ctrl+D           : Dupliquer la sélection (+10 mm)"),
            self.tr("Suppr / Backspace: Supprimer la sélection"),
            self.tr("Tab              : Entité suivante"),
            self.tr("Shift+Tab        : Entité précédente"),
            self.tr("Échap            : Quitter le mode mesure / annuler saisie"),
            self.tr("Ctrl+clic        : Ajouter/retirer une entité à la sélection"),
            self.tr("Shift+clic       : Idem Ctrl+clic"),
            self.tr("Clic-glisser     : Rectangle de sélection"),
            self.tr("Molette          : Zoom centré sur le curseur"),
            self.tr("Molette cliquée  : Déplacer la vue (pan)"),
            self.tr("Espace + glisser : Déplacer la vue (pan)"),
            self.tr("Flèches          : Déplacer la sélection de 1 pas"),
            self.tr("Shift + Flèches  : Déplacer la sélection de 10 pas"),
            self.tr("Tab (trace)      : Saisir les cotes au clavier"),
        ]
        for r in raccourcis:
            liste_raccourcis.addItem(r)
        layout_raccourcis.addWidget(liste_raccourcis)

        layout.addWidget(groupe_raccourcis)

        # --- Section Apparence ---
        groupe_apparence = QGroupBox(self.tr("Apparence"))
        layout_apparence = QVBoxLayout(groupe_apparence)

        ligne_theme = QHBoxLayout()
        ligne_theme.addWidget(QLabel(self.tr("Thème :")))
        self.combo_theme = QComboBox()
        for cle, infos in THEMES.items():
            self.combo_theme.addItem(infos["nom"], cle)
        self.combo_theme.currentIndexChanged.connect(self._appliquer_theme_depuis_ui)
        ligne_theme.addWidget(self.combo_theme)

        ligne_theme.addSpacing(20)
        ligne_theme.addWidget(QLabel(self.tr("Couleur d'accent :")))
        self.combo_accent = QComboBox()
        for cle, infos in ACCENTS.items():
            self.combo_accent.addItem(infos["nom"], cle)
        self.combo_accent.currentIndexChanged.connect(self._appliquer_theme_depuis_ui)
        ligne_theme.addWidget(self.combo_accent)

        ligne_theme.addSpacing(20)
        ligne_theme.addWidget(QLabel(self.tr("Contraste :")))
        self.combo_contraste = QComboBox()
        for cle, infos in CONTRASTES.items():
            self.combo_contraste.addItem(infos["nom"], cle)
        self.combo_contraste.currentIndexChanged.connect(self._appliquer_theme_depuis_ui)
        ligne_theme.addWidget(self.combo_contraste)

        ligne_theme.addSpacing(20)
        ligne_theme.addWidget(QLabel(self.tr("Teinte de fond :")))
        self.combo_teinte = QComboBox()
        for cle, infos in TEINTES_FOND.items():
            self.combo_teinte.addItem(infos["nom"], cle)
        self.combo_teinte.currentIndexChanged.connect(self._appliquer_theme_depuis_ui)
        self.combo_teinte.setEnabled(False) # Désactivé par défaut (seulement pour Coloré)
        ligne_theme.addWidget(self.combo_teinte)

        ligne_theme.addStretch()
        layout_apparence.addLayout(ligne_theme)

        note_apparence = QLabel(self.tr(
            "Le thème s'applique immédiatement et est sauvegardé pour "
            "les prochaines sessions."
        ))
        note_apparence.setStyleSheet("color: #888; font-style: italic; padding: 4px;")
        note_apparence.setWordWrap(True)
        layout_apparence.addWidget(note_apparence)

        layout.addWidget(groupe_apparence)

        # --- Section Langue ---
        groupe_langue = QGroupBox(self.tr("Langue / Language"))
        layout_langue = QVBoxLayout(groupe_langue)

        ligne_langue = QHBoxLayout()
        ligne_langue.addWidget(QLabel(self.tr("Langue :")))
        self.combo_langue = QComboBox()
        self.combo_langue.addItem("Français", "fr")
        self.combo_langue.addItem("English", "en")
        self.combo_langue.currentIndexChanged.connect(self._changer_langue)
        ligne_langue.addWidget(self.combo_langue)
        ligne_langue.addStretch()
        layout_langue.addLayout(ligne_langue)

        note_langue = QLabel(self.tr(
            "Le changement de langue nécessite un redémarrage de l'application."
        ))
        note_langue.setStyleSheet("color: #888; font-style: italic; padding: 4px;")
        note_langue.setWordWrap(True)
        layout_langue.addWidget(note_langue)

        layout.addWidget(groupe_langue)

        layout.addStretch()

        # Charger les recents au demarrage
        QTimer.singleShot(100, self._rafraichir_recents)
        # Charger le theme courant au demarrage
        QTimer.singleShot(150, self._rafraichir_combos_theme)
        QTimer.singleShot(160, self._rafraichir_combo_langue)

        return widget

    # -------------------------------------------------------------------------
    # Actions : sauvegarde / chargement de projet
    # -------------------------------------------------------------------------

    def _ajouter_extension_nala(self, chemin):
        """Force l'extension .nala si absente."""
        if not chemin.lower().endswith(".nala"):
            chemin += ".nala"
        return chemin

    def _maj_label_chemin_projet(self):
        """Met a jour le label affichant le chemin du projet actuel."""
        if self.chemin_projet_actuel:
            self.label_chemin_projet.setText(
                f"Projet : {self.chemin_projet_actuel}"
            )
        else:
            self.label_chemin_projet.setText("Projet non sauvegardé")

    def _faire_sauvegarde(self, chemin):
        """Effectue la sauvegarde. Retourne True si succes."""
        try:
            projet = self.mise_en_page.recuperer_projet()
            module_sauvegarde.sauvegarder_projet(chemin, projet)
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur de sauvegarde",
                f"Impossible de sauvegarder :\n{e}"
            )
            return False

        self.chemin_projet_actuel = chemin
        self._maj_label_chemin_projet()
        module_sauvegarde.ajouter_fichier_recent(chemin)
        self._rafraichir_recents()
        self.afficher_console(f"— Projet sauvegardé : {chemin} —")
        return True

    def sauvegarder_projet_action(self):
        """Sauvegarde dans le fichier courant, ou ouvre le dialogue si absent."""
        if self.chemin_projet_actuel:
            self._faire_sauvegarde(self.chemin_projet_actuel)
        else:
            self.sauvegarder_sous_action()

    def sauvegarder_sous_action(self):
        """Ouvre un dialogue pour sauvegarder sous un nouveau nom."""
        chemin, _ = QFileDialog.getSaveFileName(
            self,
            "Sauvegarder le projet sous...",
            "mon_projet.nala",
            "Fichiers projet Nala (*.nala);;Tous les fichiers (*.*)"
        )
        if not chemin:
            return
        chemin = self._ajouter_extension_nala(chemin)
        self._faire_sauvegarde(chemin)

    def charger_projet_action(self):
        """Ouvre un dialogue pour charger un projet."""
        chemin, _ = QFileDialog.getOpenFileName(
            self,
            "Charger un projet Nala",
            "",
            "Fichiers projet Nala (*.nala);;Tous les fichiers (*.*)"
        )
        if not chemin:
            return
        self._charger_projet_depuis_chemin(chemin)

    def _charger_projet_depuis_chemin(self, chemin):
        """Charge un projet depuis un chemin (avec confirmation)."""
        # Confirmation remplacement
        rep = QMessageBox.question(
            self,
            "Charger un projet",
            f"Remplacer le projet actuel par :\n\n{chemin}\n\n"
            f"Le projet actuel sera perdu s'il n'est pas sauvegardé.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if rep != QMessageBox.Yes:
            return

        try:
            projet = module_sauvegarde.charger_projet(chemin)
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur de chargement",
                f"Impossible de charger le projet :\n{e}"
            )
            return

        try:
            self.mise_en_page.charger_projet(projet)
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur",
                f"Erreur lors du chargement :\n{e}"
            )
            return

        self.chemin_projet_actuel = chemin
        self._maj_label_chemin_projet()
        module_sauvegarde.ajouter_fichier_recent(chemin)
        self._rafraichir_recents()
        self.afficher_console(f"— Projet chargé : {chemin} —")

    # -------------------------------------------------------------------------
    # Actions : fichiers recents
    # -------------------------------------------------------------------------

    def _rafraichir_combos_theme(self):
        """Cale les combo box sur les préférences sauvegardées."""
        theme, accent, contraste, teinte = charger_preferences()

        # On bloque les signaux pour ne pas déclencher _appliquer_theme_depuis_ui
        self.combo_theme.blockSignals(True)
        self.combo_accent.blockSignals(True)
        self.combo_contraste.blockSignals(True)
        self.combo_teinte.blockSignals(True)

        idx = self.combo_theme.findData(theme)
        if idx >= 0:
            self.combo_theme.setCurrentIndex(idx)

        idx = self.combo_accent.findData(accent)
        if idx >= 0:
            self.combo_accent.setCurrentIndex(idx)

        idx = self.combo_contraste.findData(contraste)
        if idx >= 0:
            self.combo_contraste.setCurrentIndex(idx)

        idx = self.combo_teinte.findData(teinte)
        if idx >= 0:
            self.combo_teinte.setCurrentIndex(idx)

        self.combo_theme.blockSignals(False)
        self.combo_accent.blockSignals(False)
        self.combo_contraste.blockSignals(False)
        self.combo_teinte.blockSignals(False)

        # Activer le combo de teinte uniquement si le thème est "Coloré"
        self.combo_teinte.setEnabled(theme == "colore")

    def _appliquer_theme_depuis_ui(self):
        """Applique le thème choisi dans les combo box et le sauvegarde."""
        theme = self.combo_theme.currentData()
        accent = self.combo_accent.currentData()
        contraste = self.combo_contraste.currentData()
        teinte = self.combo_teinte.currentData()

        if theme is None or accent is None or contraste is None or teinte is None:
            return

        # Activer/désactiver le combo de teinte selon le thème
        self.combo_teinte.setEnabled(theme == "colore")

        # Applique la QSS à la fenêtre principale
        self.setStyleSheet(obtenir_stylesheet(theme, accent, contraste, teinte))

        # Mise à jour de la scène (Mise en page)
        couleurs = obtenir_couleurs_scene(theme, teinte)
        self.mise_en_page.changer_couleurs_scene(couleurs["fond"], couleurs["zone"])

        # Sauvegarde dans QSettings
        sauvegarder_preferences(theme, accent, contraste, teinte)

        # Log dans la console
        nom_theme = THEMES.get(theme, {}).get("nom", theme)
        nom_accent = ACCENTS.get(accent, {}).get("nom", accent)
        nom_contraste = CONTRASTES.get(contraste, {}).get("nom", contraste)
        self.afficher_console(
            f"— Apparence : {nom_theme}, {nom_accent}, {nom_contraste} —"
        )

    def _changer_langue(self):
        """Sauvegarde la langue choisie et propose un redémarrage."""
        langue = self.combo_langue.currentData()
        if langue is None:
            return
        
        # Sauvegarder dans QSettings
        i18n_gestionnaire.sauvegarder_langue(langue)
        
        nom = self.tr("Français") if langue == "fr" else self.tr("English")
        self.afficher_console(f"— Langue : {nom} (redémarrage nécessaire) —")
        
        QMessageBox.information(
            self,
            self.tr("Langue changée"),
            self.tr("La langue a été changée en ") + nom + ".\n\n"
            + self.tr("Veuillez redémarrer Nala pour que la traduction prenne effet.")
        )

    def _rafraichir_combo_langue(self):
        """Cale le combo langue sur la préférence sauvegardée."""
        langue = i18n_gestionnaire.obtenir_langue()
        
        self.combo_langue.blockSignals(True)
        idx = self.combo_langue.findData(langue)
        if idx >= 0:
            self.combo_langue.setCurrentIndex(idx)
        self.combo_langue.blockSignals(False)

    def _rafraichir_recents(self):
        """Recharge la liste des fichiers recents dans le QListWidget."""
        if not hasattr(self, "liste_recents"):
            return
        self.liste_recents.clear()
        recents = module_sauvegarde.obtenir_fichiers_recents()
        if not recents:
            self.liste_recents.addItem("(aucun fichier récent)")
            self.liste_recents.setEnabled(False)
            return
        self.liste_recents.setEnabled(True)
        for chemin in recents:
            self.liste_recents.addItem(chemin)

    def _on_recent_double_clic(self, item):
        """Appele au double-clic sur un fichier recent."""
        chemin = item.text()
        if not chemin or chemin.startswith("("):
            return
        self._charger_projet_depuis_chemin(chemin)

    def _effacer_recents(self):
        """Efface la liste des fichiers recents."""
        rep = QMessageBox.question(
            self,
            "Effacer les récents",
            "Effacer la liste des fichiers récents ?\n\n"
            "(Les fichiers eux-mêmes ne sont pas supprimés.)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if rep != QMessageBox.Yes:
            return
        module_sauvegarde.nettoyer_recents()
        self._rafraichir_recents()

    # -------------------------------------------------------------------------
    # Actions : ports et connexion
    # -------------------------------------------------------------------------

    def rafraichir_ports(self):
        self.combo_ports.clear()
        for p in list_ports.comports():
            self.combo_ports.addItem(f"{p.device}  —  {p.description}", p.device)

    def basculer_connexion(self):
        if self.grbl.est_connecte:
            self._arreter_statut_thread()
            self.grbl.deconnecter()
            self.btn_connecter.setText("Connecter")
            self.label_statut.setText("Déconnecté")
            self.label_pos_x.setText("X :   ---.---")
            self.label_pos_y.setText("Y :   ---.---")
            self.label_etat.setText("État : ---")
            self.apercu.vider()
            # Desactivation du bouton Point laser
            self.btn_point_laser.setEnabled(False)
            self.afficher_console("— Déconnecté —")
        else:
            if self.combo_ports.count() == 0:
                self.label_statut.setText("Aucun port disponible.")
                return
            port = self.combo_ports.currentData()
            try:
                self.grbl.connecter(port)
            except Exception as e:
                self.label_statut.setText(f"Erreur : {e}")
                return
            self.btn_connecter.setText("Déconnecter")
            self.label_statut.setText("Connecté — en attente du statut…")
            self.afficher_console(f"— Connecté sur {port} —")
            self._demarrer_statut_thread()
            # Activation du bouton "Point laser"
            self.btn_point_laser.setEnabled(True)

    # -------------------------------------------------------------------------
    # StatutThread : creation / demarrage / arret / suspension
    # -------------------------------------------------------------------------

    def _demarrer_statut_thread(self):
        """Cree et demarre le StatutThread (appele apres connexion)."""
        self.statut_thread = StatutThread(self.grbl)
        self.statut_thread.statut_recu.connect(self.on_statut_recu)
        self.statut_thread.ok_recu.connect(self.on_ok_recu)
        self.statut_thread.erreur_recue.connect(self.on_erreur_grbl)
        self.statut_thread.autre_recu.connect(self.on_autre_recu)
        self.statut_thread.start()

    def _arreter_statut_thread(self):
        """Arrete et supprime le StatutThread (appele a la deconnexion)."""
        if self.statut_thread is not None:
            self.statut_thread.arreter()
            self.statut_thread.wait(2000)
            self.statut_thread = None

    def _suspendre_statut(self):
        """
        Suspend le StatutThread (arret de la lecture du port) le temps
        d'une commande synchrone via grbl.envoyer() ou grbl.lire_statut().
        """
        if self.statut_thread is not None and self.statut_thread.isRunning():
            self.statut_thread.arreter()
            self.statut_thread.wait(1000)

    def _reprendre_statut(self):
        """Relance le StatutThread apres une commande synchrone."""
        if self.statut_thread is not None and not self.statut_thread.isRunning():
            # Redemarrer un QThread deja termine n'est pas possible : on le recree
            self.statut_thread = StatutThread(self.grbl)
            self.statut_thread.statut_recu.connect(self.on_statut_recu)
            self.statut_thread.ok_recu.connect(self.on_ok_recu)
            self.statut_thread.erreur_recue.connect(self.on_erreur_grbl)
            self.statut_thread.autre_recu.connect(self.on_autre_recu)
            self.statut_thread.start()

    # -------------------------------------------------------------------------
    # Slots du StatutThread
    # -------------------------------------------------------------------------

    def on_statut_recu(self, ligne_statut):
        """
        Appele par StatutThread a chaque rapport <...> recu.
        Parse la position et met a jour l'UI.

        Priorite : WPos: (si present, ex. avec $10=19)
        Fallback : MPos: - WCO:
        """
        self.dernier_statut_brut = ligne_statut

        if not (ligne_statut.startswith("<") and ligne_statut.endswith(">")):
            return

        contenu = ligne_statut[1:-1]
        morceaux = contenu.split("|")
        if not morceaux:
            return

        etat = morceaux[0]
        mpos = None
        wpos = None
        for m in morceaux[1:]:
            if m.startswith("MPos:"):
                try:
                    mpos = tuple(float(v) for v in m[5:].split(","))
                except ValueError:
                    pass
            elif m.startswith("WPos:"):
                try:
                    wpos = tuple(float(v) for v in m[5:].split(","))
                except ValueError:
                    pass
            elif m.startswith("WCO:"):
                try:
                    self.dernier_wco = tuple(float(v) for v in m[4:].split(","))
                except ValueError:
                    pass
            elif m.startswith("Ov:"):
                # Format : "Ov:feed,rapids,spindle" (en %)
                # On ignore "rapids" (2eme valeur), on garde feed et spindle.
                try:
                    valeurs = [int(v) for v in m[3:].split(",")]
                    if len(valeurs) >= 1:
                        self.override_feed_grbl = valeurs[0]
                        self.label_override_vitesse.setText(
                            f"{valeurs[0]} %"
                        )
                    if len(valeurs) >= 3:
                        self.override_spindle_grbl = valeurs[2]
                        self.label_override_puissance.setText(
                            f"{valeurs[2]} %"
                        )
                except (ValueError, IndexError):
                    pass

        # Position travail : WPos prioritaire, sinon MPos - WCO
        if wpos is not None:
            wpos_x, wpos_y = wpos[0], wpos[1]
        elif mpos is not None:
            wpos_x = mpos[0] - self.dernier_wco[0]
            wpos_y = mpos[1] - self.dernier_wco[1]
        else:
            wpos_x = None
            wpos_y = None

        if wpos_x is not None:
            self.label_pos_x.setText(f"X : {wpos_x:8.3f}")
            self.label_pos_y.setText(f"Y : {wpos_y:8.3f}")
            self.apercu.maj_position(wpos_x, wpos_y)

        self.label_statut.setText(f"Statut : {ligne_statut}")
        self.label_etat.setText(f"État : {etat}")

    def on_ok_recu(self, total_ok):
        """
        Appele par StatutThread a chaque "ok" recu de GRBL.
        Met a jour la progression UNIQUEMENT si un envoi est en cours.
        """
        if self.thread_envoi is None or not self.thread_envoi.isRunning():
            return

        total = len(self.thread_envoi.lignes) if self.thread_envoi else 0
        if total <= 0:
            return

        numero = min(total_ok, total)
        self.label_progression.setText(f"Envoi : {numero} / {total}")

        # --- Calcul du temps restant estime ---
        try:
            if getattr(self, "temps_debut_envoi", None) is None:
                return

            maintenant = time.time()
            temps_ecoule = maintenant - self.temps_debut_envoi

            if getattr(self, "temps_pause_debut", None) is not None:
                temps_ecoule -= (maintenant - self.temps_pause_debut)

            temps_ecoule -= getattr(self, "temps_ecoule_avant_pause", 0.0)

            if numero > 0 and temps_ecoule > 0:
                restant = total - numero
                estimation = temps_ecoule * restant / numero

                self.mesures_temps_restant.append(estimation)
                if len(self.mesures_temps_restant) > 20:
                    self.mesures_temps_restant.pop(0)

                moyenne = (sum(self.mesures_temps_restant)
                           / len(self.mesures_temps_restant))

                if temps_ecoule < 3.0:
                    self.label_temps_restant.setText("Estimation…")
                else:
                    self.label_temps_restant.setText(
                        f"Temps restant : ~{self._formater_duree(moyenne)}"
                    )
        except Exception:
            pass

    def on_erreur_grbl(self, message):
        """Appele par StatutThread a chaque ligne 'error:N' recue."""
        self.afficher_console(f"<< {message}")
        # Si un envoi est en cours, on l'arrete.
        if self.thread_envoi is not None and self.thread_envoi.isRunning():
            self.thread_envoi.arreter()

    def on_autre_recu(self, message):
        """Appele par StatutThread pour toute autre ligne (accueil, info)."""
        self.afficher_console(f"<< {message}")

    # -------------------------------------------------------------------------
    # Actions : console
    # -------------------------------------------------------------------------

    def afficher_console(self, texte):
        self.console.append(texte)

    def envoyer_commande_manuelle(self):
        commande = self.champ_commande.text().strip()
        if not commande:
            return
        if not self.grbl.est_connecte:
            self.afficher_console(">> (non connecté, commande ignorée)")
            return

        self._suspendre_statut()

        self.afficher_console(f">> {commande}")
        try:
            reponses = self.grbl.envoyer(commande)
            for ligne in reponses:
                self.afficher_console(f"<< {ligne}")
        except Exception as e:
            self.afficher_console(f"!! Erreur : {e}")

        self.champ_commande.clear()
        self._reprendre_statut()

    def effacer_console(self):
        self.console.clear()

    # -------------------------------------------------------------------------
    # Actions : jog
    # -------------------------------------------------------------------------

    def jog(self, axe, direction):
        if not self.grbl.est_connecte:
            self.afficher_console(">> (jog ignoré : non connecté)")
            return

        pas = self.combo_pas.currentData()
        vitesse = self.combo_vitesse.currentData()
        delta = pas * direction

        commande = f"$J=G91 G21 {axe}{delta} F{vitesse}"
        self.afficher_console(f">> {commande}")

        self._suspendre_statut()

        try:
            reponses = self.grbl.envoyer(commande)
            for ligne in reponses:
                self.afficher_console(f"<< {ligne}")
        except Exception as e:
            self.afficher_console(f"!! Erreur jog : {e}")

        self._reprendre_statut()

    # -------------------------------------------------------------------------
    # Actions : STOP
    # -------------------------------------------------------------------------

    def stop_urgence(self):
        if not self.grbl.est_connecte:
            return

        self.grbl.envoyer_octet_immediat(0x18)
        self.afficher_console(">> [STOP] Ctrl-X envoyé à GRBL")

        if self.thread_envoi is not None and self.thread_envoi.isRunning():
            if self.est_en_pause:
                self.thread_envoi.reprendre()
                self.est_en_pause = False
                self.btn_pause.setText("⏸  PAUSE")
            self.thread_envoi.arreter()
            self.afficher_console(">> [STOP] Demande d'arrêt du thread d'envoi.")

        self.stop_restant = STOP_COOLDOWN
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText(f"STOP ({self.stop_restant}s)")
        self.timer_stop.start()

    def decrementer_stop(self):
        self.stop_restant -= 1
        if self.stop_restant <= 0:
            self.timer_stop.stop()
            self.btn_stop.setEnabled(True)
            self.btn_stop.setText("STOP")
        else:
            self.btn_stop.setText(f"STOP ({self.stop_restant}s)")

    # -------------------------------------------------------------------------
    # Actions : origine travail
    # -------------------------------------------------------------------------

    def definir_origine_ici(self):
        if not self.grbl.est_connecte:
            self.afficher_console(">> (origine ignorée : non connecté)")
            return

        commande = "G10 L20 P1 X0 Y0"
        self.afficher_console(f">> {commande}  (définir origine ici)")

        self._suspendre_statut()

        try:
            reponses = self.grbl.envoyer(commande)
            for ligne in reponses:
                self.afficher_console(f"<< {ligne}")
        except Exception as e:
            self.afficher_console(f"!! Erreur origine : {e}")

        self._reprendre_statut()

    def retour_origine(self):
        if not self.grbl.est_connecte:
            self.afficher_console(">> (retour origine ignoré : non connecté)")
            return

        commande = "G90 G0 X0 Y0"
        self.afficher_console(f">> {commande}  (retour origine travail)")

        self._suspendre_statut()

        try:
            reponses = self.grbl.envoyer(commande, timeout=10.0)
            for ligne in reponses:
                self.afficher_console(f"<< {ligne}")
        except Exception as e:
            self.afficher_console(f"!! Erreur retour origine : {e}")

        self._reprendre_statut()

    def deverrouiller(self):
        if not self.grbl.est_connecte:
            self.afficher_console(">> ($X ignoré : non connecté)")
            return

        self.afficher_console(">> $X  (déverrouillage)")
        try:
            reponses = self.grbl.envoyer("$X")
            for ligne in reponses:
                self.afficher_console(f"<< {ligne}")
        except Exception as e:
            self.afficher_console(f"!! Erreur $X : {e}")

    # -------------------------------------------------------------------------
    # Actions : "Aller à X,Y"
    # -------------------------------------------------------------------------

    def aller_a_position(self):
        if not self.grbl.est_connecte:
            self.afficher_console(">> (aller à ignoré : non connecté)")
            return

        x = self.spin_x.value()
        y = self.spin_y.value()

        reponse = QMessageBox.question(
            self,
            "Confirmer le déplacement",
            f"Déplacer la machine à :\n\n"
            f"    X = {x:.1f} mm\n"
            f"    Y = {y:.1f} mm\n\n"
            f"Ce déplacement se fera en mode rapide (G0).\n"
            f"Vérifier que la trajectoire est libre.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reponse != QMessageBox.Yes:
            self.afficher_console(">> (aller à annulé par l'utilisateur)")
            return

        commande = f"G90 G0 X{x:.3f} Y{y:.3f}"
        self.afficher_console(f">> {commande}  (aller à position absolue)")

        self._suspendre_statut()

        try:
            reponses = self.grbl.envoyer(commande, timeout=10.0)
            for ligne in reponses:
                self.afficher_console(f"<< {ligne}")
        except Exception as e:
            self.afficher_console(f"!! Erreur aller à : {e}")

        self._reprendre_statut()

    # -------------------------------------------------------------------------
    # Actions : fichier G-code (chargement)
    # -------------------------------------------------------------------------

    def charger_fichier(self):
        chemin, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir un fichier G-code",
            "",
            FILTRES_GCODE
        )
        if not chemin:
            return

        try:
            with open(chemin, "r", encoding="utf-8", errors="replace") as f:
                contenu = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de lecture", f"Impossible de lire le fichier :\n{e}")
            return

        self.fichier_charge = chemin
        self.apercu_gcode.setPlainText(contenu)

        lignes = contenu.splitlines()
        nb_total = len(lignes)
        nb_non_vides = sum(1 for l in lignes if l.strip())

        nom = os.path.basename(chemin)
        self.label_fichier.setText(
            f"{nom}   —   {nb_total} lignes ({nb_non_vides} non vides)"
        )
        self.afficher_console(f"— Fichier chargé : {chemin}  ({nb_non_vides} lignes)")

        # Estimation du temps
        try:
            from src.core.estimateur_temps import (
                estimer_temps_gcode, formater_temps
            )
            secondes = estimer_temps_gcode(lignes)
            self.label_temps_fichier.setText(
                f"Temps estimé : {formater_temps(secondes)}"
            )
        except Exception:
            self.label_temps_fichier.setText("")

        self.apercu.charger_parcours(lignes)

    # -------------------------------------------------------------------------
    # Actions : ENVOI DU FICHIER (threadé)
    # -------------------------------------------------------------------------

    def envoyer_fichier(self):
        if not self.grbl.est_connecte:
            QMessageBox.warning(self, "Non connecté",
                                "Veuillez d'abord connecter la machine.")
            return
        if not self.fichier_charge:
            QMessageBox.warning(self, "Aucun fichier",
                                "Veuillez d'abord charger un fichier G-code.")
            return
        if self.thread_envoi is not None and self.thread_envoi.isRunning():
            QMessageBox.information(self, "Envoi en cours",
                                    "Un envoi est déjà en cours.")
            return

        texte = self.apercu_gcode.toPlainText()
        lignes_brutes = texte.splitlines()
        lignes = [l.strip() for l in lignes_brutes if l.strip()]
        total = len(lignes)

        if total == 0:
            QMessageBox.information(self, "Fichier vide",
                                    "Le fichier ne contient aucune ligne à envoyer.")
            return

        nom = os.path.basename(self.fichier_charge)

        if self.mode_machine == "fraiseuse":
            rappel = ("⚠ MODE FRAISEUSE ⚠\n"
                      "La pause n'arrêtera PAS la broche.\n"
                      "Gardez la main sur l'arrêt d'urgence.\n")
        else:
            rappel = "Mode LASER : la pause coupera automatiquement le faisceau.\n"

        reponse = QMessageBox.question(
            self,
            "Confirmer l'envoi",
            f"Envoyer « {nom} » à la machine ?\n\n"
            f"{rappel}\n"
            f"Rappels :\n"
            f"  • l'origine doit être définie\n"
            f"  • la trajectoire doit être libre\n"
            f"  • ayez la main sur l'alimentation physique",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reponse != QMessageBox.Yes:
            self.afficher_console(">> (envoi annulé par l'utilisateur)")
            return

        self.est_en_pause = False
        self.btn_pause.setText("⏸  PAUSE")

        # Reset des overrides a 100 % pour eviter d'oublier un reglage precedent
        self._reset_overrides()

        self.mettre_interface_en_envoi(True)

        self.afficher_console(f"═══ Début d'envoi : {nom} — {total} lignes ═══")
        self.afficher_console(f"    Mode machine : {self.combo_mode.currentText()}")
        self.label_progression.setText(f"Envoi : 0 / {total}")
        self.label_temps_restant.setText("Estimation…")

        # Compteur de temps pour l'estimation du temps restant
        self.temps_debut_envoi = time.time()
        self.temps_ecoule_avant_pause = 0.0
        self.temps_pause_debut = None
        self.mesures_temps_restant = []  # moyenne glissante

        # Le StatutThread continue de tourner PENDANT l'envoi : il est le
        # seul lecteur du port et fournit la position (WPos:) + la
        # progression (via on_ok_recu) + les erreurs (via on_erreur_grbl).
        self.thread_envoi = EnvoiGcodeThread(self.grbl, lignes)
        self.thread_envoi.ligne_envoyee.connect(self.on_envoi_ligne)
        self.thread_envoi.termine.connect(self.on_envoi_termine)
        self.thread_envoi.start()

    def mettre_interface_en_envoi(self, en_cours):
        actif = not en_cours

        self.btn_x_plus.setEnabled(actif)
        self.btn_x_moins.setEnabled(actif)
        self.btn_y_plus.setEnabled(actif)
        self.btn_y_moins.setEnabled(actif)

        self.btn_definir_origine.setEnabled(actif)
        self.btn_retour_origine.setEnabled(actif)
        self.btn_deverrouiller.setEnabled(actif)
        self.btn_aller.setEnabled(actif)

        self.btn_envoyer.setEnabled(actif)
        self.champ_commande.setEnabled(actif)

        self.btn_envoyer_fichier.setEnabled(actif)
        self.btn_charger.setEnabled(actif)

        self.combo_mode.setEnabled(actif)

        self.btn_pause.setEnabled(en_cours)

        if not en_cours:
            self.btn_pause.setText("⏸  PAUSE")
            self.est_en_pause = False

    # -------------------------------------------------------------------------
    # Slots du thread d'envoi
    # -------------------------------------------------------------------------

    def _formater_duree(self, secondes):
        """Formate une duree en secondes en 'X min Y s' ou 'Y s'."""
        try:
            s = int(round(secondes))
            if s < 60:
                return f"{s} s"
            minutes = s // 60
            sec = s % 60
            return f"{minutes} min {sec:02d} s"
        except Exception:
            return "---"

    def on_envoi_ligne(self, numero, ligne):
        self.afficher_console(f">> [{numero}] {ligne}")

    def on_envoi_termine(self, succes, message):
        if succes:
            self.afficher_console(f"═══ {message} ═══")
            self.label_progression.setText(message)
        else:
            self.afficher_console(f"═══ ÉCHEC : {message} ═══")
            self.label_progression.setText(f"Échec : {message}")

        self.mettre_interface_en_envoi(False)

        # Nettoyage du compteur de temps restant
        self.label_temps_restant.setText("")
        self.temps_debut_envoi = None
        self.temps_ecoule_avant_pause = 0.0
        self.temps_pause_debut = None
        self.mesures_temps_restant = []

        if self.thread_envoi is not None:
            self.thread_envoi.wait(2000)
            self.thread_envoi = None

        # Le StatutThread continue de tourner : pas besoin de relancer de timer.

        # On remontre le marqueur de l'Aperçu une fois l'envoi terminé
        self.apercu.item_marqueur.setVisible(True)


    # -------------------------------------------------------------------------
    # Overrides temps reel (vitesse + puissance)
    # -------------------------------------------------------------------------

    # --- Octets GRBL 1.1 (doc officielle) ---
    # Feed (vitesse)
    OCTET_FEED_RESET = 0x90   # remet a 100 %
    OCTET_FEED_PLUS  = 0x91   # +10 %
    OCTET_FEED_MOINS = 0x92   # -10 %
    # Spindle (puissance)
    OCTET_SPINDLE_RESET = 0x99   # remet a 100 %
    OCTET_SPINDLE_PLUS  = 0x9A   # +10 %
    OCTET_SPINDLE_MOINS = 0x9B   # -10 %

    def _envoyer_octet_override(self, octet, nom):
        """Envoie un octet d'override a GRBL (silencieux si non connecte)."""
        if not self.grbl.est_connecte:
            return
        try:
            self.grbl.envoyer_octet_immediat(octet)
            self.afficher_console(
                f">> [OVERRIDE] {nom} (octet 0x{octet:02X})"
            )
        except Exception as e:
            self.afficher_console(f"!! Erreur override {nom} : {e}")

    def _override_vitesse_moins(self):
        # Envoie l'octet -10 % a GRBL. Le label sera mis a jour par le
        # prochain statut recu (Ov:) : plus d'estimation locale.
        self._envoyer_octet_override(self.OCTET_FEED_MOINS, "Vitesse -10 %")

    def _override_vitesse_plus(self):
        # Envoie l'octet +10 % a GRBL. Le label sera mis a jour par le
        # prochain statut recu (Ov:).
        self._envoyer_octet_override(self.OCTET_FEED_PLUS, "Vitesse +10 %")

    def _override_puissance_moins(self):
        # Envoie l'octet -10 % a GRBL. Le label sera mis a jour par le
        # prochain statut recu (Ov:).
        self._envoyer_octet_override(self.OCTET_SPINDLE_MOINS, "Puissance -10 %")

    def _override_puissance_plus(self):
        # Envoie l'octet +10 % a GRBL. Le label sera mis a jour par le
        # prochain statut recu (Ov:).
        self._envoyer_octet_override(self.OCTET_SPINDLE_PLUS, "Puissance +10 %")

    def _reset_overrides(self):
        """
        Remet les overrides a 100 % (appele au debut de chaque envoi).
        Envoie les octets de reset officiels.
        Les labels seront mis a jour par le prochain statut recu (Ov:).
        """
        if self.grbl.est_connecte:
            try:
                self.grbl.envoyer_octet_immediat(self.OCTET_FEED_RESET)
                self.grbl.envoyer_octet_immediat(self.OCTET_SPINDLE_RESET)
            except Exception:
                pass


    # -------------------------------------------------------------------------
    # PAUSE / REPRISE
    # -------------------------------------------------------------------------


    # -------------------------------------------------------------------------
    # Point laser (appui maintenu)
    # -------------------------------------------------------------------------

    def allumer_point_laser(self):
        """
        Allume le laser a la puissance choisie (appui maintenu sur le bouton).
        Sequence GRBL : M3 S<valeur> + G1 F<vitesse> (pour activer le PWM).
        ⚠️ La securite depend de l'appui maintenu : si l'utilisateur relache,
        le bouton emet 'released' et le laser s'eteint.
        """
        if not self.grbl.est_connecte:
            return

        puissance_pct = self.spin_puissance_point.value()

        # Recuperation de S_MAX ($30 de GRBL)
        s_max = 1000  # valeur par defaut
        try:
            reponses = self.grbl.envoyer("$$", timeout=2.0)
            for r in reponses:
                if r.startswith("$30="):
                    s_max = int(r.split("=")[1])
                    break
        except Exception:
            pass

        s_valeur = int(round(puissance_pct / 100.0 * s_max))

        # Sequence : M3 S<valeur> + G1 F<vitesse> (active le PWM)
        try:
            self.grbl.envoyer(f"M3 S{s_valeur}", timeout=2.0)
            self.grbl.envoyer("G1 F500", timeout=2.0)
            self.afficher_console(
                f">> [POINT LASER] Allume a {puissance_pct}% (S{s_valeur})"
            )
        except Exception as e:
            self.afficher_console(f"!! Erreur allumage point laser : {e}")


    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Mini-matrice : estimation du temps (live)
    # -------------------------------------------------------------------------

    def _maj_estimation_matrice(self):
        """
        Met a jour le label d'estimation de la mini-matrice a chaque
        changement d'un champ. Affichage simple : nombre de cases + duree.
        """
        cols = self.spin_matrice_cols.value()
        rows = self.spin_matrice_rows.value()
        taille = self.spin_matrice_taille.value()
        espace = self.spin_matrice_espace.value()

        nb_cases = cols * rows

        # Perimetre d'un carre + retour au point de depart (fermeture)
        perimetre = 4.0 * taille

        # Vitesse moyenne (approximation : on prend la moyenne des V min/max)
        v_min = self.spin_matrice_v_min.value()
        v_max = self.spin_matrice_v_max.value()
        v_moy = (v_min + v_max) / 2.0 if v_max > v_min else v_min
        if v_moy < 1.0:
            v_moy = 1.0

        # Duree d'un carre = perimetre / vitesse (mm / (mm/min)) * 60 = secondes
        duree_case_s = (perimetre / v_moy) * 60.0

        # Duree totale = nb_cases * duree_case (sans compter les deplacements)
        # + deplacements estimes : on ajoute ~20 %
        duree_totale_s = nb_cases * duree_case_s * 1.2

        # Format
        if duree_totale_s < 60:
            txt_temps = f"{duree_totale_s:.0f} s"
        else:
            minutes = int(duree_totale_s // 60)
            secondes = int(duree_totale_s % 60)
            txt_temps = f"{minutes} min {secondes:02d} s"

        self.label_matrice_estime.setText(
            f"~{nb_cases} cases, duree estimee ~{txt_temps}"
        )


    # -------------------------------------------------------------------------
    # Mini-matrice : gravure de la grille P x V
    # -------------------------------------------------------------------------

    def graver_matrice(self):
        """
        Grave une mini-matrice de carres a partir de la position actuelle.

        - P en colonnes (X), V en lignes (Y).
        - Chaque case : carre de 'taille' mm, espacement 'espace' mm.
        - Mode Line uniquement (contours).
        - Position de depart = position actuelle de la tete (coin bas-gauche
          de la matrice).
        """
        # --- Securite : connexion obligatoire ---
        if not self.grbl.est_connecte:
            QMessageBox.warning(self, "Non connecte",
                                "Connecte la machine avant de graver.")
            return

        # --- Recuperation des parametres ---
        cols = self.spin_matrice_cols.value()
        rows = self.spin_matrice_rows.value()
        taille = self.spin_matrice_taille.value()
        espace = self.spin_matrice_espace.value()

        p_min = self.spin_matrice_p_min.value()
        p_max = self.spin_matrice_p_max.value()
        v_min = self.spin_matrice_v_min.value()
        v_max = self.spin_matrice_v_max.value()

        if p_max <= p_min:
            QMessageBox.warning(self, "Plage P invalide",
                                "Puissance max doit etre > puissance min.")
            return
        if v_max <= v_min:
            QMessageBox.warning(self, "Plage V invalide",
                                "Vitesse max doit etre > vitesse min.")
            return

        # --- Recuperation de S_MAX ($30) + position (statut suspendu) ---
        s_max = 1000
        self._suspendre_statut()
        try:
            reponses = self.grbl.envoyer("$$", timeout=2.0)
            for r in reponses:
                if r.startswith("$30="):
                    try:
                        s_max = int(r.split("=")[1])
                    except ValueError:
                        pass
                    break
        except Exception:
            pass

        # --- Lecture de la position actuelle ---
        statut = self.grbl.lire_statut()
        self._reprendre_statut()
        if not statut or not (statut.startswith("<") and statut.endswith(">")):
            QMessageBox.warning(self, "Position inconnue",
                                "Impossible de lire la position actuelle.")
            return

        contenu = statut[1:-1]
        morceaux = contenu.split("|")
        mpos = None
        wco = self.dernier_wco
        for m in morceaux[1:]:
            if m.startswith("MPos:"):
                try:
                    mpos = tuple(float(v) for v in m[5:].split(","))
                except ValueError:
                    pass
            elif m.startswith("WCO:"):
                try:
                    wco = tuple(float(v) for v in m[4:].split(","))
                except ValueError:
                    pass

        if mpos is None:
            if timer_actif:
                self.timer_statut.start()
            QMessageBox.warning(self, "Position inconnue",
                                "MPos absent du statut GRBL.")
            return

        x_orig = mpos[0] - wco[0]
        y_orig = mpos[1] - wco[1]

        # --- Generation des listes de valeurs P et V ---
        # Colonnes : P de p_min a p_max, cols valeurs
        if cols == 1:
            liste_p = [p_min]
        else:
            pas_p = (p_max - p_min) / (cols - 1)
            liste_p = [p_min + i * pas_p for i in range(cols)]

        # Lignes : V de v_min a v_max, rows valeurs
        if rows == 1:
            liste_v = [v_min]
        else:
            pas_v = (v_max - v_min) / (rows - 1)
            liste_v = [v_min + i * pas_v for i in range(rows)]

        # --- Construction du G-code ---
        # La tete commence a (x_orig, y_orig), qui est le coin bas-gauche
        # de la case (0, 0) de la grille.
        lignes = []
        lignes.append("; === Mini-matrice de test ===")
        lignes.append(f"; Grille {cols} x {rows}  |  P={p_min}..{p_max}%  "
                      f"|  V={v_min}..{v_max} mm/min")
        lignes.append(f"; Taille case={taille}mm  Espacement={espace}mm")
        lignes.append("")

        pas_case = taille + espace

        # Legende dans la console (pour retrouver quel carre = quel P/V)
        self.afficher_console("--- Mini-matrice : legende ---")
        for j in range(rows):
            v_val = liste_v[j]
            self.afficher_console(
                f"  Ligne {j} (Y={y_orig + j * pas_case:.1f}) : V={v_val:.0f}"
            )
        for i in range(cols):
            p_val = liste_p[i]
            self.afficher_console(
                f"  Col {i} (X={x_orig + i * pas_case:.1f}) : P={p_val:.1f}%"
            )
        self.afficher_console("---")

        # Parcours ligne par ligne (Y), puis colonne par colonne (X)
        for j in range(rows):
            v_val = liste_v[j]
            vitesse = v_val if v_val > 0 else 500.0
            for i in range(cols):
                p_val = liste_p[i]
                s_valeur = int(round(p_val / 100.0 * s_max))
                s_valeur = max(0, min(s_max, s_valeur))

                x0 = x_orig + i * pas_case
                y0 = y_orig + j * pas_case
                x1 = x0 + taille
                y1 = y0 + taille

                lignes.append(f"; Case ({i},{j}) : P={p_val:.1f}% (S{s_valeur}) "
                              f"V={vitesse:.0f} mm/min")
                lignes.append("S0")
                lignes.append(f"G0 X{x0:.3f} Y{y0:.3f}")
                lignes.append(f"M4 S{s_valeur}")
                lignes.append(f"G1 F{vitesse:.0f}")
                lignes.append(f"G1 X{x1:.3f} Y{y0:.3f}")
                lignes.append(f"G1 X{x1:.3f} Y{y1:.3f}")
                lignes.append(f"G1 X{x0:.3f} Y{y1:.3f}")
                lignes.append(f"G1 X{x0:.3f} Y{y0:.3f}")
                lignes.append("M5")
                lignes.append("G0")
                lignes.append("")

        # Fin : retour a l'origine de la matrice
        lignes.append("M5")
        lignes.append(f"G0 X{x_orig:.3f} Y{y_orig:.3f}")

        # --- Envoi synchrone, ligne par ligne ---
        self.afficher_console(
            f"--- Mini-matrice : {cols}x{rows} cases a partir de "
            f"({x_orig:.1f},{y_orig:.1f}) ---"
        )

        self.mettre_interface_en_envoi(True)

        succes = True
        message = "Mini-matrice terminee."
        nb_envoyees = 0
        try:
            for ligne in lignes:
                if ligne.startswith(";") or not ligne.strip():
                    continue
                reponses = self.grbl.envoyer(ligne, timeout=10.0)
                nb_envoyees += 1
                self.afficher_console(f">> {ligne}")
                for r in reponses:
                    if r.startswith("error"):
                        succes = False
                        message = f"Erreur GRBL : {r} (ligne : {ligne})"
                        break
                if not succes:
                    break
        except Exception as e:
            succes = False
            message = f"Erreur : {e}"
        finally:
            if not succes:
                try:
                    self.grbl.envoyer("M5", timeout=2.0)
                    self.grbl.envoyer("G0", timeout=2.0)
                except Exception:
                    pass

        self.afficher_console(f"--- {message} ({nb_envoyees} lignes) ---")
        self.mettre_interface_en_envoi(False)


    # -------------------------------------------------------------------------
    # Test rapide : gravure d'un carre a la position actuelle
    # -------------------------------------------------------------------------


    # Test rapide : gravure d'un carre a la position actuelle
    # -------------------------------------------------------------------------

    def graver_carre_test(self):
        """
        Grave un carre de test a la position actuelle de la tete.

        Parametres saisis dans l'onglet Jog :
            - taille (mm)
            - puissance (%)
            - vitesse (mm/min)
            - passes (N)

        Le carre est ferme (retour au point de depart).
        Sequence GRBL par passe :
            S0, G0 vers coin, M3 S<val>, G1 F<vit>,
            G1 x3 (cotes), G1 retour coin, M5, G0
        """
        # --- Securite : connexion obligatoire ---
        if not self.grbl.est_connecte:
            QMessageBox.warning(self, "Non connecte",
                                "Connecte la machine avant de graver.")
            return

        # --- Recuperation des parametres ---
        taille = self.spin_test_taille.value()
        puissance_pct = self.spin_test_puissance.value()
        vitesse = self.spin_test_vitesse.value()
        passes = self.spin_test_passes.value()

        # --- Recuperation de S_MAX ($30) + position (statut suspendu) ---
        s_max = 1000  # fallback
        self._suspendre_statut()
        try:
            reponses = self.grbl.envoyer("$$", timeout=2.0)
            for r in reponses:
                if r.startswith("$30="):
                    try:
                        s_max = int(r.split("=")[1])
                    except ValueError:
                        pass
                    break
        except Exception:
            pass

        s_valeur = int(round(puissance_pct / 100.0 * s_max))
        s_valeur = max(0, min(s_max, s_valeur))

        # --- Lecture de la position actuelle (MPos - WCO) ---
        statut = self.grbl.lire_statut()
        self._reprendre_statut()
        if not statut or not (statut.startswith("<") and statut.endswith(">")):
            QMessageBox.warning(self, "Position inconnue",
                                "Impossible de lire la position actuelle.")
            return

        contenu = statut[1:-1]
        morceaux = contenu.split("|")
        mpos = None
        wco = self.dernier_wco
        for m in morceaux[1:]:
            if m.startswith("MPos:"):
                try:
                    mpos = tuple(float(v) for v in m[5:].split(","))
                except ValueError:
                    pass
            elif m.startswith("WCO:"):
                try:
                    wco = tuple(float(v) for v in m[4:].split(","))
                except ValueError:
                    pass

        if mpos is None:
            if timer_actif:
                self.timer_statut.start()
            QMessageBox.warning(self, "Position inconnue",
                                "MPos absent du statut GRBL.")
            return

        x0 = mpos[0] - wco[0]
        y0 = mpos[1] - wco[1]
        x1 = x0 + taille
        y1 = y0 + taille

        # --- Construction du G-code ---
        lignes = []
        lignes.append("; === Test rapide : carre de test ===")
        lignes.append(f"; Taille={taille}mm  P={puissance_pct}%  "
                      f"V={vitesse}mm/min  N={passes}")
        for _ in range(passes):
            lignes.append("S0")
            lignes.append(f"G0 X{x0:.3f} Y{y0:.3f}")
            lignes.append(f"M3 S{s_valeur}")
            lignes.append(f"G1 F{vitesse:.0f}")
            lignes.append(f"G1 X{x1:.3f} Y{y0:.3f}")
            lignes.append(f"G1 X{x1:.3f} Y{y1:.3f}")
            lignes.append(f"G1 X{x0:.3f} Y{y1:.3f}")
            lignes.append(f"G1 X{x0:.3f} Y{y0:.3f}")
            lignes.append("M5")
            lignes.append("G0")

        self.afficher_console(
            f"--- Test rapide : carre {taille}mm a ({x0:.1f},{y0:.1f}) "
            f"P={puissance_pct}% (S{s_valeur}) V={vitesse} N={passes} ---"
        )

        # --- Desactivation de l'interface pendant la gravure ---
        self.mettre_interface_en_envoi(True)

        succes = True
        message = "Test rapide termine."
        try:
            for ligne in lignes:
                if not ligne.startswith(";") and ligne.strip():
                    reponses = self.grbl.envoyer(ligne, timeout=10.0)
                    self.afficher_console(f">> {ligne}")
                    for r in reponses:
                        if r.startswith("error"):
                            succes = False
                            message = f"Erreur GRBL : {r} (ligne : {ligne})"
                            break
                    if not succes:
                        break
        except Exception as e:
            succes = False
            message = f"Erreur : {e}"
        finally:
            if not succes:
                try:
                    self.grbl.envoyer("M5", timeout=2.0)
                    self.grbl.envoyer("G0", timeout=2.0)
                except Exception:
                    pass

        self.afficher_console(f"--- {message} ---")
        self.mettre_interface_en_envoi(False)



    def eteindre_point_laser(self):
        """
        Eteint le laser (relachement du bouton).
        Sequence : M5 + G0 (pour forcer la coupure PWM).
        """
        if not self.grbl.est_connecte:
            return

        try:
            self.grbl.envoyer("M5", timeout=2.0)
            self.grbl.envoyer("G0", timeout=2.0)
            self.afficher_console(">> [POINT LASER] Eteint")
        except Exception as e:
            self.afficher_console(f"!! Erreur extinction point laser : {e}")

    # -------------------------------------------------------------------------
    # Cadrage : parcourt le rectangle de la bbox avec laser faible
    # -------------------------------------------------------------------------

    def executer_cadrage(self, x_min, y_min, x_max, y_max, cible_txt):
        """
        Execute un cadrage : parcourt le rectangle (x_min,y_min)-(x_max,y_max)
        avec un laser faible (0.5 %). La tete RESTE au point de depart.

        Appelee par MiseEnPageWidget.cadrer_selection().
        """
        if not self.grbl.est_connecte:
            QMessageBox.warning(self, "Non connecté",
                                "Connectez la machine avant de cadrer.")
            return

        # --- Conversion 0.5 % en S ---
        s_max = 1000
        try:
            reponses = self.grbl.envoyer("$$", timeout=2.0)
            for r in reponses:
                if r.startswith("$30="):
                    s_max = int(r.split("=")[1])
                    break
        except Exception:
            pass

        s_valeur = max(1, int(round(0.5 / 100.0 * s_max)))  # 0.5 %
        vitesse = 1000  # mm/min

        try:
            # 1) Va au coin 1 (laser eteint)
            self.grbl.envoyer("S0", timeout=2.0)
            self.grbl.envoyer(
                f"G0 X{x_min:.3f} Y{y_min:.3f}", timeout=5.0
            )

            # 2) Allume le laser faiblement
            self.grbl.envoyer(f"M4 S{s_valeur}", timeout=2.0)
            self.grbl.envoyer(f"G1 F{vitesse}", timeout=2.0)

            # 3) Trace les 3 autres cotes et ferme
            self.grbl.envoyer(
                f"G1 X{x_max:.3f} Y{y_min:.3f}", timeout=10.0
            )
            self.grbl.envoyer(
                f"G1 X{x_max:.3f} Y{y_max:.3f}", timeout=10.0
            )
            self.grbl.envoyer(
                f"G1 X{x_min:.3f} Y{y_max:.3f}", timeout=10.0
            )
            self.grbl.envoyer(
                f"G1 X{x_min:.3f} Y{y_min:.3f}", timeout=10.0
            )

            # 4) Eteint le laser
            self.grbl.envoyer("M5", timeout=2.0)
            self.grbl.envoyer("G0", timeout=2.0)

            self.afficher_console(
                f"— Cadrage terminé : {cible_txt}  "
                f"X[{x_min:.1f} → {x_max:.1f}]  Y[{y_min:.1f} → {y_max:.1f}]"
            )

        except Exception as e:
            # En cas d'erreur, on force l'extinction
            try:
                self.grbl.envoyer("M5", timeout=2.0)
                self.grbl.envoyer("G0", timeout=2.0)
            except Exception:
                pass
            self.afficher_console(f"!! Erreur cadrage : {e}")

    def basculer_pause(self):
        if not self.grbl.est_connecte:
            return
        if self.thread_envoi is None or not self.thread_envoi.isRunning():
            return

        try:
            if not self.est_en_pause:
                self.grbl.envoyer_octet_immediat(0x21)
                self.thread_envoi.pause()
                self.est_en_pause = True
                self.btn_pause.setText("▶  REPRENDRE")
                # Marque le debut de la pause (pour ne pas compter ce temps)
                self.temps_pause_debut = time.time()

                if self.mode_machine == "fraiseuse":
                    self.afficher_console(
                        ">> [PAUSE] Feed hold envoyé. "
                        "⚠ La broche continue de tourner."
                    )
                else:
                    self.afficher_console(">> [PAUSE] Feed hold envoyé (faisceau coupé auto).")
            else:
                self.grbl.envoyer_octet_immediat(0x7E)
                self.thread_envoi.reprendre()
                self.est_en_pause = False
                self.btn_pause.setText("⏸  PAUSE")
                self.afficher_console(">> [REPRISE] Cycle start envoyé à GRBL")
                # Cumule le temps de pause ecoule et remet le marqueur a None
                if self.temps_pause_debut is not None:
                    self.temps_ecoule_avant_pause += (time.time() - self.temps_pause_debut)
                    self.temps_pause_debut = None

        except Exception as e:
            self.afficher_console(f"!! Erreur pause/reprise : {type(e).__name__} — {e}")

        # -------------------------------------------------------------------------
        # Fermeture propre
        # -------------------------------------------------------------------------

    def closeEvent(self, event):
        if self.thread_envoi is not None and self.thread_envoi.isRunning():
            if self.est_en_pause:
                self.thread_envoi.reprendre()
            self.thread_envoi.arreter()
            self.thread_envoi.wait(2000)

        self._arreter_statut_thread()
        self.timer_stop.stop()
        if self.grbl.est_connecte:
            self.grbl.deconnecter()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # --- Chargement de la police embarquée (Inter) ---
    dossier_polices = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                   "src", "assets", "polices")
    if os.path.exists(dossier_polices):
        fichiers_polices = glob.glob(os.path.join(dossier_polices, "*.ttf"))
        polices_chargees = 0
        for chemin in fichiers_polices:
            id_police = QFontDatabase.addApplicationFont(chemin)
            if id_police != -1:
                polices_chargees += 1
        print(f"{polices_chargees} police(s) chargée(s) depuis {dossier_polices}")
    else:
        print(f"Attention : dossier de polices introuvable ({dossier_polices})")

    # Charger la langue sauvegardee
    i18n_gestionnaire.charger_langue(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()