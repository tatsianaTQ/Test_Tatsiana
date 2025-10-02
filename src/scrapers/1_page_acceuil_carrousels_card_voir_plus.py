#URL   = "https://video.telequebec.tv/"             # URL de la page acceuil
# ---------------------------------------------------------------------------
# SCRIPT DE COLLECTE DES URLS (Page Acceuil) – cartes + bouton « Voir plus »
# ---------------------------------------------------------------------------
# Pour chaque carrousel (swiper/slick) :
#   – Lien « Voir plus » s’il existe
#   – Toutes les cartes (Swiper/Slick)
# Noms corrects des cartes (fallback aria-label)
# Exécution headless + robustesse (rechargements, timeouts, stale elements)
# Export CSV + XLSX + durée d’exécution
# ---------------------------------------------------------------------------

import os
import time
import csv
import logging
from datetime import datetime
from pathlib import Path
from contextlib import suppress

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from src.common.selenium_setup import new_driver

# -------------------- CONFIG ------------------------------------------------
URL   = "https://video.telequebec.tv/"                    # <-- URL de la page Acceuil
WAIT  = 15                                                # Timeout WebDriverWait (sec)
DATE  = datetime.now().strftime("%Y-%m-%d")
ROOT  = Path("output"); ROOT.mkdir(exist_ok=True)

# Mode de log minimal (silence pour runs orchestrés)
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

def wait_blocks(dr, timeout=35):
    """Attend le chargement complet + présence du body + des blocs."""
    WebDriverWait(dr, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    WebDriverWait(dr, timeout).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    WebDriverWait(dr, timeout).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "app-page-block"))
    )

def safe_get(dr, url, tries=2, base_timeout=35, debug_dir: Path | None = None):
    """
    Ouvre l’URL et attend les blocs; en cas de timeout, fait 1 retry avec délai augmenté.
    Sauvegarde un screenshot en cas d’échec (si debug_dir est fourni).
    """
    last_err = None
    for i in range(tries):
        dr.get(url)
        with suppress(Exception):
            accept_cookies(dr, WebDriverWait(dr, 5))
        try:
            wait_blocks(dr, timeout=base_timeout + i*15)  # 35 → 50s au 2e essai
            return
        except TimeoutException as e:
            last_err = e
            if debug_dir:
                with suppress(Exception):
                    debug_dir.mkdir(exist_ok=True, parents=True)
                    ts = datetime.now().strftime("%H%M%S")
                    dr.save_screenshot(str(debug_dir / f"timeout_{ts}.png"))
    raise last_err

# ----------------- CLICS ROBUSTES ------------------------------------------
def robust_click(dr, el):
    """Scroll au centre + tentative de click classique puis JS si nécessaire."""
    with suppress(Exception):
        dr.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.05)
    try:
        el.click()
    except Exception:
        with suppress(Exception):
            dr.execute_script("arguments[0].click();", el)

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
    with suppress(Exception):
        dr.execute_script("arguments[0].removeAttribute('target');", link)
    robust_click(dr, link)
    # attendre un vrai changement d'URL (sinon on reste sur l'accueil)
    with suppress(Exception):
        WebDriverWait(dr, 10).until(lambda d: d.current_url != URL)
    time.sleep(0.5)
    url    = dr.current_url
    chemin = url.split(".tv/", 1)[1] if ".tv/" in url else ""
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
        log(f"Démarrage à {start.strftime('%H:%M:%S')}")
        safe_get(dr, URL, debug_dir=ROOT / "debug")

        car_total = len(dr.find_elements(By.TAG_NAME, 'app-page-block'))
        log(f"Carrousels détectés : {car_total}")
        logging.info(f"Carrousels détectés : {car_total}")

        for idx in range(1, car_total + 1):
            safe_get(dr, URL, debug_dir=ROOT / "debug")

            bloc = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
            dr.execute_script("arguments[0].scrollIntoView({block:'center'});", bloc)

            # Type + titre du bloc
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

            # 0) Bouton « Voir plus »
            click_voir_plus(dr, wait, bloc, idx, typ, titre, rows)

            # =================== 1) GRANDE CARROUSEL (Swiper) =================
            if "Grande" in typ:
                # Déduplication par libellé pour éviter les doublons (ex: clones)
                metas, vus_labels = [], set()
                for sl in bloc.find_elements(By.CSS_SELECTOR, "swiper-slide"):
                    if '-duplicate' in (sl.get_attribute('class') or ''):
                        continue
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
                        if lab and lab not in vus_labels:
                            vus_labels.add(lab)
                            metas.append((sid, lab))
                log(f"  Nombre de cartes (uniques) : {len(metas)}")

                for ordre, (sid, lab) in enumerate(metas, 1):
                    safe_get(dr, URL, debug_dir=ROOT / "debug")
                    car = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
                    dr.execute_script("arguments[0].scrollIntoView({block:'center'});", car)

                    # ⚠️ Revenir à la logique « slide ACTIF » (sinon pas de navigation)
                    swipe = 0
                    while swipe < 120:
                        try:
                            act = car.find_element(By.CSS_SELECTOR, 'swiper-slide.swiper-slide-active')
                            # Vérifier l'index de la diapo active
                            if int(act.get_attribute('data-swiper-slide-index')) == sid:
                                # Chercher un lien cliquable à l'intérieur de la diapo active
                                link = None
                                with suppress(Exception):
                                    link = act.find_element(By.CSS_SELECTOR, 'a')
                                if not link:
                                    with suppress(Exception):
                                        link = act.find_element(By.CSS_SELECTOR, 'div[role="link"]')
                                target = link if link else act
                                with suppress(Exception):
                                    dr.execute_script("arguments[0].removeAttribute('target');", target)
                                robust_click(dr, target)
                                # attendre vrai changement d'URL
                                with suppress(Exception):
                                    WebDriverWait(dr, 10).until(lambda d: d.current_url != URL)
                                break
                        except Exception:
                            pass
                        # faire défiler jusqu'à rendre la bonne diapo active
                        with suppress(Exception):
                            car.find_element(By.CSS_SELECTOR, '.ic-arrow-right-bg').click()
                        time.sleep(0.15)
                        swipe += 1

                    time.sleep(0.8)
                    url    = dr.current_url
                    chemin = url.split('.tv/', 1)[1] if '.tv/' in url else ''
                    rows.append([idx, typ, titre, ordre, lab, url, chemin])

                    dr.back()
                    with suppress(TimeoutException):
                        wait_blocks(dr, 10)

            # ==================== 2) PETITE CARROUSEL (Slick) =================
            elif "Petite" in typ:
                # Reprise du bloc avant itération Slick
                safe_get(dr, URL, debug_dir=ROOT / "debug")
                bloc = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
                dr.execute_script("arguments[0].scrollIntoView({block:'center'});", bloc)

                # Collecte des noms uniques dans l'ordre d'affichage
                noms, vus = [], set()
                last = -1
                for _ in range(50):  # max 50 défilements
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
                    time.sleep(0.30)

                log(f"  Nombre de cartes : {len(noms)}")

                # Trouver la version VISIBLE de la carte 'nom'
                def find_visible_slide(nom):
                    cand = None
                    for s in bloc.find_elements(By.CSS_SELECTOR, 'app-slide'):
                        with suppress(Exception):
                            nm = s.find_element(By.CSS_SELECTOR, 'h3 span[aria-hidden]').text.strip()
                        if nm != nom:
                            continue
                        cls  = s.get_attribute('class') or ''
                        aria = (s.get_attribute('aria-hidden') or 'false').lower()
                        if 'slick-cloned' in cls:
                            continue
                        if aria == 'false':
                            return s
                        cand = s
                    return cand

                for ordre, nom in enumerate(noms, 1):
                    safe_get(dr, URL, debug_dir=ROOT / "debug")
                    bloc = dr.find_element(By.XPATH, f"//app-page-block[{idx}]")
                    dr.execute_script("arguments[0].scrollIntoView({block:'center'});", bloc)

                    found = False
                    tries = 0
                    while tries < 160 and not found:
                        s = find_visible_slide(nom)
                        if s is not None:
                            aria = (s.get_attribute('aria-hidden') or 'false').lower()
                            if aria != 'false':
                                with suppress(Exception):
                                    nxt = bloc.find_element(By.CSS_SELECTOR, '.slick-next.slick-arrow')
                                    if 'slick-disabled' in nxt.get_attribute('class'):
                                        break
                                    nxt.click()
                                time.sleep(0.20)
                                tries += 1
                                continue

                            link = None
                            with suppress(Exception):
                                link = s.find_element(By.TAG_NAME, 'a')
                            if not link:
                                with suppress(Exception):
                                    link = s.find_element(By.CSS_SELECTOR, "div[role='link']")
                            target = link if link else s
                            with suppress(Exception):
                                dr.execute_script("arguments[0].removeAttribute('target');", target)
                            robust_click(dr, target)
                            with suppress(Exception):
                                WebDriverWait(dr, 10).until(lambda d: d.current_url != URL)
                            found = True
                            break

                        with suppress(Exception):
                            nxt = bloc.find_element(By.CSS_SELECTOR, '.slick-next.slick-arrow')
                            if 'slick-disabled' in nxt.get_attribute('class'):
                                break
                            nxt.click()
                        time.sleep(0.20)
                        tries += 1

                    if not found:
                        continue

                    time.sleep(0.8)
                    url    = dr.current_url
                    chemin = url.split('.tv/', 1)[1] if '.tv/' in url else ''
                    rows.append([idx, typ, titre, ordre, nom, url, chemin])

                    dr.back()
                    with suppress(TimeoutException):
                        wait_blocks(dr, 10)

        # -------------------- EXPORT FICHIERS --------------------------------
        COLS = ["# Carrousel","Type","Titre du carrousel","#","titre (card)","URL détail","Chemin"]
        base = f"carrousels_cards_url_page_acceuil_{DATE}"
        csv_f = ROOT / f"{base}.csv"
        xlsx_f = ROOT / f"{base}.xlsx"

        with csv_f.open('w', newline='', encoding='utf-8') as f:
            csv.writer(f, delimiter=';').writerows([COLS, *rows])

        pd.DataFrame(rows, columns=COLS).to_excel(xlsx_f, index=False)

        # Sortie minimale
        print(f"\nFichiers enregistrés : {csv_f}   {xlsx_f}")
        print(f"Durée totale : {(datetime.now()-start).seconds} sec")

    finally:
        dr.quit()

if __name__ == "__main__":
    run()
