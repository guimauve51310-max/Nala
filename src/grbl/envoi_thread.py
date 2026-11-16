# =============================================================================
# src/grbl/envoi_thread.py
# -----------------------------------------------------------------------------
# Rôle : Moteur d'envoi de G-code en ARRIERE-PLAN avec support PAUSE/REPRISE.
#
# Deux modes d'envoi :
#   1. run_synchrone() : envoi ligne par ligne, attente du "ok" (comportement
#      historique, fiable mais lent et saccade).
#   2. run_counting()  : envoi en CHARACTER COUNTING GRBL (recommande).
#      Envoie les lignes tant que le buffer GRBL n'est pas plein, lit les
#      reponses en continu, ne bloque pas sur chaque "ok".
#
# Le mode est choisi par l'attribut utiliser_counting (defaut : True).
# Pour regresser : passer utiliser_counting=False au constructeur.
#
# ⚠️ Le suivi marqueur temps reel (position_emise) n'est PAS implemente ici.
#    Il sera ajoute a l'Etape 4 du chantier character counting.
# =============================================================================

import time
from PySide6.QtCore import QThread, Signal


TIMEOUT_LIGNE_DEFAUT = 10.0
GRANULARITE_ATTENTE = 0.1
PAUSE_BOUCLE_COUNTING = 0.001   # 1 ms entre deux iterations de la boucle


class EnvoiGcodeThread(QThread):
    """Thread d'envoi de G-code avec pause / reprise."""

    ligne_envoyee = Signal(int, str)
    termine = Signal(bool, str)
    # NOTE : la progression est desormais pilotee par StatutThread.ok_recu
    #        (approche GRBL officielle : seul le StatutThread lit le port).
    # NOTE : position_emise est retiree (le suivi marqueur passe par le
    #        StatutThread qui lit WPos: dans les rapports de statut).

    def __init__(self, controleur, lignes, timeout_ligne=TIMEOUT_LIGNE_DEFAUT,
                 utiliser_counting=True):
        super().__init__()
        self.controleur = controleur
        self.lignes = lignes
        self.timeout_ligne = timeout_ligne
        self._arret_demande = False
        self._pause_demandee = False
        # Mode character counting (True) ou synchrone (False).
        self.utiliser_counting = utiliser_counting
        # Position absolue en cours (pour le parser G-code).
        # Initialisee a (0, 0) : a ajuster si le G-code commence en G92.
        self._position_courante = (0.0, 0.0)
        # Mode de positionnement : False = absolu (G90), True = relatif (G91).
        # Persiste entre les lignes (contrairement a la variable locale
        # de _parser_position qui etait reinitialisee a chaque appel).
        self._mode_relatif = False

    def arreter(self):
        self._arret_demande = True

    def pause(self):
        self._pause_demandee = True

    def reprendre(self):
        self._pause_demandee = False

    def _est_ligne_utile(self, ligne):
        """Retourne False si la ligne est un commentaire ou vide."""
        s = ligne.strip()
        if not s:
            return False
        if s.startswith(";"):
            return False
        if s.startswith("("):
            return False
        return True

    def _parser_position(self, ligne):
        """
        Parse une ligne G-code et retourne la position cible (x, y)
        apres execution de la ligne, ou None si la ligne ne provoque
        pas de mouvement.

        Gere :
          - G0 / G1 / G2 / G3 avec X et/ou Y
          - G90 (absolu) / G91 (relatif)
          - Ignore : F, S, M, G92, G10, commentaires

        Met a jour self._position_courante.
        """
        # Nettoyer la ligne : retirer les commentaires (; et (...))
        s = ligne.strip()
        if ";" in s:
            s = s.split(";")[0]
        if "(" in s:
            s = s.split("(")[0]
        s = s.strip().upper()
        if not s:
            return None

        # Decouper en mots
        mots = s.split()
        if not mots:
            return None

        # Verifier si c'est un mouvement (G0, G1, G2, G3)
        # et mettre a jour le mode de positionnement (G90 / G91)
        est_mouvement = False
        for mot in mots:
            if mot in ("G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03"):
                est_mouvement = True
            elif mot == "G90":
                self._mode_relatif = False
            elif mot == "G91":
                self._mode_relatif = True

        # Extraire X et Y
        x = None
        y = None
        for mot in mots:
            if mot.startswith("X"):
                try:
                    x = float(mot[1:])
                except ValueError:
                    pass
            elif mot.startswith("Y"):
                try:
                    y = float(mot[1:])
                except ValueError:
                    pass

        # Si pas de X ni Y, pas de mouvement
        if x is None and y is None:
            return None

        # Si ce n'est pas un mouvement mais juste une position (G92, G10),
        # on ignore (pas de deplacement physique)
        if not est_mouvement:
            return None

        # Calculer la nouvelle position (en utilisant le mode PERSISTANT)
        x_act, y_act = self._position_courante
        if self._mode_relatif:
            # Mode relatif (G91)
            if x is not None:
                x_act += x
            if y is not None:
                y_act += y
        else:
            # Mode absolu (G90 ou par defaut)
            if x is not None:
                x_act = x
            if y is not None:
                y_act = y

        self._position_courante = (x_act, y_act)
        return (x_act, y_act)

    def _est_ligne_finale(self, ligne):
        """
        Retourne True si la ligne est une commande de fin de programme
        (M2 ou M30) pour laquelle GRBL ne renvoie PAS de 'ok'.

        Ces lignes doivent etre envoyees a la fin, sans attendre le ok.
        """
        s = ligne.strip().upper()
        # Retirer les commentaires en fin de ligne (; ...)
        if ";" in s:
            s = s.split(";")[0].strip()
        # M2 ou M30 en debut de ligne (ou seuls)
        if s == "M2" or s == "M30":
            return True
        # M2/M30 avec d'autres parametres (ex: "M30 S1000")
        if s.startswith("M2 ") or s.startswith("M30 "):
            return True
        # Cas ou M2/M30 est au milieu (ex: "G0 X0 M30")
        if " M2" in s or " M30" in s:
            # Verifier que ce n'est pas M20, M200, etc.
            import re
            if re.search(r"\bM(2|30)\b", s):
                return True
        return False

    # -------------------------------------------------------------------------
    # Point d'entree : dispatch selon le mode
    # -------------------------------------------------------------------------

    def run(self):
        if self.utiliser_counting:
            self.run_counting()
        else:
            self.run_synchrone()

    # -------------------------------------------------------------------------
    # Mode synchrone (historique)
    # -------------------------------------------------------------------------

    def run_synchrone(self):
        """Envoi ligne par ligne, attente du ok pour chaque ligne."""
        lignes_utiles = [l for l in self.lignes if self._est_ligne_utile(l)]
        total = len(lignes_utiles)

        if total == 0:
            self.termine.emit(True, "Fichier vide, rien a envoyer.")
            return

        for i, ligne in enumerate(lignes_utiles, start=1):
            # Arret total
            if self._arret_demande:
                self.termine.emit(
                    False,
                    f"Envoi interrompu par l'utilisateur (ligne {i}/{total})."
                )
                return

            # Attente pause
            while self._pause_demandee and not self._arret_demande:
                time.sleep(GRANULARITE_ATTENTE)

            if self._arret_demande:
                self.termine.emit(
                    False,
                    f"Envoi interrompu par l'utilisateur (ligne {i}/{total})."
                )
                return

            # Envoi synchrone : write + attente 'ok'
            try:
                reponses = self.controleur.envoyer(ligne, timeout=self.timeout_ligne)
            except Exception as e:
                self.termine.emit(False, f"Erreur d'envoi ligne {i} : {e}")
                return

            # Detection erreur GRBL
            for r in reponses:
                if r.startswith("error"):
                    self.termine.emit(
                        False,
                        f"Erreur GRBL ligne {i} : {r}  (commande : {ligne})"
                    )
                    return

            self.ligne_envoyee.emit(i, ligne)
            if i == 1 or i % 5 == 0 or i == total:
                self.progression.emit(i, total)

        self.termine.emit(True, f"Envoi termine : {total} lignes.")

    # -------------------------------------------------------------------------
    # Mode character counting
    # -------------------------------------------------------------------------

    def run_counting(self):
        """
        Envoi en CHARACTER COUNTING GRBL.

        Principe :
          - Envoyer les lignes tant que le buffer GRBL n'est pas plein.
          - Lire les reponses (ok, error) en continu.
          - Ne PAS envoyer de "?" pendant l'envoi (evite le laser saccade).
          - S'arreter sur STOP, pause, ou erreur.
        """
        lignes_utiles = [l for l in self.lignes if self._est_ligne_utile(l)]

        # Separer les lignes en deux groupes :
        #   - normales : on attend le ok
        #   - finales (M2/M30) : on les envoie a la fin, sans attendre le ok
        lignes_normales = [l for l in lignes_utiles
                           if not self._est_ligne_finale(l)]
        lignes_finales = [l for l in lignes_utiles
                          if self._est_ligne_finale(l)]

        total = len(lignes_normales)
        total_finales = len(lignes_finales)

        # Reinitialise le buffer du controleur
        try:
            self.controleur.reset_buffer()
        except Exception:
            pass

        if total == 0:
            # Cas particulier : que des lignes finales
            for ligne in lignes_finales:
                self.controleur.envoyer_async(ligne)
                self.ligne_envoyee.emit(1, ligne)
            self.termine.emit(True, "Envoi termine (0 lignes normales).")
            return

        # On va utiliser lignes_utiles = lignes_normales pour la boucle
        lignes_utiles = lignes_normales

        envoyees = 0   # index de la prochaine ligne a envoyer
        recues = 0     # nombre de ok recus
        erreur = None

        # --- Boucle principale ---
        while recues < total and erreur is None:
            # Arret total
            if self._arret_demande:
                erreur = (f"Envoi interrompu par l'utilisateur "
                          f"({recues}/{total}).")
                break

            # Attente pause
            if self._pause_demandee:
                time.sleep(GRANULARITE_ATTENTE)
                continue

            # --- Envoi tant qu'il y a de la place dans le buffer ---
            while envoyees < total and erreur is None:
                if self._arret_demande or self._pause_demandee:
                    break

                ligne = lignes_utiles[envoyees]
                taille = len(ligne) + 1  # +1 pour le \n

                if not self.controleur.buffer_libre(taille):
                    break  # buffer plein, on attend un ok

                if not self.controleur.envoyer_async(ligne):
                    erreur = f"Echec envoi ligne {envoyees + 1}"
                    break

                envoyees += 1
                self.ligne_envoyee.emit(envoyees, ligne)

            # --- Lecture des compteurs (le port est lu par StatutThread) ---
            # Le StatutThread, seul lecteur du port, incremente nb_ok_recus()
            # et nb_erreurs_recues() a chaque "ok" / "error" recu.
            try:
                nouvelles_recues = self.controleur.nb_ok_recus()
                nouvelles_erreurs = self.controleur.nb_erreurs_recues()
            except Exception as e:
                erreur = f"Erreur lecture compteurs : {e}"
                break

            # Mettre a jour recues (utile pour la suite : envoi tant que
            # le buffer n'est pas plein).
            recues = nouvelles_recues

            # Detection d'erreur GRBL
            if nouvelles_erreurs > 0:
                erreur = (f"Erreur GRBL ({recues + 1}/{total}) : "
                          f"voir console pour le detail.")
                break

            # Petite pause pour ne pas saturer le CPU
            time.sleep(PAUSE_BOUCLE_COUNTING)

        # --- Attente des derniers ok (buffer qui se vide) ---
        if erreur is None:
            while recues < envoyees:
                if self._arret_demande:
                    erreur = f"Envoi interrompu ({recues}/{total})."
                    break
                try:
                    recues = self.controleur.nb_ok_recus()
                    erreurs_total = self.controleur.nb_erreurs_recues()
                except Exception as e:
                    erreur = f"Erreur lecture finale : {e}"
                    break
                if erreurs_total > 0:
                    erreur = "Erreur GRBL finale : voir console pour le detail."
                    break
                time.sleep(PAUSE_BOUCLE_COUNTING)

        # --- Envoi des lignes finales (M2/M30) sans attendre le ok ---
        if erreur is None and lignes_finales:
            try:
                time.sleep(0.1)  # petite pause pour que GRBL finisse le buffer
                for ligne in lignes_finales:
                    self.controleur.envoyer_async(ligne)
                    self.ligne_envoyee.emit(total + 1, ligne)
            except Exception:
                pass

        # --- Emission du resultat ---
        if erreur:
            self.termine.emit(False, erreur)
        else:
            msg = f"Envoi termine : {recues} lignes"
            if total_finales > 0:
                msg += f" (+ {total_finales} ligne(s) finale(s))"
            msg += "."
            self.termine.emit(True, msg)
