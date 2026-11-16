# =============================================================================
# test_envoi_counting.py
# -----------------------------------------------------------------------------
# Rôle : Test isolé de EnvoiGcodeThread en mode character counting.
#
# Ce script :
#   1. Se connecte a la machine (port demande a l'utilisateur)
#   2. Utilise un petit fichier G-code de test (genere en dur)
#   3. Lance EnvoiGcodeThread en mode counting
#   4. Affiche la progression + les signaux recus
#   5. Verifie que tout se passe bien
#
# ⚠️ ATTENTION : la machine va BOUGER. Laser eteint (pas de M3/M4).
#    On fait uniquement des G0 (rapides) vers des positions sures.
#
# Usage : env/Scripts/python.exe test_envoi_counting.py
# =============================================================================

import sys
import time

from PySide6.QtCore import QCoreApplication, QTimer

from serial.tools import list_ports
from src.grbl.controller import GrblController
from src.grbl.envoi_thread import EnvoiGcodeThread


# --- G-code de test : petits mouvements G0 autour de l'origine --------------
GCODE_TEST = [
    "; Test character counting",
    "G21",              ; mm
    "G90",              ; absolu
    "S0",               ; laser eteint (securite)
    "G0 X10 Y0",
    "G0 X10 Y10",
    "G0 X0 Y10",
    "G0 X0 Y0",
    "G0 X5 Y5",
    "G0 X15 Y5",
    "G0 X15 Y15",
    "G0 X5 Y15",
    "G0 X5 Y5",
    "G0 X0 Y0",
]


def choisir_port():
    ports = list(list_ports.comports())
    if not ports:
        print("Aucun port disponible.")
        sys.exit(1)

    print("\nPorts disponibles :")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.device}  —  {p.description}")

    try:
        choix = int(input("\nNumero du port : ").strip())
    except (ValueError, EOFError):
        print("Choix invalide.")
        sys.exit(1)

    if choix < 0 or choix >= len(ports):
        print("Numero hors plage.")
        sys.exit(1)

    return ports[choix].device


def main():
    print("=" * 60)
    print("Test isole de EnvoiGcodeThread en mode CHARACTER COUNTING")
    print("=" * 60)
    print("")
    print("⚠️  La machine va faire de PETITS MOUVEMENTS (G0).")
    print("⚠️  Laser ETEINT (S0, pas de M3/M4).")
    print("⚠️  Verifie que la zone est DEGAGEE autour de la tete.")
    print("")

    port = choisir_port()

    # --- Connexion ---
    grbl = GrblController()
    try:
        grbl.connecter(port)
    except Exception as e:
        print(f"ERREUR de connexion : {e}")
        sys.exit(1)

    print(f"\nConnecte sur {port}")
    time.sleep(0.5)

    # --- Vider les reponses d'accueil ---
    grbl.reset_buffer()
    time.sleep(0.5)
    for typ, cont in grbl.lire_reponses():
        print(f"  [accueil] {typ} : {cont}")

    # --- QCoreApplication (obligatoire pour les signaux Qt) ---
    app = QCoreApplication(sys.argv)

    # --- Thread d'envoi en mode counting ---
    thread = EnvoiGcodeThread(grbl, GCODE_TEST, utiliser_counting=True)

    # --- Connexion des signaux ---
    def on_progression(numero, total):
        print(f"  [progression] {numero} / {total}")

    def on_ligne(numero, ligne):
        print(f"  [ligne] {numero} : {ligne}")

    def on_termine(succes, message):
        print("")
        print("=" * 60)
        if succes:
            print(f"✅ SUCCES : {message}")
        else:
            print(f"❌ ECHEC : {message}")
        print("=" * 60)
        # Quitter la boucle Qt
        app.quit()

    thread.progression.connect(on_progression)
    thread.ligne_envoyee.connect(on_ligne)
    thread.termine.connect(on_termine)

    print("\n" + "=" * 60)
    print("Lancement de l'envoi en character counting")
    print("=" * 60)

    thread.start()

    # Securite : quitter au bout de 30 secondes max
    QTimer.singleShot(30000, app.quit)

    app.exec()

    # --- Attendre la fin du thread ---
    thread.wait(2000)

    # --- Etat final du buffer ---
    print(f"\nBuffer final : {grbl._buffer_utilise}")
    print(f"FIFO finale : {len(grbl._file_tailles)} lignes")

    # --- Deconnexion ---
    grbl.deconnecter()
    print("\nDeconnecte. Test termine.")


if __name__ == "__main__":
    main()