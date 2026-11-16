from PySide6.QtCore import QTranslator, QCoreApplication
import sys

app = QCoreApplication(sys.argv)
traducteur = QTranslator()
if traducteur.load("src/i18n/nala_en.qm"):
    app.installTranslator(traducteur)
    print("Traducteur chargé.\n")

    textes = [
        "Masques de travail",
        "Transformations (redim, position, rotation, miroir)",
        "Projet (zone, origine)",
        "Annuler la derniere action (Ctrl+Z)",
        "Refaire la derniere action annulee (Ctrl+Y)",
    ]
    for t in textes:
        traduit = QCoreApplication.translate("MiseEnPageWidget", t)
        print(f"'{t}' -> '{traduit}'")
else:
    print("Erreur : impossible de charger le .qm")