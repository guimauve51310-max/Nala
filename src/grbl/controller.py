# =============================================================================
# src/grbl/controller.py
# -----------------------------------------------------------------------------
# Rôle : Encapsule toute la communication avec une carte GRBL.
#
# Version RESTAUREE : envoi synchrone uniquement (envoyer + attente ok).
# Les methodes ecrire_ligne / lire_reponse (pour le buffering) ont ete
# retirees.
# =============================================================================

import time
import threading
import serial


class GrblController:
    """Controleur de communication avec une carte GRBL."""

    BAUDRATE_DEFAUT = 115200

    def __init__(self, baudrate=BAUDRATE_DEFAUT):
        self.baudrate = baudrate
        self.serial = None
        self._verrou_ecriture = threading.Lock()

        # --- Character counting GRBL ---
        # Buffer GRBL : 127 caracteres (128 octets avec le null terminal).
        # _buffer_utilise : nombre d'octets actuellement dans le buffer GRBL.
        # _file_tailles   : FIFO des tailles de lignes en attente d'un "ok".
        #                   A chaque "ok" recu, on retire la premiere taille
        #                   et on decremente _buffer_utilise.
        self._buffer_utilise = 0
        self._file_tailles = []

        # --- Compteurs d'acquittements (thread-safe) ---
        # _nb_ok_recus       : nombre total de "ok" recus depuis le dernier reset.
        # _nb_erreurs_recues : nombre total d'"error" recues depuis le dernier reset.
        # Proteges par _verrou_compteur (different de _verrou_ecriture).
        self._verrou_compteur = threading.Lock()
        self._nb_ok_recus = 0
        self._nb_erreurs_recues = 0

    # -------------------------------------------------------------------------
    # Connexion / deconnexion
    # -------------------------------------------------------------------------

    def connecter(self, port):
        self.serial = serial.Serial(port, self.baudrate, timeout=0.2)
        time.sleep(2)
        self.serial.reset_input_buffer()
        return True

    def deconnecter(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.serial = None

    @property
    def est_connecte(self):
        return self.serial is not None and self.serial.is_open

    # -------------------------------------------------------------------------
    # Envoi de commandes
    # -------------------------------------------------------------------------

    def envoyer(self, commande, attendre_ok=True, timeout=3.0):
        # Envoie une commande terminee par \n et lit la reponse.
        if not self.est_connecte:
            raise RuntimeError("Non connecte : appelez connecter() d'abord.")

        with self._verrou_ecriture:
            self.serial.write((commande + "\n").encode())

        lignes = []
        fin = time.time() + timeout

        while time.time() < fin:
            ligne = self.serial.readline().decode(errors="ignore").strip()
            if not ligne:
                continue

            lignes.append(ligne)

            if attendre_ok and (ligne == "ok" or ligne.startswith("error")):
                break

        return lignes

    def envoyer_octet_immediat(self, octet):
        # Envoie un octet brut sans \n (Ctrl-X, !, ~).
        if not self.est_connecte:
            return
        with self._verrou_ecriture:
            self.serial.write(bytes([octet]))

    # -------------------------------------------------------------------------
    # Character counting GRBL
    # -------------------------------------------------------------------------

    def reset_buffer(self):
        """Remet le compteur de buffer a zero (a appeler apres un reset GRBL)."""
        self._buffer_utilise = 0
        self._file_tailles = []
        with self._verrou_compteur:
            self._nb_ok_recus = 0
            self._nb_erreurs_recues = 0

    def buffer_libre(self, taille_ligne):
        """
        Retourne True si on peut envoyer une ligne de taille donnee
        sans depasser le buffer GRBL (127 chars).

        On prend une marge d'un octet pour le "\n" terminal.
        """
        return (self._buffer_utilise + taille_ligne + 1) <= 127

    def envoyer_async(self, ligne):
        """
        Ecrit une ligne SANS attendre le ok (mode character counting).
        Incremente _buffer_utilise et ajoute la taille a la FIFO.

        Retourne True si l'ecriture a reussi, False sinon.
        """
        if not self.est_connecte:
            return False
        try:
            octets = (ligne + "\n").encode()
            with self._verrou_ecriture:
                self.serial.write(octets)
                self._buffer_utilise += len(octets)
                self._file_tailles.append(len(octets))
            return True
        except Exception:
            return False

    def lire_reponses(self):
        """
        Lit toutes les reponses disponibles (non bloquant).
        Retourne une liste de tuples (type, contenu) :
          ("ok", None)             -> acquittement d'une ligne
          ("error", "error:2")     -> erreur GRBL
          ("statut", "<Idle|...>") -> rapport de statut
          ("autre", "...")         -> autre (message d'accueil, etc.)

        Decremente _buffer_utilise a chaque ok recu (via la FIFO).
        """
        reponses = []
        if not self.est_connecte:
            return reponses

        try:
            with self._verrou_ecriture:
                while self.serial.in_waiting > 0:
                    try:
                        ligne = self.serial.readline().decode(
                            errors="ignore").strip()
                    except Exception:
                        break
                    if not ligne:
                        continue

                    if ligne == "ok":
                        # Decremente le compteur avec la 1ere taille de la FIFO
                        if self._file_tailles:
                            taille = self._file_tailles.pop(0)
                            self._buffer_utilise -= taille
                            if self._buffer_utilise < 0:
                                self._buffer_utilise = 0
                        reponses.append(("ok", None))
                    elif ligne.startswith("error"):
                        # En cas d'erreur, on retire aussi une ligne de la FIFO
                        # (la ligne qui a provoque l'erreur a ete rejetee)
                        if self._file_tailles:
                            taille = self._file_tailles.pop(0)
                            self._buffer_utilise -= taille
                            if self._buffer_utilise < 0:
                                self._buffer_utilise = 0
                        reponses.append(("error", ligne))
                    elif ligne.startswith("<") and ligne.endswith(">"):
                        reponses.append(("statut", ligne))
                    else:
                        reponses.append(("autre", ligne))
        except Exception:
            pass

        return reponses

    def demander_statut(self):
        """
        Envoie juste le caractere "?" (0x3F) pour demander un rapport de statut.
        N'attend AUCUNE reponse : c'est lire_et_dispatcher() qui lira, dans
        le thread de statut dedie (approche GRBL officielle, 5 Hz max).
        """
        if not self.est_connecte:
            return
        try:
            with self._verrou_ecriture:
                self.serial.write(b"?")
        except Exception:
            pass

    def lire_et_dispatcher(self):
        """
        Identique a lire_reponses() mais incremente aussi les compteurs
        thread-safe _nb_ok_recus / _nb_erreurs_recues.

        Cette methode est appelee par le StatutThread (seul lecteur du port).
        Elle retourne la liste des tuples (type, contenu) comme lire_reponses().

        Types retournes :
          ("ok", None)
          ("error", "error:N")
          ("statut", "<...>")
          ("autre", "...")
        """
        reponses = []
        if not self.est_connecte:
            return reponses

        try:
            with self._verrou_ecriture:
                while self.serial.in_waiting > 0:
                    try:
                        ligne = self.serial.readline().decode(
                            errors="ignore").strip()
                    except Exception:
                        break
                    if not ligne:
                        continue

                    if ligne == "ok":
                        if self._file_tailles:
                            taille = self._file_tailles.pop(0)
                            self._buffer_utilise -= taille
                            if self._buffer_utilise < 0:
                                self._buffer_utilise = 0
                        with self._verrou_compteur:
                            self._nb_ok_recus += 1
                        reponses.append(("ok", None))
                    elif ligne.startswith("error"):
                        if self._file_tailles:
                            taille = self._file_tailles.pop(0)
                            self._buffer_utilise -= taille
                            if self._buffer_utilise < 0:
                                self._buffer_utilise = 0
                        with self._verrou_compteur:
                            self._nb_erreurs_recues += 1
                        reponses.append(("error", ligne))
                    elif ligne.startswith("<") and ligne.endswith(">"):
                        reponses.append(("statut", ligne))
                    else:
                        reponses.append(("autre", ligne))
        except Exception:
            pass

        return reponses

    def nb_ok_recus(self):
        """Retourne le nombre total de "ok" recus (thread-safe)."""
        with self._verrou_compteur:
            return self._nb_ok_recus

    def nb_erreurs_recues(self):
        """Retourne le nombre total d'"error" recues (thread-safe)."""
        with self._verrou_compteur:
            return self._nb_erreurs_recues

    # -------------------------------------------------------------------------
    # Lecture du statut temps reel (ancienne methode, conservee pour regression)
    # -------------------------------------------------------------------------

    def lire_statut(self):
        # Envoie "?" et renvoie la ligne de statut brute.
        if not self.est_connecte:
            return None
        with self._verrou_ecriture:
            self.serial.write(b"?")
        return self.serial.readline().decode(errors="ignore").strip() or None
