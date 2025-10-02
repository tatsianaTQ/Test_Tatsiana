# Weekly Data Collector

Ce projet automatise la collecte de données depuis plusieurs pages d'un site web, compile les résultats dans des fichiers CSV et Excel, les archive dans un fichier ZIP, puis envoie ce dernier par e-mail à une liste de destinataires.

L'ensemble du processus est conçu pour être exécuté de manière hebdomadaire via le Planificateur de tâches de Windows.

## Structure du Projet

```
WeeklyDataCollector/
│
├── .venv/                  # Environnement virtuel Python
├── logs/                   # Fichiers de log générés à chaque exécution
├── output/                 # Fichiers CSV, Excel et ZIP générés
├── src/                    # Code source
│   ├── common/             # Modules partagés (configuration Selenium, etc.)
│   └── scrapers/           # Scripts de scraping individuels
│
├── .env                    # Fichier de configuration (identifiants, destinataires)
├── requirements.txt        # Liste des dépendances Python
├── run.py                  # Script principal d'orchestration
└── run.bat                 # Fichier batch pour le lancement via Windows
```

## Prérequis

- Python 3.9+
- Un compte SendGrid (ou un autre service SMTP) pour l'envoi d'e-mails.

## Installation

1.  **Cloner le projet** (ou le créer localement).

2.  **Créer l'environnement virtuel :**
    Ouvrez un terminal dans le dossier du projet et exécutez :
    ```bash
    python -m venv .venv
    ```

3.  **Activer l'environnement virtuel :**
    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

4.  **Installer les dépendances :**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configurer les variables d'environnement :**
    - Créez un fichier nommé `.env` à la racine du projet.
    - Copiez le contenu ci-dessous et remplacez les valeurs par les vôtres.

    ```dotenv
    # .env

    # --- SMTP (SendGrid) ---
    SMTP_SERVER=smtp.sendgrid.net
    SMTP_PORT=587
    SMTP_USER=apikey
    SMTP_PASSWORD=CLE_API_SENDGRID

    # --- Destinataires de l'e-mail ---
    EMAIL_FROM=email@expediteur.com
    EMAIL_TO=destinataire_principal@email.com
    EMAIL_CC=copie1@email.com,copie2@email.com
    ```

## Utilisation

### Exécution Manuelle

Pour tester le script, activez l'environnement virtuel et lancez le script principal :
```bash
python run.py
```
Les logs seront affichés dans la console et enregistrés dans le dossier `/logs`.





