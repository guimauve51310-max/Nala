# =============================================================================
# test_parser.py
# -----------------------------------------------------------------------------
# Rôle : Test isolé du parser G-code (_parser_position) dans EnvoiGcodeThread.
#
# Ce script :
#   1. Instancie un EnvoiGcodeThread factice (sans machine)
#   2. Teste le parser sur une serie de lignes G-code connues
#   3. Verifie que les positions extraites sont correctes
#
# Usage : env/Scripts/python.exe test_parser.py
# =============================================================================

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.grbl.envoi_thread import EnvoiGcodeThread


# --- Cas de test : (ligne, position attendue ou None) ------------------------
CAS_TESTS = [
    # (ligne, position attendue apres execution)
    ("G21",                         None),         # mm, pas de mouvement
    ("G90",                         None),         # absolu, pas de mouvement
    ("G0 X10 Y0",                   (10.0, 0.0)),
    ("G0 X10 Y10",                  (10.0, 10.0)),
    ("G1 X0",                       (0.0, 10.0)),  # seul X change, Y reste
    ("G1 Y0",                       (0.0, 0.0)),   # seul Y change
    ("G1 F500",                     None),         # vitesse seule
    ("M3 S100",                     None),         # laser, pas de mouvement
    ("G1 X5 Y5",                    (5.0, 5.0)),
    ("G91",                         None),         # passage en relatif
    ("G1 X2 Y3",                    (7.0, 8.0)),   # relatif
    ("G90",                         None),         # retour en absolu
    ("G1 X10 Y10 ; commentaire",    (10.0, 10.0)), # avec commentaire
    ("G1 X20 Y20 (autre comm)",     (20.0, 20.0)), # avec commentaire ()
    ("S0",                          None),         # laser off
    ("M5",                          None),         # laser off
    ("G0",                          None),         # pas de coordonnees
    ("G92 X0 Y0",                   None),         # G92 ignore
    ("G10 L20 P1 X0 Y0",            None),         # G10 ignore
]


def main():
    print("=" * 60)
    print("Test isole du parser G-code (_parser_position)")
    print("=" * 60)

    # --- Instancier un thread factice (sans machine) ---
    # On passe un controleur None, on n'appellera pas ses methodes.
    thread = EnvoiGcodeThread(None, [], utiliser_counting=True)

    nb_ok = 0
    nb_erreurs = 0

    print("\nTest des lignes une par une :\n")

    for i, (ligne, attendu) in enumerate(CAS_TESTS, start=1):
        resultat = thread._parser_position(ligne)

        # Comparer avec tolerance
        if attendu is None:
            ok = resultat is None
        else:
            if resultat is None:
                ok = False
            else:
                ok = (abs(resultat[0] - attendu[0]) < 0.001 and
                      abs(resultat[1] - attendu[1]) < 0.001)

        if ok:
            nb_ok += 1
            symbole = "OK "
        else:
            nb_erreurs += 1
            symbole = "ERR"

        print(f"  [{symbole}] [{i:2d}] {ligne!r}")
        print(f"         attendu : {attendu}")
        print(f"         obtenu  : {resultat}")
        print(f"         position courante : {thread._position_courante}")
        print()

    print("=" * 60)
    print(f"Resultat : {nb_ok} OK, {nb_erreurs} erreurs sur {len(CAS_TESTS)} tests.")
    print("=" * 60)

    if nb_erreurs > 0:
        print("\n⚠️  Il y a des erreurs. Verifier le parser.")
        sys.exit(1)
    else:
        print("\n✅ Tous les tests passent. Le parser est OK.")
        print("On peut passer a l'Etape 4b (emission position_emise).")


if __name__ == "__main__":
    main()