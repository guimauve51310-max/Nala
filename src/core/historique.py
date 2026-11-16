# =============================================================================
# src/core/historique.py
# -----------------------------------------------------------------------------
# Rôle : Gestionnaire d'historique pour Undo/Redo (Ctrl+Z / Ctrl+Y).
#
# Principe (Approche Snapshot) :
#   - On stocke une "photo" (deepcopy) du projet à chaque action.
#   - On garde une pile d'états (max 50 pour ne pas saturer la RAM).
#   - Undo = on recule dans la pile.
#   - Redo = on avance dans la pile.
#
# Ce module N'AFFICHE RIEN et NE PARLE PAS À LA MACHINE.
# =============================================================================

import copy

# Nombre maximum d'états gardés en mémoire
MAX_ETATS = 50


class Historique:
    """
    Gère l'historique des états du projet.
    """

    def __init__(self):
        self.etats = []        # Liste des états (dicts)
        self.index_actuel = -1 # Index de l'état courant
        self._en_train_de_charger = False

    def est_vide(self):
        """Retourne True si l'historique est vide."""
        return len(self.etats) == 0

    def peut_annuler(self):
        """Retourne True si on peut faire un Undo."""
        return self.index_actuel > 0

    def peut_refaire(self):
        """Retourne True si on peut faire un Redo."""
        return self.index_actuel < len(self.etats) - 1

    def ajouter_etat(self, etat_projet):
        """
        Ajoute un nouvel état à l'historique.
        
        ⚠️ On ne l'ajoute que si on n'est pas en train de charger
        (pour éviter de créer un état pendant un Undo/Redo).
        """
        if self._en_train_de_charger:
            return

        # Si on est au milieu de la pile (après un Undo), on coupe le futur
        if self.index_actuel < len(self.etats) - 1:
            self.etats = self.etats[:self.index_actuel + 1]

        # Deepcopy pour isoler l'état (sinon les modifs futures l'affectent)
        # On utilise copy.deepcopy pour être sûr que tout est isolé.
        try:
            etat_copie = copy.deepcopy(etat_projet)
            self.etats.append(etat_copie)
        except Exception as e:
            print(f"[Historique] Erreur de copie (deepcopy) : {e}")
            return

        # Limiter la taille de l'historique
        if len(self.etats) > MAX_ETATS:
            self.etats.pop(0)
        else:
            self.index_actuel += 1

    def annuler(self):
        """
        Recule d'un état. Retourne l'état précédent (ou None si impossible).
        """
        if not self.peut_annuler():
            return None

        self.index_actuel -= 1
        self._en_train_de_charger = True
        return copy.deepcopy(self.etats[self.index_actuel])

    def refaire(self):
        """
        Avance d'un état. Retourne l'état suivant (ou None si impossible).
        """
        if not self.peut_refaire():
            return None

        self.index_actuel += 1
        self._en_train_de_charger = True
        return copy.deepcopy(self.etats[self.index_actuel])

    def fin_chargement(self):
        """À appeler après un Undo/Redo pour réactiver l'enregistrement."""
        self._en_train_de_charger = False

    def vider(self):
        """Vide l'historique (ex: quand on charge un nouveau projet)."""
        self.etats = []
        self.index_actuel = -1
        self._en_train_de_charger = False