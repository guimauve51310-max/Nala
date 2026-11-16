import sys
import ast
import re

FICHIER = "src/ui/mise_en_page.py"

def main():
    with open(FICHIER, "r", encoding="utf-8") as f:
        code = f.read()

    # On remplace la classe pour augmenter la largeur des champs
    pattern = r"class BarreFlottanteTransformations\(QWidget\):.*?self\.hide\(\) # Cachée par défaut"
    
    nouvelle_classe = '''class BarreFlottanteTransformations(QWidget):
    """
    Barre flottante de transformations.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BarreFlottante")
        
        self.setStyleSheet("""
            QWidget#BarreFlottante {
                background-color: #2c3e50;
                border: 2px solid #1a252f;
                border-radius: 6px;
            }
            QDoubleSpinBox {
                background-color: #ffffff;
                color: #2c3e50;
                border: 1px solid #7f8c8d;
                border-radius: 3px;
                padding: 2px 4px;
                font-family: Consolas, monospace;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.setFixedHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        # Champ X (Élargi à 140)
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setPrefix("X: ")
        self.spin_x.setSuffix(" mm")
        self.spin_x.setRange(-9999, 9999)
        self.spin_x.setDecimals(2)
        self.spin_x.setFixedWidth(140)
        layout.addWidget(self.spin_x)

        # Champ Y (Élargi à 140)
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setPrefix("Y: ")
        self.spin_y.setSuffix(" mm")
        self.spin_y.setRange(-9999, 9999)
        self.spin_y.setDecimals(2)
        self.spin_y.setFixedWidth(140)
        layout.addWidget(self.spin_y)

        # Champ Largeur (Élargi à 140)
        self.spin_w = QDoubleSpinBox()
        self.spin_w.setPrefix("L: ")
        self.spin_w.setSuffix(" mm")
        self.spin_w.setRange(0.1, 9999)
        self.spin_w.setDecimals(2)
        self.spin_w.setFixedWidth(140)
        layout.addWidget(self.spin_w)

        # Champ Hauteur (Élargi à 140)
        self.spin_h = QDoubleSpinBox()
        self.spin_h.setPrefix("H: ")
        self.spin_h.setSuffix(" mm")
        self.spin_h.setRange(0.1, 9999)
        self.spin_h.setDecimals(2)
        self.spin_h.setFixedWidth(140)
        layout.addWidget(self.spin_h)

        # Bouton Appliquer
        self.btn_appliquer = QPushButton("Appliquer")
        layout.addWidget(self.btn_appliquer)

        self.hide() # Cachée par défaut'''

    code, nb = re.subn(pattern, nouvelle_classe, code, flags=re.DOTALL)
    if nb == 0:
        print("❌ ÉCHEC : impossible de remplacer la classe.")
        sys.exit(1)

    with open(FICHIER, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        ast.parse(code)
        print("✅ Barre flottante élargie avec succès.")
    except SyntaxError as e:
        print(f"❌ Erreur de syntaxe : {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()