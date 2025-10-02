#URL   = "https://video.telequebec.tv/sur%20demande"                    # <-- URL de la page d’accueil
# ---------------------------------------------------------------------------
# SCRIPT DE COLLECTE DES URLS (« Sur demande ») – cartes + bouton « Voir plus »
# ---------------------------------------------------------------------------
# • Pour chaque carrousel (swiper/slick) :
#   – Lien « Voir plus » s’il existe
#   – Toutes les cartes (Swiper/Slick)
# • Noms corrects des cartes (fallback aria-label)
# • Exécution headless + robustesse (rechargements, timeouts, stale elements)
# • Export CSV + XLSX + durée d’exécution
# ---------------------------------------------------------------------------

import os
import time
import csv
import logging
from datetime import datetime
from pathlib import Path
from contextlib import suppress
from typing import Union

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from src.common.selenium_setup import new_driver

# -------------------- CONFIG ------------------------------------------------
URL   = "https://video.telequebec.tv/sur%20demande"                    
WAIT  = 30
DATE  = datetime.now( ).strftime("%Y-%m-%d")
ROOT  = Path("output"); ROOT.mkdir(exist_ok=True)

_LOG_MINIMAL = os.getenv("LOG_MINIMAL", "0") == "1"
def log(*args, **kwargs):
    if not _LOG_MINIMAL:
        print(*args, **kwargs)

# -------------------- OUTILS SELENIUM --------------------------------------
def accept_cookies(dr, wait):
    with suppress(Exception):
        wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()

def wait_blocks(dr, timeout=60):
    WebDriverWait(dr, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
    WebDriverWait(dr, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    WebDriverWait(dr, timeout).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "app-page-block")))

def safe_get(dr, url, tries=2, base_timeout=60, debug_dir: Union[Path, None] = None):
    last_err = None
    for i in range(tries):
        try:
            dr.get(url)
            with suppress(Exception):
                accept_cookies(dr, WebDriverWait(dr, 5))
            wait_blocks(dr, timeout=base_timeout + i*15)
            return
        except (TimeoutException, WebDriverException) as e:
            last_err = e
            if debug_dir:
                with suppress(Exception):
                    debug_dir.mkdir(exist_ok=True, parents=True)
                    ts = datetime.now().strftime("%H%M%S")
                    dr.save_screenshot(str(debug_dir / f"timeout_{ts}.png"))
    raise last_err

# -------------------- MAIN --------------------------------------------------
def run():
    start = datetime.now()
    rows  = []
    
    # --- ÉTAPE 1: OBTENIR LA LISTE COMPLÈTE DES TÂCHES ---
    log("ÉTAPE 1: Démarrage du navigateur pour obtenir la liste des tâches...")
    dr = new_driver()
    all_tasks = []
    try:
        safe_get(dr, URL, debug_dir=ROOT / "debug")
        log("Début du défilement pour charger tous les blocs...")
        last_height = dr.execute_script("return document.body.scrollHeight")
        while True:
            dr.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = dr.execute_script("return document.body.scrollHeight")
            if new_height == last_height: break
            last_height = new_height
        log("Fin du défilement.")

        car_total = len(dr.find_elements(By.TAG_NAME, 'app-page-block'))
        log(f"Carrousels détectés : {car_total}")

        for idx in range(1, car_total + 1):
            bloc = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
            dr.execute_script("arguments[0].scrollIntoView({block:'center'});", bloc)
            typ = "Grande" if bloc.find_elements(By.CSS_SELECTOR, 'swiper-slide') else "Petite"
            titre = bloc.find_element(By.CSS_SELECTOR, '.block-title').text.strip() or f"Carrousel_{idx}"
            
            # Tâche pour "Voir plus"
            with suppress(Exception):
                link = bloc.find_element(By.XPATH, ".//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'voir plus')]")
                if link.is_displayed():
                    all_tasks.append({'type': 'voir_plus', 'idx': idx, 'typ_name': typ, 'titre': titre})

            # Tâches pour les cartes
            if "Grande" in typ:
                for sl in bloc.find_elements(By.CSS_SELECTOR, "swiper-slide:not([class*='-duplicate'])"):
                    with suppress(Exception):
                        sid = int(sl.get_attribute('data-swiper-slide-index'))
                        all_tasks.append({'type': 'grande_carte', 'idx': idx, 'typ_name': typ, 'titre': titre, 'sid': sid})
            elif "Petite" in typ:
                noms, vus = [], set()
                for _ in range(50):
                    last_len = len(vus)
                    for s in bloc.find_elements(By.CSS_SELECTOR, 'app-slide'):
                        with suppress(Exception):
                            nm = s.find_element(By.CSS_SELECTOR, "h3 span[aria-hidden='true']").text.strip()
                            if nm and nm not in vus: vus.add(nm); noms.append(nm)
                    if len(vus) == last_len: break
                    with suppress(Exception):
                        nxt = bloc.find_element(By.CSS_SELECTOR, '.slick-next:not(.slick-disabled)')
                        nxt.click(); time.sleep(0.35)
                for nom in noms:
                    all_tasks.append({'type': 'petite_carte', 'idx': idx, 'typ_name': typ, 'titre': titre, 'nom': nom})
    finally:
        log("Liste des tâches créée. Fermeture du premier navigateur.")
        dr.quit()

    # --- ÉTAPE 2: EXÉCUTER CHAQUE TÂCHE DANS UN NOUVEAU NAVIGATEUR ---
    log(f"\nÉTAPE 2: Exécution de {len(all_tasks)} tâches une par une...")
    for i, task in enumerate(all_tasks):
        log(f"  Tâche {i+1}/{len(all_tasks)}: {task['type']} pour carrousel {task['idx']}")
        dr = new_driver()
        try:
            safe_get(dr, URL, debug_dir=ROOT / "debug")
            bloc = dr.find_element(By.XPATH, f"//app-page-block[{task['idx']}]")
            dr.execute_script("arguments[0].scrollIntoView({block:'center'});", bloc)

            if task['type'] == 'voir_plus':
                link = bloc.find_element(By.XPATH, ".//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'voir plus')]")
                dr.execute_script("arguments[0].removeAttribute('target');", link)
                link.click(); time.sleep(2)
                url = dr.current_url
                rows.append([task['idx'], task['typ_name'], task['titre'], '', 'Voir plus', url, url.split('.tv/')[1] if '.tv/' in url else ''])

            elif task['type'] == 'grande_carte':
                swipe = 0
                while swipe < 80:
                    with suppress(Exception):
                        act = bloc.find_element(By.CSS_SELECTOR, 'swiper-slide.swiper-slide-active')
                        if int(act.get_attribute('data-swiper-slide-index')) == task['sid']:
                            act.click(); break
                    with suppress(Exception):
                        bloc.find_element(By.CSS_SELECTOR, '.ic-arrow-right-bg').click()
                    time.sleep(0.25); swipe += 1
                time.sleep(2); url = dr.current_url
                rows.append([task['idx'], task['typ_name'], task['titre'], '', f"Carte SID {task['sid']}", url, url.split('.tv/')[1] if '.tv/' in url else ''])

            elif task['type'] == 'petite_carte':
                tries = 0
                while tries < 120:
                    found = False
                    for s in bloc.find_elements(By.CSS_SELECTOR, 'app-slide'):
                        with suppress(Exception):
                            if s.find_element(By.CSS_SELECTOR, 'h3 span[aria-hidden]').text.strip() == task['nom']:
                                s.click(); found = True; break
                    if found: break
                    with suppress(Exception):
                        bloc.find_element(By.CSS_SELECTOR, '.slick-next:not(.slick-disabled)').click()
                    time.sleep(0.25); tries += 1
                time.sleep(2); url = dr.current_url
                rows.append([task['idx'], task['typ_name'], task['titre'], '', task['nom'], url, url.split('.tv/')[1] if '.tv/' in url else ''])
        except Exception as e:
            log(f"    !!!! ERREUR sur la tâche {i+1}: {e}")
        finally:
            dr.quit()

    # --- ÉTAPE 3: EXPORT ---
    log("\nÉTAPE 3: Exportation des résultats...")
    COLS = ["# Carrousel","Type","Titre du carrousel","#","titre (card)","URL détail","Chemin"]
    base = f"carrousels_cards_url_page_en_sur_demande_{DATE}"
    csv_f = ROOT / f"{base}.csv"
    xlsx_f = ROOT / f"{base}.xlsx"
    with csv_f.open('w', newline='', encoding='utf-8') as f:
        csv.writer(f, delimiter=';').writerows([COLS, *rows])
    pd.DataFrame(rows, columns=COLS).to_excel(xlsx_f, index=False)
    print(f"\nFichiers enregistrés : {csv_f}   {xlsx_f}")
    print(f"Durée totale : {(datetime.now()-start).seconds} sec")

if __name__ == "__main__":
    run()
