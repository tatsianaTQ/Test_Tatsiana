# run.py

import subprocess
from datetime import datetime
from pathlib import Path
import zipfile
import time
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv
from typing import Tuple, List, Optional

# --- CONFIGURATION ---

PYTHON_EXECUTABLE = "python"
SCRIPTS_TO_RUN = [
    #"src/scrapers/1_page_acceuil_carrousels_card_voir_plus.py",
    #"src/scrapers/2_page_en_vedette_carrousels_card_voir_plus.py",
    #"src/scrapers/3_page_jeunesse_carrousels_card_voir_plus.py",
    "src/scrapers/4_page_sur_demande_carrousels_card_voir_plus.py",
]
OUTPUT_DIR = Path("output")
LOG_DIR = Path("logs")
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


# --- LOGGING SETUP ---

def setup_logging():
    """Configure logging to file and console."""
    log_filename = LOG_DIR / f"run_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()  # To also print to console
        ]
    )


# --- SCRIPT LOGIC ---

def run_scraper(script_path: str) -> bool:
    """Exécute un script de scraping en tant que module et attend sa fin."""
    if not Path(script_path).exists():
        logging.error(f"Script non trouvé : {script_path}")
        return False

    logging.info(f"Lancement du scraper : {script_path}")
    try:
        module_name = script_path.replace('/', '.').replace('\\', '.').removesuffix('.py')
        result = subprocess.run(
            [PYTHON_EXECUTABLE, "-m", module_name],
            check=True, capture_output=True, text=True, encoding='utf-8',
            errors='ignore', env={**os.environ, "LOG_MINIMAL": "1"}
        )
        logging.info(f"Scraper {script_path} terminé avec succès.")
        if result.stdout: logging.info("Sortie du scraper:\n" + result.stdout)
        if result.stderr: logging.warning("Erreurs (stderr) du scraper:\n" + result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"ERREUR lors de l'exécution de {script_path}!")
        logging.error("--- SORTIE (stdout) ---\n" + e.stdout)
        logging.error("--- ERREURS (stderr) ---\n" + e.stderr)
        return False
    except Exception as e:
        logging.error(f"Erreur inattendue : {e}")
        return False


def create_zip_archive() -> Optional[Tuple[Path, List[Path]]]:
    """Archive les rapports et retourne le chemin du ZIP et la liste des fichiers sources."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    zip_filename = OUTPUT_DIR / f"rapport_hebdomadaire_{date_str}.zip"
    logging.info(f"Création de l'archive ZIP : {zip_filename}")

    files_to_archive = [p for p in OUTPUT_DIR.glob(f"*{date_str}*") if p.suffix in ['.csv', '.xlsx']]
    if not files_to_archive:
        logging.warning("Aucun fichier de rapport trouvé pour aujourd'hui. L'archive ne sera pas créée.")
        return None

    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files_to_archive:
                zipf.write(file, arcname=file.name)
                logging.info(f"Ajouté à l'archive : {file.name}")
        logging.info(f"Archive {zip_filename} créée avec succès.")
        return zip_filename, files_to_archive
    except Exception as e:
        logging.error(f"ERREUR lors de la création de l'archive ZIP : {e}")
        return None


def send_email_with_attachment(attachment_path: Path) -> bool:
    """Envoie un email avec pièce jointe et retourne True si succès, False si échec."""
    logging.info("Préparation de l'envoi de l'email...")
    to_emails = [email.strip() for email in os.getenv("EMAIL_TO", "").split(',') if email.strip()]
    cc_emails = [email.strip() for email in os.getenv("EMAIL_CC", "").split(',') if email.strip()]

    if not to_emails:
        logging.error("Aucun destinataire (EMAIL_TO) n'est configuré dans le fichier .env.")
        return False

    msg = MIMEMultipart()
    msg['From'] = os.getenv("EMAIL_FROM")
    msg['To'] = ", ".join(to_emails)
    msg['Cc'] = ", ".join(cc_emails)
    msg['Subject'] = f"Rapport Hebdomadaire de Données - {datetime.now().strftime('%d/%m/%Y')}"
    msg.attach(MIMEText(
        "===== Test de Tasiana: envoi automatique d'un rapport depuis le Planificateur de tâches. ===== Bonjour,\n\nVeuillez trouver ci-joint le rapport hebdomadaire des données collectées.\n\nCordialement,\nTatsiana.",
        'plain', 'utf-8'))

    try:
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=attachment_path.name)
        part['Content-Disposition'] = f'attachment; filename="{attachment_path.name}"'
        msg.attach(part)
    except Exception as e:
        logging.error(f"ERREUR lors de l'attachement du fichier {attachment_path}: {e}")
        return False

    try:
        logging.info(f"Connexion au serveur SMTP : {os.getenv('SMTP_SERVER')}:{os.getenv('SMTP_PORT')}")
        server = smtplib.SMTP(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT")))
        server.starttls()
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        all_recipients = to_emails + cc_emails
        server.sendmail(msg['From'], all_recipients, msg.as_string())
        server.quit()
        logging.info(f"Email envoyé avec succès à : {', '.join(all_recipients)}")
        return True
    except Exception as e:
        logging.error(f"ERREUR lors de l'envoi de l'email : {e}")
        return False


def cleanup_files(files_to_delete: List[Path]):
    """Supprime les fichiers spécifiés."""
    logging.info("--- Nettoyage des fichiers sources ---")
    for file in files_to_delete:
        try:
            file.unlink()
            logging.info(f"--- Fichier supprimé --- : {file.name}")
        except Exception as e:
            logging.error(f"ERREUR lors de la suppression de {file.name}: {e}")
    logging.info("--- Nettoyage terminé. Seul le fichier ZIP a été conservé. ---")


def main():
    """Fonction principale pour orchestrer tout le processus."""
    setup_logging()
    load_dotenv()
    start_time = time.time()
    logging.info("=" * 50)
    logging.info("Début du processus d'automatisation.")
    logging.info("=" * 50)

    all_ok = True
    for script in SCRIPTS_TO_RUN:
        if not run_scraper(script):
            all_ok = False
            logging.critical(f"Processus arrêté à cause d'une erreur critique dans {script}.")
            break

    if all_ok:
        logging.info("Tous les scrapers ont terminé avec succès.")
        archive_result = create_zip_archive()
        if archive_result:
            zip_file_path, source_files = archive_result
            email_sent_successfully = send_email_with_attachment(zip_file_path)

            if email_sent_successfully:
                cleanup_files(source_files)

    end_time = time.time()
    logging.info("=" * 50)
    logging.info(f"Processus terminé. Durée totale : {end_time - start_time:.2f} secondes.")
    logging.info("=" * 50)


if __name__ == "__main__":
    main()

