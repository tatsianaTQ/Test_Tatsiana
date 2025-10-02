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
from selenium.common.exceptions import TimeoutException
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
    """Accepte la bannière cookies si elle est présente (OneTrust)."""
    with suppress(Exception):
        wait.until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        ).click()

def wait_blocks(dr, timeout=60):
    """Attend un chargement réellement complet."""
    WebDriverWait(dr, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    WebDriverWait(dr, timeout).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    WebDriverWait(dr, timeout).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "app-page-block"))
    )

def safe_get(dr, url, tries=2, base_timeout=60, debug_dir: Union[Path, None] = None):
    """Ouvre l’URL et attend les blocs; en cas de timeout, fait 1 retry."""
    last_err = None
    for i in range(tries):
        dr.get(url)
        with suppress(Exception):
            accept_cookies(dr, WebDriverWait(dr, 5))
        try:
            wait_blocks(dr, timeout=base_timeout + i*15)
            return
        except TimeoutException as e:
            last_err = e
            if debug_dir:
                with suppress(Exception):
                    debug_dir.mkdir(exist_ok=True, parents=True)
                    ts = datetime.now().strftime("%H%M%S")
                    dr.save_screenshot(str(debug_dir / f"timeout_{ts}.png"))
    raise last_err

# -------------------- BOUTON « VOIR PLUS » ---------------------------------
def click_voir_plus(dr, wait, bloc, idx, typ, titre, rows):
    """Clique sur « Voir plus » s’il existe et journalise l’URL."""
    xpaths = [
        ".//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'voir plus')]",
        ".//*[@role='link' and contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'voir plus')]",
    ]
    link = None
    for xp in xpaths:
        with suppress(Exception):
            link = bloc.find_element(By.XPATH, xp)
            if link:
                break
    if not link or not link.is_displayed():
        return
    dr.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
    with suppress(Exception):
        dr.execute_script("arguments[0].removeAttribute('target');", link)
    link.click()
    time.sleep(2)
    url    = dr.current_url
    chemin = url.split(".tv/")[1] if ".tv/" in url else ""
    log(f"Bouton « Voir plus » → {url}")
    rows.append([idx, typ, titre, '', 'Voir plus', url, chemin])
    dr.back()
    with suppress(TimeoutException):
        wait_blocks(dr, 10)

# -------------------- MAIN --------------------------------------------------
def run():
    dr    = new_driver()
    wait  = WebDriverWait(dr, WAIT)
    start = datetime.now()
    rows  = []

    try:
        # Page initiale
        print(f"Démarrage à {start.strftime('%H:%M:%S')}")
        safe_get(dr, URL, debug_dir=ROOT / "debug")

        # --- NOUVELLE ÉTAPE : DÉFILEMENT COMPLET DE LA PAGE ---
        # Ceci force le chargement de tous les éléments "paresseux" (lazy-loaded).
        log("Début du défilement pour charger tous les blocs de la page...")
        last_height = dr.execute_script("return document.body.scrollHeight")
        while True:
            # Fait défiler la page jusqu'en bas
            dr.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            # Attend un court instant pour laisser le temps aux nouveaux éléments de se charger
            time.sleep(3)
            # Calcule la nouvelle hauteur de la page et la compare à l'ancienne
            new_height = dr.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break  # Sort de la boucle si la hauteur n'augmente plus
            last_height = new_height
        log("Fin du défilement.")
        # ---------------------------------------------------------

        # Maintenant, on compte les carrousels en étant sûr qu'ils sont tous chargés
        car_total = len(dr.find_elements(By.TAG_NAME, 'app-page-block'))
        log(f"Carrousels détectés : {car_total}")
        logging.info(f"Carrousels détectés : {car_total}")

        for idx in range(1, car_total + 1):
            safe_get(dr, URL, debug_dir=ROOT / "debug")
            bloc = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
            dr.execute_script("arguments[0].scrollIntoView({block:'center'});", bloc)

            typ = (
                "Grande carrousel (swiper)" if bloc.find_elements(By.CSS_SELECTOR, 'swiper-slide') else
                "Petite carrousel (slick)"  if bloc.find_elements(By.CSS_SELECTOR, 'app-slide')  else
                "Carrousel inconnu"
            )
            try:
                titre = bloc.find_element(By.CSS_SELECTOR, '.block-title').text.strip()
            except Exception:
                titre = f"Carrousel_{idx}"

            log(f"\n{idx}. {typ} : {titre}")
            click_voir_plus(dr, wait, bloc, idx, typ, titre, rows)

            if "Grande" in typ:
                metas = []
                for sl in bloc.find_elements(By.CSS_SELECTOR, "swiper-slide:not([class*='-duplicate'])"):
                    with suppress(Exception):
                        sid = int(sl.get_attribute('data-swiper-slide-index'))
                        lab = (sl.get_attribute('aria-label') or '').strip()
                        if not lab or lab.replace(' ', '').replace('/', '').isdigit():
                            with suppress(Exception):
                                inner = sl.find_element(By.CSS_SELECTOR, "div[role='link'][aria-label]")
                                lab   = (inner.get_attribute('aria-label') or '').strip()
                        if not lab:
                            with suppress(Exception):
                                lab = sl.find_element(By.CSS_SELECTOR, 'span[aria-hidden], h2, h3').text.strip()
                        for sep in (' - ', ' – '):
                            pref = f"{titre}{sep}"
                            if lab.startswith(pref):
                                lab = lab[len(pref):].strip(); break
                        metas.append((sid, lab or f"carte_{sid}"))

                log(f"  Nombre de cartes : {len(metas)}")
                for ordre, (sid, lab) in enumerate(metas, 1):
                    car = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
                    dr.execute_script("arguments[0].scrollIntoView({block:'center'});", car)
                    swipe = 0
                    while swipe < 80:
                        try:
                            act = car.find_element(By.CSS_SELECTOR, 'swiper-slide.swiper-slide-active')
                            if int(act.get_attribute('data-swiper-slide-index')) == sid:
                                link = None
                                with suppress(Exception):
                                    link = act.find_element(By.CSS_SELECTOR, 'a, div[role="link"]')
                                if link:
                                    dr.execute_script("arguments[0].removeAttribute('target');", link)
                                    link.click()
                                else:
                                    act.click()
                                break
                        except Exception:
                            pass
                        with suppress(Exception):
                            car.find_element(By.CSS_SELECTOR, '.ic-arrow-right-bg').click()
                        time.sleep(0.25)
                        swipe += 1
                    time.sleep(2)
                    url    = dr.current_url
                    chemin = url.split('.tv/')[1] if '.tv/' in url else ''
                    rows.append([idx, typ, titre, ordre, lab, url, chemin])
                    dr.back()
                    with suppress(TimeoutException):
                        wait_blocks(dr, 10)

            elif "Petite" in typ:
                safe_get(dr, URL, debug_dir=ROOT / "debug")
                bloc = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
                dr.execute_script("arguments[0].scrollIntoView({block:'center'});", bloc)
                noms, vus = [], set()
                last = -1
                for _ in range(50):
                    for s in bloc.find_elements(By.CSS_SELECTOR, 'app-slide'):
                        with suppress(Exception):
                            nm = s.find_element(By.CSS_SELECTOR, "h3 span[aria-hidden='true']").text.strip()
                            if nm and nm not in vus:
                                vus.add(nm)
                                noms.append(nm)
                    if len(vus) == last:
                        break
                    last = len(vus)
                    try:
                        nxt = bloc.find_element(By.CSS_SELECTOR, '.slick-next.slick-arrow')
                    except Exception:
                        break
                    if 'slick-disabled' in nxt.get_attribute('class'):
                        break
                    nxt.click()
                    time.sleep(0.35)

                log(f"  Nombre de cartes : {len(noms)}")
                for ordre, nom in enumerate(noms, 1):
                    bloc = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
                    dr.execute_script("arguments[0].scrollIntoView({block:'center'});", bloc)
                    found, tries = False, 0
                    while tries < 120 and not found:
                        for s in bloc.find_elements(By.CSS_SELECTOR, 'app-slide'):
                            with suppress(Exception):
                                nm = s.find_element(By.CSS_SELECTOR, 'h3 span[aria-hidden]').text.strip()
                                if nm == nom:
                                    link = None
                                    with suppress(Exception):
                                        link = s.find_element(By.TAG_NAME, 'a')
                                    if link:
                                        dr.execute_script("arguments[0].removeAttribute('target');", link)
                                        link.click()
                                    else:
                                        s.click()
                                    found = True
                                    break
                        if found:
                            break
                        try:
                            nxt = bloc.find_element(By.CSS_SELECTOR, '.slick-next.slick-arrow')
                        except Exception:
                            break
                        if 'slick-disabled' in nxt.get_attribute('class'):
                            break
                        nxt.click()
                        time.sleep(0.25)
                        tries += 1
                    if not found:
                        continue
                    time.sleep(2)
                    url    = dr.current_url
                    chemin = url.split('.tv/')[1] if '.tv/' in url else ''
                    rows.append([idx, typ, titre, ordre, nom, url, chemin])
                    dr.back()
                    with suppress(TimeoutException):
                        wait_blocks(dr, 10)

        # -------------------- EXPORT FICHIERS --------------------------------
        COLS = ["# Carrousel","Type","Titre du carrousel","#","titre (card)","URL détail","Chemin"]
        base = f"carrousels_cards_url_page_en_sur_demande_{DATE}"
        csv_f = ROOT / f"{base}.csv"
        xlsx_f = ROOT / f"{base}.xlsx"

        with csv_f.open('w', newline='', encoding='utf-8') as f:
            csv.writer(f, delimiter=';').writerows([COLS, *rows])

        pd.DataFrame(rows, columns=COLS).to_excel(xlsx_f, index=False)

        print(f"\nFichiers enregistrés : {csv_f}   {xlsx_f}")
        print(f"Durée totale : {(datetime.now()-start).seconds} sec")

    finally:
        dr.quit()

if __name__ == "__main__":
    run()


