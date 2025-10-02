# src/common/selenium_setup.py

from selenium import webdriver

def new_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--window-size=1280,1024")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-dev-shm-usage")
    # -----------------
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=opts)

