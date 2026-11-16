# diag_imports.py — Test des imports (à supprimer après)
print("Test des imports...")

try:
    from src.core.dxf_loader import Entite, charger_dxf
    print("[OK] dxf_loader")
except Exception as e:
    print(f"[ECHEC] dxf_loader : {e}")

try:
    from src.core.svg_loader import charger_svg
    print("[OK] svg_loader")
except Exception as e:
    print(f"[ECHEC] svg_loader : {e}")

try:
    from src.core.image_loader import charger_image
    print("[OK] image_loader")
except Exception as e:
    print(f"[ECHEC] image_loader : {e}")

try:
    from src.core.dithering_loader import generer_gcode_photo
    print("[OK] dithering_loader")
except Exception as e:
    print(f"[ECHEC] dithering_loader : {e}")

try:
    from src.ui.mise_en_page import MiseEnPageWidget
    print("[OK] mise_en_page")
except Exception as e:
    print(f"[ECHEC] mise_en_page : {e}")

try:
    from src.core.historique import Historique
    print("[OK] historique")
except Exception as e:
    print(f"[ECHEC] historique : {e}")

print("\nTest terminé.")