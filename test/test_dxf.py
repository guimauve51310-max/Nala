# =============================================================================
# test_dxf.py
# -----------------------------------------------------------------------------
# Rôle : Test du lecteur DXF (src/core/dxf_loader.py) SANS interface graphique.
#
# Ce script :
#   1) Génère un fichier DXF de test avec ezdxf (carré + cercle + arc)
#   2) Le relit avec notre fonction charger_dxf()
#   3) Affiche en console les entités trouvées
#
# Objectif : valider que la lecture DXF fonctionne, avant d'attaquer l'onglet
# de mise en page. On débogue ici, en console, c'est plus simple.
# =============================================================================

import sys
import os

# Ajoute le dossier du script à sys.path pour importer 'src'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ezdxf
from src.core.dxf_loader import charger_dxf


# --- Emplacement du fichier de test (à côté du script) ------------------------
CHEMIN_TEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "dxf_test.dxf")


def generer_dxf_de_test(chemin):
    """
    Crée un petit DXF de test avec quelques entités de base :
      - une LWPOLYLINE (carré 40×40)
      - un CIRCLE (rayon 15, au centre du carré)
      - un ARC (demi-cercle, au-dessus du carré)
      - une LINE (trait horizontal en bas)
    Le tout réparti sur 2 calques : "DECOUPE" et "GRAVURE".
    """
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()

    # On crée deux calques pour tester la gestion du nom de calque
    doc.layers.add("DECOUPE", color=1)   # rouge
    doc.layers.add("GRAVURE", color=5)   # bleu

    # --- Carré (sur calque DECOUPE) ---
    carre = msp.add_lwpolyline(
        [(0, 0), (40, 0), (40, 40), (0, 40)],
        close=True,
        dxfattribs={"layer": "DECOUPE"},
    )

    # --- Cercle au centre du carré (sur calque GRAVURE) ---
    msp.add_circle(
        center=(20, 20),
        radius=10,
        dxfattribs={"layer": "GRAVURE"},
    )

    # --- Arc demi-cercle, au-dessus du carré (sur calque DECOUPE) ---
    msp.add_arc(
        center=(20, 40),
        radius=15,
        start_angle=0,
        end_angle=180,
        dxfattribs={"layer": "DECOUPE"},
    )

    # --- Ligne simple sous le carré (sur calque GRAVURE) ---
    msp.add_line(
        start=(-10, -10),
        end=(50, -10),
        dxfattribs={"layer": "GRAVURE"},
    )

    doc.saveas(chemin)
    print(f"→ DXF de test généré : {chemin}")


def main():
    print("=== Test du lecteur DXF ===\n")

    # 1) Génération du DXF de test
    generer_dxf_de_test(CHEMIN_TEST)

    # 2) Lecture avec notre loader
    print("\n→ Chargement via src.core.dxf_loader.charger_dxf()...\n")
    entites, warnings = charger_dxf(CHEMIN_TEST)

    # 3) Affichage des résultats
    print(f"Nombre d'entités lues : {len(entites)}\n")
    for i, e in enumerate(entites, start=1):
        # On affiche le type d'origine, le nombre de points, le calque,
        # et les coordonnées du premier et dernier point (pour vérifier
        # que la géométrie est cohérente).
        premier = e.points[0]
        dernier = e.points[-1]
        print(f"  [{i}] {e.type_origine:12s}  pts={len(e.points):3d}  "
              f"calque={e.calque:8s}  "
              f"de {premier} à {dernier}")

    # 4) Warnings éventuels
    if warnings:
        print("\nWarnings :")
        for w in warnings:
            print(f"  ⚠ {w}")
    else:
        print("\nAucun warning.")

    print("\n=== Fin du test ===")


if __name__ == "__main__":
    main()