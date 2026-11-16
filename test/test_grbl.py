# =============================================================================
# test_grbl.py
# -----------------------------------------------------------------------------
# Rôle : Test de la classe GrblController (src/grbl/controller.py).
#        Vérifie : connexion, envoi de commande, lecture statut, déconnexion.
#        Aucun mouvement moteur, aucune modification de paramètre.
#        Cible : COM9 (fraiseuse, cobaye en attendant la laser).
# =============================================================================

import sys
import os

# Ajoute le dossier du script à sys.path pour importer 'src'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.grbl.controller import GrblController


# --- Paramètres du test -------------------------------------------------------
PORT = "COM9"


def main():
    """Déroulé : connexion → commande → statut → déconnexion."""

    ctrl = GrblController()

    # 1) Connexion
    print(f"1) Connexion sur {PORT}...")
    try:
        ctrl.connecter(PORT)
    except Exception as e:
        print(f"   ÉCHEC : {e}")
        return
    print(f"   OK — connecté ? {ctrl.est_connecte}")

    # 2) Envoi d'une commande inoffensive ($$ = afficher les paramètres)
    print("\n2) Envoi de '$$'...")
    lignes = ctrl.envoyer("$$")
    print(f"   {len(lignes)} ligne(s). Dernière : {lignes[-1] if lignes else '(vide)'}")

    # 3) Lecture du statut temps réel
    print("\n3) Lecture du statut...")
    statut = ctrl.lire_statut()
    print(f"   {statut}")

    # 4) Déconnexion
    print("\n4) Déconnexion...")
    ctrl.deconnecter()
    print(f"   OK — connecté ? {ctrl.est_connecte}")


if __name__ == "__main__":
    main()