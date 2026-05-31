"""Recon script: log in to LinkedIn, navigate to a jobs search page, dump the DOM
fragments we care about so we can fix bot.py's selectors.

Run once; deletes itself after producing /tmp/li_dump.html and a stdout report.
"""
import os, sys, re, time, random
sys.path.insert(0, '.')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

opts = Options()
for o in ["--no-sandbox", "--start-maximized", "--disable-blink-features=AutomationControlled"]:
    opts.add_argument(o)
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
driver.maximize_window()

try:
    driver.get("https://www.linkedin.com/login")
    time.sleep(random.uniform(3, 4))
    driver.find_element(By.ID, "username").send_keys(os.environ["LINKEDIN_EMAIL"])
    driver.find_element(By.ID, "password").send_keys(os.environ["LINKEDIN_PASSWORD"])
    driver.find_element(By.CSS_SELECTOR, ".btn__primary--large").click()
    time.sleep(8)  # leave room for captcha

    # Navigate to a job search.
    url = "https://www.linkedin.com/jobs/search/?keywords=Full%20Stack%20Developer&f_TPR=r604800&f_JT=F"
    driver.get(url)
    time.sleep(8)

    # Dump body to file
    body_html = driver.page_source
    with open("/tmp/li_dump.html", "w") as f:
        f.write(body_html)
    print(f"BODY LEN: {len(body_html)}")

    # Try a bunch of candidate selectors and report counts.
    candidates = {
        "jobs-search-results-list__title-heading": "h2 with job count",
        "jobs-search-results-list__text": "header text",
        "scaffold-layout__list": "results scroll container (old)",
        "jobs-search-results-list": "results scroll container (mid)",
        "jobs-search__job-details--container": "right pane",
        "jobs-search-results__list-item": "job tile (old)",
        "scaffold-layout__list-item": "job tile (mid)",
        "job-card-container": "job card",
        "job-card-list__title--link": "job title link (old)",
        "job-card-list__title": "job title (newer)",
        "artdeco-entity-lockup__title": "lockup title",
        "artdeco-entity-lockup__subtitle": "company name",
        "job-details-jobs-unified-top-card__job-title": "job detail title",
        "job-details-jobs-unified-top-card__company-name": "job detail company",
        "job-details-jobs-unified-top-card__tertiary-description-container": "job detail location",
        "jobs-company__inline-information": "employee count",
        "hirer-card__hirer-information": "hirer card",
    }
    for cls, label in candidates.items():
        n = len(driver.find_elements(By.CLASS_NAME, cls))
        print(f"{n:>4}  .{cls}  ({label})")

    # Look for the job count heading via a broader query
    print()
    headings = driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, .jobs-search-results-list__subtitle, [class*='results-list__title']")
    for h in headings[:8]:
        txt = (h.text or "").strip().replace("\n", " | ")
        cls = h.get_attribute("class")
        if txt:
            print(f"HEADING  class='{cls[:60]}'  text='{txt[:120]}'")

    # Find any list element with job-id data attribute
    print()
    print("--- data-occludable-job-id / data-job-id ---")
    for sel in ["[data-occludable-job-id]", "[data-job-id]", "li[data-test-job-id]"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        print(f"{len(els):>4}  {sel}")

    # Save unique class names that look job-related
    print()
    print("--- unique classes containing 'job' or 'card' (first 40) ---")
    classes = set()
    for el in driver.find_elements(By.CSS_SELECTOR, "li, div"):
        c = el.get_attribute("class") or ""
        for token in c.split():
            if "job" in token.lower() or "card" in token.lower() or "results-list" in token.lower():
                classes.add(token)
    for c in sorted(classes)[:60]:
        print(f"  .{c}")

finally:
    print("\n--- DONE ---")
    time.sleep(2)
    driver.quit()
