# 🐱 Nala (ex-LaserCNC)

![Logo Nala](nala.png) <!-- Remplace "nala.png" par le nom de ton image quand tu l'auras -->

**Nala** est un logiciel open-source, gratuit et intuitif pour piloter votre découpeuse ou graveuse laser (compatible GRBL). Conçu pour être simple, il offre des fonctionnalités avancées pour préparer vos projets, de la vectorisation d'images à la génération de G-code.

> *En mémoire de Nala, le chat de l'utilisateur. 🐱*

**Nala** is a free and open-source, intuitive software to control your laser cutter or engraver (GRBL compatible). Designed to be simple, it provides advanced features to prepare your projects, from image vectorization to G-code generation.

---

## 🇫🇷 Français

### ✨ Fonctionnalités
*   **Contrôle machine** : Connexion série GRBL, jog manuel, arrêt d'urgence, point laser, pause/reprise, ajustement de la vitesse et de la puissance en temps réel.
*   **Mise en page avancée** : Importation DXF et SVG, gestion de masques de travail, transformations complètes (déplacement, redimensionnement, rotation, miroir), duplication, verrouillage.
*   **Sélection fine** : Sélection par type, groupement, navigation au clavier (Tab), annuler/rétablir (Undo/Redo) complet.
*   **Préparation de rendu** : Mode Contour (Line), Remplissage (Fill) ou les deux (Line+Fill), avec gestion des trous et de l'ordre de coupe.
*   **Onglet Photo** : Vectorisation d'images (JPG/PNG), détourage automatique, et dithering avancé (Floyd-Steinberg, Jarvis, Stucki, Atkinson, Bayer).
*   **Personnalisation** : Interface multilingue (Français / Anglais), 3 thèmes (Clair, Sombre, Coloré), polices de gravure embarquées.
*   **Calibration** : Outils intégrés pour tester et calibrer votre machine (tests carrés, matrices P×V).

### 🚀 Installation
1. Clonez le dépôt : `git clone https://github.com/votre-nom/nala.git`
2. Créez un environnement virtuel : `python -m venv env`
3. Activez-le (Windows) : `env\Scripts\activate`
4. Installez les dépendances : `pip install -r requirements.txt`
5. Lancez l'application : `python LaserCNC.py`

### 📜 Licence
Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

---

## 🇬🇧 English

### ✨ Features
*   **Machine Control**: GRBL serial connection, manual jog, emergency stop, laser pointer, pause/resume, real-time speed and power overrides.
*   **Advanced Layout**: DXF and SVG imports, work mask management, full transformations (move, resize, rotate, mirror), duplication, locking.
*   **Fine Selection**: Select by type, grouping, keyboard navigation (Tab), full Undo/Redo support.
*   **Render Preparation**: Outline (Line), Fill, or Both (Line+Fill) modes, with hole management and cut order.
*   **Photo Tab**: Image vectorization (JPG/PNG), automatic outline/detourage, and advanced dithering (Floyd-Steinberg, Jarvis, Stucki, Atkinson, Bayer).
*   **Customization**: Multilingual interface (French / English), 3 themes (Light, Dark, Colorful), embedded engraving fonts.
*   **Calibration**: Built-in tools to test and calibrate your machine (test squares, P×V matrices).

### 🚀 Installation
1. Clone the repository: `git clone https://github.com/your-name/nala.git`
2. Create a virtual environment: `python -m venv env`
3. Activate it (Windows): `env\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Run the application: `python LaserCNC.py`

### 📜 License
This project is licensed under the MIT License. See the `LICENSE` file for details.

---
*Développé avec passion pour la communauté laser.*