# =============================================================================
# src/grbl/statut_thread.py
# -----------------------------------------------------------------------------
# Rôle : Thread de statut temps réel (approche GRBL officielle).
#
# Principe :
#   - Tourne en PERMANENCE tant que le port est ouvert.
#   - Envoie "?" toutes les 200 ms (5 Hz, recommandation officielle GRBL).
#   - Est le SEUL lecteur du port série (le thread d'envoi n'y touche plus).
#   - Redispatch tout ce qu'il lit :
#       "<...>"   -> signal statut_recu   (ligne brute)
#       "ok"      -> signal ok_recu       (nouveau total de ok recus)
#       "error:N" -> signal erreur_recue  (ligne brute)
#       "autre"   -> signal autre_recu    (messages d'accueil, etc.)
#
# Le comptage des "ok" (character counting) est fait dans le controleur
# (GrblController.lire_et_dispatcher) : c'est lui qui decremente le buffer
# et incremente les compteurs thread-safe. Ce thread ne fait que relayer.
# =============================================================================

import time
from PySide6.QtCore import QThread, Signal


# Intervalle entre deux "?" (200 ms = 5 Hz, recommandation officielle GRBL).
INTERVALLE_STATUT = 0.2

# Granularite de la boucle (20 ms = 50 Hz).
# Largement suffisant pour capter les "ok" de GRBL en pratique.
GRANULARITE_BOUCLE = 0.02


class StatutThread(QThread):
    """
    Thread de statut permanent : envoie "?" a 5 Hz et lit en continu.

    Signaux :
      statut_recu(str)  : ligne "<...>" brute recue de GRBL
      ok_recu(int)      : nouveau total de "ok" recus (pour la progression)
      erreur_recue(str) : ligne "error:N" recue
      autre_recu(str)   : toute autre ligne (accueil, message, etc.)
    """

    statut_recu = Signal(str)
    ok_recu = Signal(int)
    erreur_recue = Signal(str)
    autre_recu = Signal(str)

    def __init__(self, controleur):
        super().__init__()
        self.controleur = controleur
        self._arret_demande = False

    def arreter(self):
        """Demande l'arret du thread (la boucle sortira a la prochaine iteration)."""
        self._arret_demande = True

    def run(self):
        """
        Boucle principale :
          - Envoie "?" si l'intervalle est ecoule.
          - Lit tout ce qui est disponible et redispatch via signaux.
          - Dort un court instant pour ne pas saturer le CPU.
        """
        prochain_statut = time.time()

        while not self._arret_demande:
            maintenant = time.time()

            # 1) Envoyer "?" si l'intervalle est ecoule
            if maintenant >= prochain_statut:
                try:
                    self.controleur.demander_statut()
                except Exception:
                    pass
                prochain_statut = maintenant + INTERVALLE_STATUT

            # 2) Lire tout ce qui est disponible et redispatch
            try:
                reponses = self.controleur.lire_et_dispatcher()
            except Exception:
                reponses = []

            for typ, cont in reponses:
                if typ == "statut":
                    self.statut_recu.emit(cont)
                elif typ == "ok":
                    # On relit le total courant (thread-safe) pour info.
                    try:
                        total = self.controleur.nb_ok_recus()
                    except Exception:
                        total = 0
                    self.ok_recu.emit(total)
                elif typ == "error":
                    self.erreur_recue.emit(cont)
                else:
                    self.autre_recu.emit(cont)

            # 3) Petite pause pour ne pas saturer le CPU
            time.sleep(GRANULARITE_BOUCLE)
