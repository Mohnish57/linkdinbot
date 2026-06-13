from __future__ import annotations

import os
import sys
current_file_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_file_path)

import re
import time
import random
import ast
from pathlib import Path
from urllib.parse import quote_plus

import yaml
import pandas as pd
from tqdm import tqdm

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from linkedinBot.utils.ai import (
    JobMatchEvaluator,
    build_invite_note,
    classify_role,
    INVITE_NOTE_MAX,
    DEFAULT_INVITE_NOTE_TEMPLATE,
    DEFAULT_INVITE_NOTE_TEMPLATE_FRONTEND,
    DEFAULT_INVITE_NOTE_TEMPLATE_HIRER,
    DEFAULT_INVITE_NOTE_TEMPLATE_HIRER_FRONTEND,
    DEFAULT_RESUME_DRIVE_LINK,
    DEFAULT_CANDIDATE_NAME,
    DEFAULT_CANDIDATE_FIRST_NAME,
    DEFAULT_CANDIDATE_EMAIL,
    DEFAULT_CANDIDATE_BIO_FULLSTACK,
    DEFAULT_CANDIDATE_BIO_FRONTEND,
    DEFAULT_CANDIDATE_PROFILE_BLOCK,
    DEFAULT_CANDIDATE_PITCH,
    DEFAULT_AI_SYSTEM_PROMPT_TEMPLATE,
)
from linkedinBot.utils.shortlink import shorten as shorten_url
from linkedinBot.utils.mailer import GmailCreds, send_one, gmail_creds_from_env


# Cross-platform paths anchored at the project root (the linkdinbot/ folder).
PROJECT_ROOT = os.path.dirname(current_file_path)
CONFIG_PATH = os.path.join(current_file_path, "configs", "config.yaml")
OUTPUT_DIR = os.path.join(current_file_path, "output")
POSTS_CSV = os.path.join(OUTPUT_DIR, "posts_emails.csv")
JOBS_CSV = os.path.join(OUTPUT_DIR, "jobs.csv")
CHROME_PROFILE_DIR = os.path.join(current_file_path, "chrome-profile")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Phrases that mark a post as a JOB-SEEKER / "open to work" post rather than a
# hiring post. If any appears, we skip the post (never connect to candidates).
DEFAULT_SEEKER_PHRASES = [
    "open to work", "#opentowork", "opentowork",
    "looking for opportunities", "looking for a new opportunity",
    "looking for new opportunities", "looking for an opportunity",
    "looking for a job", "looking for job", "looking for a role",
    "i'm looking for", "i am looking for", "im looking for",
    "i'm currently looking", "i am currently looking", "currently looking for",
    "seeking opportunities", "seeking new opportunities", "seeking a new role",
    "in search of", "open for opportunities", "open to opportunities",
    "open to new opportunities", "actively seeking", "actively looking for",
    "please refer me", "kindly refer", "refer me",
    "looking for referral", "looking for referrals", "need a referral",
]


class LinkedInBot:
    def __init__(self, headless=False, resume_path=None, resume_paths=None, config_overrides=None):
        """`resume_paths` is preferred: {"fullstack": "...", "frontend": "..."}.
        `resume_path` is kept for backwards compatibility — treated as the fullstack
        resume when no dict is provided.
        """
        self.headless = headless
        self.resume_paths = dict(resume_paths or {})
        if resume_path and "fullstack" not in self.resume_paths:
            self.resume_paths["fullstack"] = resume_path
        self.config = self.load_config(overrides=config_overrides or {})
        self.driver = self.init_browser()
        candidate_context = {
            "candidate_name": self.config["candidateName"],
            "candidate_email": self.config["candidateEmail"],
            "candidate_profile_block": self.config["candidateProfileBlock"],
            "candidate_pitch": self.config["candidatePitch"],
            "resume_link": self.config["resumeDriveLink"],
            "resume_link_fullstack": self.config["resumeDriveLink"],
            "resume_link_frontend": self.config["resumeDriveLinkFrontend"],
        }
        self.job_match_evaluator = (
            JobMatchEvaluator(
                resume_paths=self.resume_paths,
                candidate_context=candidate_context,
                system_prompt_template=self.config["aiSystemPromptTemplate"],
            )
            if self.resume_paths else None
        )
        self.file_path = JOBS_CSV

        job_columns = [
            "job_title", "job_location", "company_name", "company_link", "job_link",
            "job_id", "employee_count", "hirer_link", "job_skills", "referral_message",
            "role_variant",
        ]
        if os.path.exists(self.file_path):
            self.df_jobs = pd.read_csv(self.file_path)
            for col in job_columns:
                if col not in self.df_jobs.columns:
                    self.df_jobs[col] = None
            print(f"Loaded {self.df_jobs.shape[0]} jobs from file.")
        else:
            self.df_jobs = pd.DataFrame(columns=job_columns)

        self.applied_jobs = [
            (row["job_title"], row["company_name"]) for _, row in self.df_jobs.iterrows()
        ] if self.df_jobs.shape[0] else []

        # Connections CSV — one row per (job_link, profile_link).
        self.connections_path = os.path.join(OUTPUT_DIR, "connections.csv")
        conn_columns = [
            "job_title", "company_name", "job_link", "profile_link", "profile_name",
            "profile_headline", "email", "status", "note_sent", "role_variant",
            "is_hirer", "email_sent",
        ]
        if os.path.exists(self.connections_path):
            self.df_connections = pd.read_csv(self.connections_path)
            for col in conn_columns:
                if col not in self.df_connections.columns:
                    self.df_connections[col] = None
        else:
            self.df_connections = pd.DataFrame(columns=conn_columns)

        self.contacted_profiles = set(
            self.df_connections["profile_link"].dropna().tolist()
        )

    # ------------------------------------------------------------------ config
    def load_config(self, overrides=None):
        try:
            with open(CONFIG_PATH, "r") as file:
                config = yaml.safe_load(file)
        except FileNotFoundError:
            print(f"Config file not found at {CONFIG_PATH}. Using defaults.")
            config = {}

        settings = config.get("settings", {})
        prefs = config.get("jobPreferences", {})
        candidate = config.get("candidate", {})

        resolved = {
            "email": os.environ.get("LINKEDIN_EMAIL"),
            "password": os.environ.get("LINKEDIN_PASSWORD"),
            "disableAntiLock": settings.get("disableAntiLock", False),
            "maxJobPage": settings.get("maxJobPage", 5),
            "maxPeoplePerProfile": settings.get("maxPeoplePerProfile", 3),
            "recruitersOnly": settings.get("recruitersOnly", True),
            "sendInviteNote": settings.get("sendInviteNote", True),
            "contactHirerFirst": settings.get("contactHirerFirst", True),
            "resumeDriveLink": settings.get("resumeDriveLink", DEFAULT_RESUME_DRIVE_LINK),
            "resumeDriveLinkFrontend": settings.get(
                "resumeDriveLinkFrontend",
                settings.get("resumeDriveLink", DEFAULT_RESUME_DRIVE_LINK),
            ),
            "inviteNoteTemplate": settings.get("inviteNoteTemplate", DEFAULT_INVITE_NOTE_TEMPLATE),
            "inviteNoteTemplateFrontend": settings.get(
                "inviteNoteTemplateFrontend", DEFAULT_INVITE_NOTE_TEMPLATE_FRONTEND
            ),
            "inviteNoteTemplateHirer": settings.get(
                "inviteNoteTemplateHirer", DEFAULT_INVITE_NOTE_TEMPLATE_HIRER
            ),
            "inviteNoteTemplateHirerFrontend": settings.get(
                "inviteNoteTemplateHirerFrontend", DEFAULT_INVITE_NOTE_TEMPLATE_HIRER_FRONTEND
            ),
            "postSearch": settings.get("postSearch", {}),
            "postInviteNoteTemplate": settings.get(
                "postInviteNoteTemplate",
                "Hi {name}, I'm {candidate_first_name} — {candidate_bio}. "
                "Saw your post about the {job_title} role at {company}; I'd love to connect. "
                "Resume: {resume_link}"
            ),
            "candidateName": candidate.get("name", DEFAULT_CANDIDATE_NAME),
            "candidateFirstName": candidate.get("first_name", DEFAULT_CANDIDATE_FIRST_NAME),
            "candidateEmail": candidate.get("email", DEFAULT_CANDIDATE_EMAIL),
            "candidateBioFullstack": candidate.get("bio_fullstack", DEFAULT_CANDIDATE_BIO_FULLSTACK),
            "candidateBioFrontend": candidate.get("bio_frontend", DEFAULT_CANDIDATE_BIO_FRONTEND),
            "candidateProfileBlock": candidate.get("profile_block", DEFAULT_CANDIDATE_PROFILE_BLOCK),
            "candidatePitch": candidate.get("pitch", DEFAULT_CANDIDATE_PITCH),
            "aiSystemPromptTemplate": settings.get(
                "aiSystemPromptTemplate", DEFAULT_AI_SYSTEM_PROMPT_TEMPLATE
            ),
            "gmailUser": os.environ.get("GMAIL_USER") or candidate.get("email"),
            "gmailAppPassword": os.environ.get("GMAIL_APP_PASSWORD"),
            "emailSubjectTemplate": settings.get("emailSubjectTemplate"),
            "emailBodyTemplate": settings.get("emailBodyTemplate"),
            "jobTypes": prefs.get("jobTypes", {}),
            "datePosted": prefs.get("datePosted", {}),
            "positions": prefs.get("positions", []),
            "people_profiles": prefs.get("people_profiles", ["Recruiter", "Hiring"]),
            "recruiterKeywords": [k.lower() for k in prefs.get("recruiterKeywords", ["recruiter", "hiring", "talent"])],
            "blacklistedtitles": prefs.get("blacklistedTitles", []),
            "blacklistedEmployeeCounts": prefs.get("blacklistedEmployeeCounts", []),
            "blacklistedDescription": prefs.get("blacklistedDescription", []),
            "blacklistedcompanys": prefs.get("blacklistedCompanies", prefs.get("blacklistedcompany", [])),
        }

        # UI / runtime overrides take precedence.
        for k, v in (overrides or {}).items():
            if v is not None:
                resolved[k] = v
        return resolved

    # ------------------------------------------------------------------ browser
    def init_browser(self):
        browser_options = Options()
        if self.headless:
            browser_options.add_argument("--headless=new")

        for opt in [
            "--no-sandbox",
            "--start-maximized",
            "--disable-extensions",
            "--ignore-certificate-errors",
            "--disable-blink-features=AutomationControlled",
            f"--user-data-dir={CHROME_PROFILE_DIR}",
        ]:
            browser_options.add_argument(opt)
        browser_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        browser_options.add_experimental_option("useAutomationExtension", False)

        driver_path = ChromeDriverManager().install()
        # webdriver-manager sometimes returns a sibling file (e.g.
        # THIRD_PARTY_NOTICES.chromedriver) instead of the real binary.
        # Point Service at the actual `chromedriver` in the same directory.
        driver_path = Path(driver_path)
        if driver_path.name != "chromedriver":
            real = driver_path.parent / "chromedriver"
            if real.exists():
                driver_path = real
        os.chmod(driver_path, 0o755)
        service = Service(str(driver_path))
        driver = webdriver.Chrome(service=service, options=browser_options)
        driver.set_window_position(0, 0)
        driver.maximize_window()
        return driver

    def security_check(self):
        current_url = self.driver.current_url
        page_source = self.driver.page_source
        if (
            "/checkpoint/challenge/" in current_url
            or "security check" in page_source
            or "quick verification" in page_source
        ):
            input("Please complete the security check then press Enter here...")
            time.sleep(random.uniform(5.5, 10.5))

    def _is_logged_in(self):
        url = (self.driver.current_url or "").lower()
        if any(p in url for p in ["/feed", "/in/", "/mynetwork", "/jobs"]):
            return True
        # Fallback: presence of the global nav profile menu means logged in.
        try:
            self.driver.find_element(By.CSS_SELECTOR, "img.global-nav__me-photo, .global-nav__me")
            return True
        except NoSuchElementException:
            return False

    def login(self):
        print("Logging in to LinkedIn...")
        self.driver.get("https://www.linkedin.com/feed")
        time.sleep(random.uniform(3, 5))

        if self._is_logged_in():
            print("Already logged in (persistent Chrome profile).")
            return

        # Not logged in — fall through to the standard login form.
        self.driver.get("https://www.linkedin.com/login")
        time.sleep(random.uniform(3, 5))

        email, password = self.config.get("email"), self.config.get("password")
        # LinkedIn's /login is now a React SPA — the form mounts after JS hydration,
        # so a short presence wait will time out. Try several selectors and wait longer.
        # LinkedIn ships two copies of the login form (desktop + responsive
        # variant). The first in DOM order is hidden via CSS, so we must
        # iterate through every match and pick the first one that's visible.
        user_selectors = [
            (By.CSS_SELECTOR, "input[autocomplete*='username']"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.ID, "username"),
            (By.NAME, "session_key"),
        ]
        pw_selectors = [
            (By.CSS_SELECTOR, "input[autocomplete*='current-password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.ID, "password"),
            (By.NAME, "session_password"),
        ]

        def _find_first(selectors, timeout):
            end = time.time() + timeout
            attempts = 0
            while time.time() < end:
                attempts += 1
                for by, sel in selectors:
                    try:
                        els = self.driver.find_elements(by, sel)
                    except Exception as ex:
                        print(f"  selector {sel!r} errored: {ex}")
                        els = []
                    for idx, el in enumerate(els):
                        try:
                            if el.is_displayed() and el.is_enabled():
                                print(
                                    f"  matched selector {sel!r} (match #{idx + 1}/{len(els)})"
                                )
                                return el
                        except Exception:
                            continue
                time.sleep(0.5)
            print(f"  _find_first gave up after {attempts} polls")
            return None

        def _switch_into_login_iframe():
            """If the form is inside an iframe, switch into the first iframe
            that contains a username-looking input. Returns True if switched."""
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            except Exception:
                iframes = []
            for frame in iframes:
                try:
                    self.driver.switch_to.frame(frame)
                    for by, sel in user_selectors:
                        try:
                            el = self.driver.find_element(by, sel)
                            if el.is_displayed():
                                return True
                        except NoSuchElementException:
                            continue
                    self.driver.switch_to.default_content()
                except Exception:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
            return False

        def _dump_login_diagnostics():
            try:
                print(f"  login diagnostic: url={self.driver.current_url}")
                print(f"  login diagnostic: title={self.driver.title!r}")
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                print(f"  login diagnostic: {len(inputs)} <input> elements")
                for el in inputs[:15]:
                    try:
                        print(
                            "    input id={!r} name={!r} type={!r} autocomplete={!r}".format(
                                el.get_attribute("id"),
                                el.get_attribute("name"),
                                el.get_attribute("type"),
                                el.get_attribute("autocomplete"),
                            )
                        )
                    except Exception:
                        pass
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                print(f"  login diagnostic: {len(iframes)} iframes")
                for fr in iframes[:5]:
                    try:
                        print(f"    iframe src={fr.get_attribute('src')!r}")
                    except Exception:
                        pass
                shot_path = "/tmp/linkedin_login_debug.png"
                try:
                    self.driver.save_screenshot(shot_path)
                    print(f"  login diagnostic: screenshot saved to {shot_path}")
                except Exception as ex:
                    print(f"  login diagnostic: screenshot failed: {ex}")
            except Exception as ex:
                print(f"  login diagnostic: dump failed: {ex}")

        try:
            user_field = _find_first(user_selectors, timeout=45)
            if user_field is None and _switch_into_login_iframe():
                user_field = _find_first(user_selectors, timeout=10)
            if user_field is None:
                _dump_login_diagnostics()
                raise TimeoutException("login form did not appear in 45s")
            if email and password:
                user_field.clear()
                user_field.send_keys(email)
                pw = _find_first(pw_selectors, timeout=10)
                if pw is None:
                    raise TimeoutException("password field did not appear")
                pw.clear()
                pw.send_keys(password)
                submit_selectors = [
                    (By.CSS_SELECTOR, "button[data-litms-control-urn='login-submit']"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.CSS_SELECTOR, "button[aria-label*='Sign in']"),
                    (By.CSS_SELECTOR, ".btn__primary--large"),
                ]
                submit_btn = _find_first(submit_selectors, timeout=5)
                if submit_btn is not None:
                    try:
                        submit_btn.click()
                        print("  clicked submit button")
                    except Exception as ex:
                        print(f"  submit click failed ({ex}); falling back to Enter key")
                        pw.send_keys(Keys.RETURN)
                else:
                    print("  no visible submit button — submitting with Enter key")
                    pw.send_keys(Keys.RETURN)
                time.sleep(random.uniform(5, 8))
            else:
                print("No credentials in env — please login manually in the browser.")
        except TimeoutException as e:
            print(f"Login form not found ({e}) — LinkedIn may be showing a different screen.")

        # If still not logged in (captcha / 2FA / pin), wait for the user to finish
        # in the Chrome window. We poll instead of using input() so this works when
        # the bot is launched as a background process.
        deadline = time.time() + 600  # 10 minutes
        if not self._is_logged_in():
            print("\n>>> Login challenge detected. Please complete it in the Chrome window.")
            print(">>> The bot will auto-detect when you're on the LinkedIn feed and continue.\n")
        while not self._is_logged_in() and time.time() < deadline:
            time.sleep(5)

        if self._is_logged_in():
            print("Logged in successfully.")
        else:
            print("Timed out waiting for login — continuing anyway.")

    # ------------------------------------------------------------- job search
    def get_base_search_url(self, parameters):
        job_types_url = "f_JT="
        job_types = parameters.get("jobTypes", {})
        job_types_url += "%2C".join([k[0].upper() for k in job_types if job_types[k]])

        date_url = ""
        dates = {
            "all_time": "",
            "month": "&f_TPR=r2592000",
            "week": "&f_TPR=r604800",
            "last_24_hours": "&f_TPR=r86400",
            "3_days": "&f_TPR=r259200",
        }
        for k, v in parameters.get("datePosted", {}).items():
            if v:
                date_url = dates.get(k, "")
                break
        return "&".join(t for t in [job_types_url, date_url] if t)

    def avoid_lock(self):
        # pyautogui is platform-touchy and not needed for the core flow — best-effort only.
        if self.config.get("disableAntiLock", False):
            return
        try:
            import pyautogui  # noqa: WPS433 (intentional lazy import)
            pyautogui.keyDown("ctrl")
            pyautogui.press("esc")
            pyautogui.keyUp("ctrl")
            time.sleep(1.0)
            pyautogui.press("esc")
        except Exception:
            pass

    def scroll_down_page(self, percentage=20):
        scroll_height = self.driver.execute_script("return document.body.scrollHeight")
        self.driver.execute_script(f"window.scrollBy(0, {scroll_height * (percentage / 100)});")
        time.sleep(random.uniform(1, 2))

    def scroll_slow(self, scrollable_element, reverse=False):
        try:
            last_height = self.driver.execute_script("return arguments[0].scrollHeight;", scrollable_element)
            while True:
                self.driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scrollable_element)
                time.sleep(random.uniform(0.3, 1.0))
                new_height = self.driver.execute_script("return arguments[0].scrollHeight;", scrollable_element)
                if new_height == last_height:
                    break
                last_height = new_height
            if reverse:
                while last_height > 0:
                    self.driver.execute_script("arguments[0].scrollBy(0, -200);", scrollable_element)
                    time.sleep(random.uniform(0.3, 1.0))
                    last_height -= 200
        except Exception as e:
            print(f"Scroll error: {e}")

    def job_page(self, position, job_page):
        url = (
            "https://www.linkedin.com/jobs/search/?"
            + self.get_base_search_url(self.config)
            + "&keywords=" + quote_plus(position)
            + "&start=" + str(job_page * 25)
        )
        self.driver.get(url)
        self.avoid_lock()

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    def start_applying(self):
        for position in self.config["positions"]:
            try:
                print(f"Starting the search for {position}")
                self.job_page(position, 0)
                time.sleep(random.uniform(2, 4))

                job_count = self._read_job_count() or 25
                print(f"Job count parsed: {job_count}")

                print(f"Total jobs available for '{position}': {job_count}")
                if job_count == 0:
                    continue

                total_applied = 0
                for page in range(0, min(job_count // 25 + 1, self.config["maxJobPage"])):
                    print(f"Processing page {page + 1} for position '{position}'")
                    self.job_page(position, page)
                    time.sleep(random.uniform(3, 5))
                    try:
                        jobs_details = self.apply_jobs()
                        if jobs_details:
                            total_applied += len(jobs_details)
                            self.df_jobs = pd.concat([self.df_jobs, pd.DataFrame(jobs_details)], ignore_index=True)
                            self.df_jobs.to_csv(self.file_path, index=False)
                            print(f"Job details saved to {self.file_path}")
                    except Exception as e:
                        print(f"Error applying for jobs on page {page}: {e}")
                        continue
                print(f"Applied for {total_applied} jobs for the position: {position}.")
            except Exception as e:
                print(f"Error while processing position '{position}': {e}")

    # ----------------------------------------------------------------- filters
    def head_check(self, text):
        text = text.lower()
        return not any(k.lower() in text for k in self.config.get("blacklistedtitles", []))

    def jd_check(self, text):
        text = text.lower()
        return not any(k.lower() in text for k in self.config.get("blacklistedDescription", []))

    def emp_check(self, text):
        return not any(c in text for c in self.config.get("blacklistedEmployeeCounts", []))

    def company_check(self, text):
        text = text.lower()
        return not any(k.lower() in text for k in self.config.get("blacklistedcompanys", []))

    # -------------------------------------------------------------- job parsing
    def apply_jobs(self):
        try:
            # Soft guard: detect the "Jobs you may be interested in" fallback page.
            try:
                guard = self.driver.find_element(By.CLASS_NAME, "jobs-search-results-list__text")
                if "Jobs you may be interested in" in (guard.text or ""):
                    raise Exception("Nothing to do here, moving forward...")
            except NoSuchElementException:
                pass

            job_results = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.scaffold-layout__list"))
            )
            self.scroll_slow(job_results)
            self.scroll_slow(job_results, reverse=True)

            # Job tiles use [data-occludable-job-id]; also accept the legacy class.
            job_list = self.driver.find_elements(
                By.CSS_SELECTOR, "li[data-occludable-job-id], li.scaffold-layout__list-item"
            )
            print(f"Found {len(job_list)} jobs on this page")
            if len(job_list) == 0:
                raise Exception("No jobs found on this page.")

            jobs_details = []
            for job_tile in tqdm(job_list):
                try:
                    job_details = self.get_job_details(job_tile)
                    if job_details:
                        jobs_details.append(job_details)
                except Exception as e:
                    print(f"Error while getting job details: {e}")
                    continue
            print(f"Total jobs processed: {len(jobs_details)}")
            return jobs_details
        except NoSuchElementException as e:
            print(f"Element not found: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")

    def get_job_details(self, job_tile, save=True):
        try:
            job_title_element = job_tile.find_element(By.CLASS_NAME, "job-card-list__title--link")
            job_title = job_title_element.find_element(By.TAG_NAME, "strong").text

            company_name_element = job_tile.find_element(By.CLASS_NAME, "artdeco-entity-lockup__subtitle")
            company_name = company_name_element.find_element(By.TAG_NAME, "span").text

            if (job_title, company_name) in self.applied_jobs:
                return None
            if not self.company_check(company_name):
                return None
            if not self.head_check(job_title):
                return None

            retries = 0
            while retries < 3:
                try:
                    job_tile.find_element(By.CLASS_NAME, "job-card-list__title--link").click()
                    break
                except Exception:
                    retries += 1
                    if retries == 3:
                        return None

            time.sleep(random.uniform(3, 5))

            try:
                employee_count = self.driver.find_elements(By.CSS_SELECTOR, ".jobs-company__inline-information")[0].text
                if not self.emp_check(employee_count):
                    print(f"Employee count '{employee_count}' is not acceptable.")
                    return None
            except Exception:
                employee_count = None

            try:
                job_element = self.driver.find_element(By.CLASS_NAME, "job-details-jobs-unified-top-card__job-title")
                job_link = job_element.find_element(By.TAG_NAME, "a").get_attribute("href")
            except Exception:
                job_link = None

            job_id = self._extract_job_id(job_link) if job_link else None

            try:
                job_description = self.driver.find_element(By.ID, "job-details").text
                if not self.jd_check(job_description):
                    print("Job description is not acceptable.")
                    return None
            except Exception:
                job_description = None

            skills, referral_message = None, None
            role_variant = classify_role(job_title, job_description or "")
            try:
                if self.job_match_evaluator and job_description:
                    is_matching, skills, referral_message, role_variant = self.job_match_evaluator.check_job_match(
                        job_description=f"{job_description}\nJOB_LINK:{job_link}\nJOB_ID:{job_id}",
                        job_title=job_title,
                    )
                    if is_matching == "No":
                        print(f"Job description does not match {role_variant} resume.")
                        return None
            except Exception as e:
                print(f"AI match failed: {e}")

            try:
                job_location = self.driver.find_element(
                    By.CSS_SELECTOR, ".job-details-jobs-unified-top-card__tertiary-description-container"
                ).text.split("·")[0].strip()
            except Exception:
                job_location = None

            try:
                hirer_link = self.driver.find_element(By.CSS_SELECTOR, ".hirer-card__hirer-information a").get_attribute("href")
            except Exception:
                hirer_link = None

            try:
                company_link = self.driver.find_element(
                    By.CSS_SELECTOR, "div.job-details-jobs-unified-top-card__company-name a"
                ).get_attribute("href")
            except Exception:
                company_link = None

            if save:
                try:
                    easy_apply_button = self.driver.find_elements(
                        "xpath", "//button[@id='jobs-apply-button-id' and .//span[text()='Easy Apply']]"
                    )
                except Exception:
                    easy_apply_button = []
                if easy_apply_button:
                    try:
                        save_button = self.driver.find_element(By.CSS_SELECTOR, ".jobs-save-button")
                        if "Save" in save_button.text.split():
                            save_button.click()
                            try:
                                time.sleep(random.uniform(0.5, 1.5))
                                self.driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Dismiss')]").click()
                            except Exception:
                                pass
                    except Exception:
                        pass

            self.applied_jobs.append((job_title, company_name))
            return {
                "job_title": job_title,
                "job_location": job_location,
                "company_name": company_name,
                "company_link": company_link,
                "job_link": job_link,
                "job_id": job_id,
                "employee_count": employee_count,
                "hirer_link": hirer_link,
                "job_skills": skills,
                "referral_message": referral_message,
                "role_variant": role_variant,
            }
        except Exception as e:
            print(f"An error occurred while processing job details: {e}")
            return None

    def _read_job_count(self):
        """LinkedIn now shows e.g. 'Full Stack Developer in India | 2,000+ results'
        on a single line. Pull the number out wherever it lives.
        """
        for selector in [
            ".jobs-search-results-list__title-heading",
            ".jobs-search-results-list__subtitle",
            "div.jobs-search-results-list__title-heading--strong",
        ]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = (el.text or "").replace("\n", " ")
                m = re.search(r"([\d,]+)\+?\s*result", text, re.IGNORECASE)
                if m:
                    return int(m.group(1).replace(",", ""))
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_job_id(job_link):
        if not job_link:
            return None
        m = re.search(r"/jobs/view/(\d+)", job_link)
        if m:
            return m.group(1)
        m = re.search(r"currentJobId=(\d+)", job_link)
        return m.group(1) if m else None

    # ------------------------------------------------------- recruiter search
    def _build_note_for(self, variant, is_hirer, name, job_title, company, job_link):
        """Pick the right template + resume link based on (variant, is_hirer) and
        render the invite note.
        """
        if is_hirer:
            tmpl_key = "inviteNoteTemplateHirerFrontend" if variant == "frontend" else "inviteNoteTemplateHirer"
        else:
            tmpl_key = "inviteNoteTemplateFrontend" if variant == "frontend" else "inviteNoteTemplate"
        template = self.config.get(tmpl_key, "")
        resume_link = (
            self.config["resumeDriveLinkFrontend"] if variant == "frontend"
            else self.config["resumeDriveLink"]
        )
        bio = (
            self.config["candidateBioFrontend"] if variant == "frontend"
            else self.config["candidateBioFullstack"]
        )
        return build_invite_note(
            template=template,
            name=name,
            job_title=job_title,
            company=company,
            job_link=job_link or "",
            resume_link=resume_link,
            candidate_first_name=self.config["candidateFirstName"],
            candidate_bio=bio,
        )

    def _is_recruiter_headline(self, headline):
        if not self.config.get("recruitersOnly", True):
            return True  # accept everyone when filter disabled
        if not headline:
            return False
        text = headline.lower()
        return any(k in text for k in self.config.get("recruiterKeywords", []))

    def _extract_email_from_text(self, text):
        if not text:
            return None
        m = EMAIL_RE.search(text)
        return m.group(0) if m else None

    def _extract_all_emails_from_text(self, text):
        """Return every distinct email address found in `text`, order-preserved."""
        if not text:
            return []
        seen = []
        for m in EMAIL_RE.findall(text):
            addr = m.strip().strip(".,;:)>]")
            if addr and addr.lower() not in [s.lower() for s in seen]:
                seen.append(addr)
        return seen

    def _extract_role_company_from_post(self, text):
        """Best-effort parse of a job role and company name straight from a post's
        text. Heuristic only — returns (role, company), either may be "".
        """
        if not text:
            return "", ""
        # Collapse whitespace and strip out email addresses first, so an address
        # like "careers@datax.com" can't masquerade as the company name.
        flat = EMAIL_RE.sub(" ", text)
        flat = re.sub(r"\s+", " ", flat).strip()

        role = ""
        company = ""

        # ---- Role: look for common "hiring/looking for <role>" phrasings. -------
        # Role char class deliberately excludes '.' so a sentence period ends the
        # match (e.g. "... Analyst position. Apply now" stops at "position").
        role_chars = r"[A-Za-z0-9/\+\-&'’ ]"
        role_patterns = [
            rf"hiring(?:\s+(?:a|an|for|now))?\s*:?\s*({role_chars}{{3,60}}?)(?=\s+(?:at|@|in|for|with|to|\(|[-–—|.,!]|$))",
            rf"looking for(?:\s+(?:a|an))?\s+({role_chars}{{3,60}}?)(?=\s+(?:at|@|in|for|with|to|\(|[-–—|.,!]|$))",
            rf"(?:role|position|opening|opportunity|vacancy)\s*:?\s*({role_chars}{{3,60}}?)(?=\s+(?:at|@|in|for|with|\(|[-–—|.,!]|$)|[.])",
            rf"open(?:ing)?\s+for\s+(?:a|an)?\s*({role_chars}{{3,60}}?)(?=\s+(?:at|@|in|for|with|\(|[-–—|.,!]|$))",
        ]
        for pat in role_patterns:
            m = re.search(pat, flat, re.IGNORECASE)
            if m:
                role = m.group(1).strip(" -–—|:,.")
                break

        # ---- Company: "at <Company>" / "@ <Company>" / "join <Company>". --------
        # The keyword is case-insensitive, but `(?-i:[A-Z])` forces the company to
        # start with a real capital so "at the office" / lowercase words don't match.
        company_patterns = [
            r"\bat\s+((?-i:[A-Z])[A-Za-z0-9&.\-’' ]{1,40}?)(?=\s*(?:is|are|[-–—|(.,!]|hiring|located|based|$))",
            r"@\s*((?-i:[A-Z])[A-Za-z0-9&.\-’' ]{1,40}?)(?=\s*(?:is|are|[-–—|(.,!]|$))",
            r"\bjoin\s+((?-i:[A-Z])[A-Za-z0-9&.\-’' ]{1,40}?)(?=\s*(?:is|are|[-–—|(.,!]|team|$))",
        ]
        for pat in company_patterns:
            m = re.search(pat, flat, re.IGNORECASE)
            if m:
                company = m.group(1).strip(" -–—|:,.")
                break

        return role, company

    def _build_post_invite_note(self, name, role, company, post_link):
        """Render the connection-invite note used when reaching out to someone who
        posted a hiring opportunity."""
        template = self.config.get("postInviteNoteTemplate") or DEFAULT_INVITE_NOTE_TEMPLATE_HIRER
        return build_invite_note(
            template,
            name=name,
            job_title=role or "the role you posted",
            company=company,
            job_link=post_link or "",
            resume_link=self.config.get("resumeDriveLink", DEFAULT_RESUME_DRIVE_LINK),
            candidate_first_name=self.config.get("candidateFirstName", DEFAULT_CANDIDATE_FIRST_NAME),
            candidate_bio=self.config.get("candidateBioFullstack", DEFAULT_CANDIDATE_BIO_FULLSTACK),
        )

    def _send_invite_with_note(self, profile, note):
        """Click Connect on a search-result tile and try to attach a personalised note.

        Returns "noted" / "no-note" / "pending-no-button" / "limit" / "skipped".
        """
        try:
            connect_btn = profile.find_element(By.XPATH, ".//button[span[text()='Connect']]")
        except NoSuchElementException:
            # Try inside the "More" dropdown.
            try:
                more_btn = profile.find_element(By.XPATH, ".//button[contains(@aria-label, 'More actions')]")
                more_btn.click()
                time.sleep(random.uniform(1, 2))
                self.driver.find_element(By.XPATH, "//div[@role='menu']//span[text()='Connect']").click()
            except Exception:
                return "skipped"
        else:
            connect_btn.click()

        time.sleep(random.uniform(1.5, 2.5))

        # Modal dialog appears.
        try:
            modal = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog']"))
            )
        except TimeoutException:
            return "pending-no-button"

        # Detect connection limit error inside modal.
        try:
            if "You've reached the weekly invitation limit" in modal.text or "invitation limit" in modal.text.lower():
                return "limit"
        except Exception:
            pass

        if not self.config.get("sendInviteNote", True) or not note:
            try:
                modal.find_element(By.XPATH, ".//button[.//span[text()='Send without a note'] or @aria-label='Send now']").click()
                return "no-note"
            except Exception:
                try:
                    modal.find_element(By.XPATH, ".//button[.//span[text()='Send']]").click()
                    return "no-note"
                except Exception:
                    return "skipped"

        # Try to open the note input.
        try:
            add_note_btn = modal.find_element(By.XPATH, ".//button[.//span[text()='Add a note']]")
            add_note_btn.click()
            time.sleep(random.uniform(0.8, 1.4))
        except NoSuchElementException:
            # Some flows show textarea immediately.
            pass

        try:
            textarea = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div[role='dialog'] textarea"))
            )
            textarea.clear()
            textarea.send_keys(note[:INVITE_NOTE_MAX])
            time.sleep(random.uniform(0.5, 1.0))
            send_btn = self.driver.find_element(
                By.XPATH, "//div[@role='dialog']//button[.//span[text()='Send'] or @aria-label='Send now']"
            )
            send_btn.click()
            return "noted"
        except Exception as e:
            # Couldn't attach note (likely free-tier monthly limit hit). Fall back to no-note.
            try:
                self.driver.find_element(
                    By.XPATH, "//div[@role='dialog']//button[.//span[text()='Send without a note']]"
                ).click()
                return "no-note"
            except Exception:
                print(f"Invite send fallback failed: {e}")
                return "skipped"

    def get_connect_people_for_job(self, job_row):
        """For a single job CSV row, first invite the hirer who posted the job,
        then visit the company's people page and connect with recruiters.
        Returns (records, connection_failed).
        """
        results = []
        connection_failed = False

        variant = job_row.get("role_variant")
        if not variant or (isinstance(variant, float) and pd.isna(variant)):
            variant = classify_role(job_row.get("job_title") or "", "")

        # ---------- Step 1: invite the hirer (the LinkedIn member who posted) ----
        hirer_link = job_row.get("hirer_link")
        if self.config.get("contactHirerFirst", True) and isinstance(hirer_link, str) and hirer_link.startswith("http"):
            hirer_link_clean = hirer_link.split("?")[0]
            if hirer_link_clean not in self.contacted_profiles:
                try:
                    hirer_result, failed = self._invite_hirer(job_row, hirer_link_clean, variant)
                    if hirer_result:
                        results.append(hirer_result)
                        self.contacted_profiles.add(hirer_link_clean)
                        self._append_connection_row(hirer_result)
                    if failed:
                        return results, True
                except Exception as e:
                    print(f"Hirer invite failed for {hirer_link_clean}: {e}")

        # ---------- Step 2: company people search → recruiters --------------------
        company_link = job_row.get("company_link")
        if not company_link or "/company/" not in str(company_link):
            return results, connection_failed
        company_id = company_link.split("/company/")[1].split("/")[0]

        self.driver.get(f"https://www.linkedin.com/company/{company_id}/people")
        time.sleep(random.uniform(3, 5))

        searches = self.config.get("people_profiles", ["Recruiter", "Hiring"])
        max_people = self.config.get("maxPeoplePerProfile", 3)

        for search in searches:
            if connection_failed:
                break
            people_count = 0
            try:
                # Reset any prior filter.
                try:
                    self.driver.execute_script("window.scrollTo(0, 0);")
                    self.scroll_down_page(10)
                    clear_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Clear all']"))
                    )
                    clear_btn.click()
                    WebDriverWait(self.driver, 3).until_not(
                        EC.presence_of_element_located((By.XPATH, "//button[normalize-space()='Clear all']"))
                    )
                    time.sleep(random.uniform(2, 3))
                except Exception:
                    pass

                search_box = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "people-search-keywords"))
                )
                search_box.clear()
                search_box.send_keys(search, Keys.RETURN)
                time.sleep(random.uniform(2, 4))
                self.scroll_down_page(30)

                profiles = self.driver.find_elements(
                    By.CSS_SELECTOR, "div.scaffold-finite-scroll__content ul li"
                )
            except Exception as e:
                print(f"People-search '{search}' failed: {e}")
                continue

            for profile in profiles:
                if people_count >= max_people or connection_failed:
                    break

                try:
                    profile_link = profile.find_element(By.TAG_NAME, "a").get_attribute("href")
                    profile_link = profile_link.split("?")[0] if profile_link else profile_link
                    profile_name = profile.find_element(
                        By.XPATH, ".//div[contains(@class, 'lt-line-clamp--single-line')]"
                    ).text.strip()
                except Exception:
                    continue

                if profile_link in self.contacted_profiles:
                    continue

                try:
                    profile_headline = profile.find_element(
                        By.XPATH, ".//div[contains(@class, 'lt-line-clamp--multi-line')]"
                    ).text.strip()
                except Exception:
                    profile_headline = ""

                if not self._is_recruiter_headline(profile_headline):
                    continue

                visible_text = (profile.text or "")
                email = self._extract_email_from_text(visible_text)

                variant = job_row.get("role_variant")
                if not variant or (isinstance(variant, float) and pd.isna(variant)):
                    variant = classify_role(job_row.get("job_title") or "", "")
                note = self._build_note_for(
                    variant=variant,
                    is_hirer=False,
                    name=profile_name,
                    job_title=job_row.get("job_title"),
                    company=job_row.get("company_name"),
                    job_link=job_row.get("job_link"),
                )

                # Already a 1st-degree connection? Skip the invite, just record.
                already_connected = False
                try:
                    profile.find_element(By.XPATH, ".//button[span[text()='Message']]")
                    already_connected = True
                except NoSuchElementException:
                    pass

                if already_connected:
                    status = "connected"
                    note_sent = False
                else:
                    outcome = self._send_invite_with_note(profile, note)
                    if outcome == "limit":
                        print("Weekly invitation limit reached.")
                        connection_failed = True
                        continue
                    if outcome == "skipped":
                        continue
                    status = "pending" if outcome in {"noted", "no-note"} else "unknown"
                    note_sent = outcome == "noted"
                    time.sleep(random.uniform(1.5, 3.0))

                record = {
                    "job_title": job_row.get("job_title"),
                    "company_name": job_row.get("company_name"),
                    "job_link": job_row.get("job_link"),
                    "profile_link": profile_link,
                    "profile_name": profile_name,
                    "profile_headline": profile_headline,
                    "email": email,
                    "status": status,
                    "note_sent": note_sent,
                    "role_variant": variant,
                    "is_hirer": False,
                    "email_sent": False,
                }
                results.append(record)
                self.contacted_profiles.add(profile_link)
                self._append_connection_row(record)
                people_count += 1

        return results, connection_failed

    def _invite_hirer(self, job_row, hirer_link, variant):
        """Navigate to the hirer's LinkedIn profile and send a personalised invite.

        Returns (record_dict_or_None, connection_failed_bool).
        """
        try:
            self.driver.get(hirer_link)
            time.sleep(random.uniform(3, 5))
        except Exception as e:
            print(f"Could not load hirer profile {hirer_link}: {e}")
            return None, False

        # Pull name + headline off the top card.
        try:
            name = self.driver.find_element(By.CSS_SELECTOR, "h1.text-heading-xlarge, h1").text.strip()
        except Exception:
            name = ""
        try:
            headline = self.driver.find_element(
                By.CSS_SELECTOR, "div.text-body-medium.break-words"
            ).text.strip()
        except Exception:
            headline = ""

        # Already a 1st-degree connection?
        already_connected = False
        try:
            self.driver.find_element(
                By.XPATH, "//main//button[.//span[text()='Message']]"
            )
            already_connected = True
        except NoSuchElementException:
            pass

        note = self._build_note_for(
            variant=variant,
            is_hirer=True,
            name=name,
            job_title=job_row.get("job_title"),
            company=job_row.get("company_name"),
            job_link=job_row.get("job_link"),
        )

        if already_connected:
            return {
                "job_title": job_row.get("job_title"),
                "company_name": job_row.get("company_name"),
                "job_link": job_row.get("job_link"),
                "profile_link": hirer_link,
                "profile_name": name,
                "profile_headline": headline,
                "email": None,
                "status": "connected",
                "note_sent": False,
                "role_variant": variant,
                "is_hirer": True,
            }, False

        outcome = self._send_invite_from_profile_page(note)
        if outcome == "limit":
            return None, True
        if outcome == "skipped":
            return None, False

        return {
            "job_title": job_row.get("job_title"),
            "company_name": job_row.get("company_name"),
            "job_link": job_row.get("job_link"),
            "profile_link": hirer_link,
            "profile_name": name,
            "profile_headline": headline,
            "email": None,
            "status": "pending" if outcome in {"noted", "no-note"} else "unknown",
            "note_sent": outcome == "noted",
            "role_variant": variant,
            "is_hirer": True,
        }, False

    def _dump_connect_debug(self, reason):
        """Save the current page (HTML + screenshot) once per run so the Connect
        flow can be refined when LinkedIn changes its profile DOM."""
        print(f"  [_dump_connect_debug] reason={reason}", flush=True)
        if getattr(self, "_connect_dumped", False):
            return
        self._connect_dumped = True
        try:
            with open(os.path.join(OUTPUT_DIR, "connect_debug.html"), "w") as f:
                f.write(self.driver.page_source or "")
            self.driver.save_screenshot(os.path.join(OUTPUT_DIR, "connect_debug.png"))
            print(f"  (connect debug saved to output/connect_debug.*)", flush=True)
        except Exception as e:
            print(f"  (connect debug dump failed: {e})", flush=True)

    def _click_el(self, el):
        """Robust click — fall back to a JS click when the element is obscured."""
        try:
            el.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", el)

    @staticmethod
    def _xp_literal(s):
        """Quote an arbitrary string for use as an XPath string literal
        (handles names containing quotes/apostrophes)."""
        if '"' not in s:
            return f'"{s}"'
        if "'" not in s:
            return f"'{s}'"
        return "concat('" + s.replace("'", "', \"'\", '") + "')"

    def _profile_owner_name(self):
        """The profile owner's display name. The new DOM has no <h1>, but the
        document title is "<Name> | LinkedIn" (sometimes "(N) <Name> | LinkedIn")."""
        try:
            t = (self.driver.title or "").strip()
            t = re.sub(r'^\(\d+\)\s*', '', t)      # drop "(3) " notification prefix
            if "|" in t:
                t = t.split("|")[0].strip()
            if t and t.lower() != "linkedin":
                return t
        except Exception:
            pass
        try:
            return self.driver.find_element(By.CSS_SELECTOR, "main h1, h1").text.strip()
        except Exception:
            return ""

    def _open_connect_dialog(self):
        """Click Connect for the PROFILE OWNER, either directly on the top card or
        via the "More" (3-dots) overflow menu — then the caller attaches the note.

        We scope strictly to the owner (matched by name) so we never click the
        "People you may know" quick-invite buttons elsewhere on the page. Classes
        are hashed/obfuscated, so we match on aria-label and visible text only.
        """
        owner = self._profile_owner_name()
        inv_label = f"Invite {owner} to connect" if owner else None
        print(f"  [connect] owner={owner!r}", flush=True)

        # 1) Direct owner Connect button on the top card (precise to the owner).
        direct = []
        if inv_label:
            direct.append(f"//button[@aria-label={self._xp_literal(inv_label)}]")
        # Generic top-card Connect immediately after the owner's <h1>.
        direct.append("//h1/following::button[.//span[normalize-space()='Connect']][1]")
        for xp in direct:
            try:
                btn = self.driver.find_element(By.XPATH, xp)
                self._click_el(btn)
                print("  [connect] clicked direct owner Connect", flush=True)
                return True
            except Exception:
                continue

        # 2) Open the owner's "More" overflow menu, then click Connect inside it.
        item_xps = []
        if inv_label:
            item_xps.append(f"//*[@aria-label={self._xp_literal(inv_label)}]")
        item_xps += [
            "//div[@role='menu']//*[normalize-space()='Connect']",
            "//*[@role='menuitem'][contains(normalize-space(.), 'Connect')]",
            "//div[contains(@class,'dropdown') or @role='menu']//span[normalize-space()='Connect']",
        ]
        try:
            more_btns = self.driver.find_elements(By.XPATH, "//button[@aria-label='More']")
        except Exception:
            more_btns = []
        for mi, mb in enumerate(more_btns):
            try:
                self._click_el(mb)
                time.sleep(random.uniform(0.9, 1.6))
            except Exception:
                continue
            # Log what the just-opened menu actually offers (useful diagnostics).
            try:
                opts = []
                for el in self.driver.find_elements(
                        By.XPATH, "//div[@role='menu']//*[self::span or self::div][normalize-space()][string-length(normalize-space())<40]"):
                    txt = (el.text or "").strip()
                    if txt and txt not in opts:
                        opts.append(txt)
                if opts:
                    print(f"  [connect] More#{mi} menu options: {opts[:12]}", flush=True)
            except Exception:
                pass
            for cxp in item_xps:
                try:
                    item = self.driver.find_element(By.XPATH, cxp)
                except Exception:
                    continue
                # Clicking the inner <span> often doesn't fire the menu item —
                # resolve to the nearest clickable (menuitem / button / a) ancestor.
                target = item
                try:
                    target = item.find_element(
                        By.XPATH, "./ancestor-or-self::*[@role='menuitem' or @role='button' or self::button or self::a][1]")
                except Exception:
                    pass
                self._click_el(target)
                print("  [connect] clicked Connect via More menu", flush=True)
                return True
            # Close this menu before trying the next "More" button.
            try:
                self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                time.sleep(0.4)
            except Exception:
                pass
        return False

    def _send_invite_from_profile_page(self, note):
        """Click Connect on the currently-loaded profile page and try to attach
        a personalised note. Same return contract as _send_invite_with_note.
        """
        if not self._open_connect_dialog():
            self._dump_connect_debug("no-connect-button")
            return "skipped"

        # The invite modal is a native <dialog> rendered inside an about:blank
        # iframe, with buttons matched by visible TEXT (classes are obfuscated).
        # So we try the main document first, then each iframe.
        time.sleep(random.uniform(1.5, 2.2))
        want_note = bool(self.config.get("sendInviteNote", True) and note)

        outcome = self._complete_invite_in_context(note, want_note)
        if outcome:
            return outcome
        for fr in self.driver.find_elements(By.TAG_NAME, "iframe"):
            try:
                self.driver.switch_to.frame(fr)
                outcome = self._complete_invite_in_context(note, want_note)
            except Exception:
                outcome = None
            finally:
                self.driver.switch_to.default_content()
            if outcome:
                return outcome

        self._dump_connect_debug("no-dialog")
        return "pending-no-button"

    _JS_DEEP_BUTTON = r"""
const wants = arguments[0].map(s => s.toLowerCase());
const hit = (e) => {
  const t = (e.textContent || '').replace(/\s+/g,' ').trim().toLowerCase();
  let al = '';
  try { al = (e.getAttribute('aria-label') || '').trim().toLowerCase(); } catch (x) {}
  return wants.some(w => t === w || al === w);
};
const visit = (root) => {
  let btns; try { btns = root.querySelectorAll('button,[role=button]'); } catch (x) { btns = []; }
  for (const e of btns) if (hit(e)) return e;
  let all; try { all = root.querySelectorAll('*'); } catch (x) { all = []; }
  for (const e of all) if (e.shadowRoot) { const r = visit(e.shadowRoot); if (r) return r; }
  return null;
};
return visit(document);
"""
    _JS_DEEP_FIELD = r"""
const visit = (root) => {
  let f; try { f = root.querySelector('textarea,[contenteditable="true"],[role="textbox"]'); } catch (x) { f = null; }
  if (f) return f;
  let all; try { all = root.querySelectorAll('*'); } catch (x) { all = []; }
  for (const e of all) if (e.shadowRoot) { const r = visit(e.shadowRoot); if (r) return r; }
  return null;
};
return visit(document);
"""

    def _deep_find_button(self, texts):
        """Recursively search the document AND open shadow roots for a button whose
        text/aria-label exactly matches one of `texts`. Returns a WebElement or None."""
        try:
            return self.driver.execute_script(self._JS_DEEP_BUTTON, texts)
        except Exception:
            return None

    def _deep_find_field(self):
        try:
            return self.driver.execute_script(self._JS_DEEP_FIELD)
        except Exception:
            return None

    def _complete_invite_in_context(self, note, want_note):
        """Within the current frame context, drive the invite <dialog>: optionally
        "Add a note" → type → "Send"; else "Send without a note". Returns
        "noted"/"no-note"/"limit" if it acted here, or None if no modal is present."""
        add_note_xps = [
            "//button[normalize-space()='Add a note']",
            "//button[.//span[normalize-space()='Add a note']]",
            "//button[@aria-label='Add a note']",
        ]
        send_xps = [
            "//button[normalize-space()='Send invitation']",
            "//button[@aria-label='Send invitation']",
            "//button[normalize-space()='Send']",
            "//button[.//span[normalize-space()='Send']]",
        ]
        send_wo_xps = [
            "//button[normalize-space()='Send without a note']",
            "//button[.//span[normalize-space()='Send without a note']]",
            "//button[@aria-label='Send without a note']",
        ]

        def _present(xps):
            for xp in xps:
                els = self.driver.find_elements(By.XPATH, xp)
                if els:
                    return els[0]
            return None

        # Deep (shadow-piercing) button finders — LinkedIn renders the invite
        # <dialog> inside shadow roots that XPath/page_source can't see.
        add_note_texts = ["add a note"]
        send_texts = ["send invitation", "send"]
        send_wo_texts = ["send without a note"]

        def _click_text(texts, xps):
            el = self._deep_find_button(texts) or _present(xps)
            if el is None:
                return False
            self._click_el(el)
            return True

        # Is the invite modal present in this context (light DOM or shadow)?
        has_modal = bool(
            self.driver.find_elements(By.CSS_SELECTOR, "dialog")
            or _present(add_note_xps) or _present(send_wo_xps)
            or self._deep_find_button(add_note_texts)
            or self._deep_find_button(send_wo_texts)
        )
        if not has_modal:
            return None

        # Weekly-limit guard.
        try:
            body_txt = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if "invitation limit" in body_txt or "you've reached the weekly" in body_txt:
                return "limit"
        except Exception:
            pass

        if want_note:
            if _click_text(add_note_texts, add_note_xps):
                print("  [connect] clicked 'Add a note'", flush=True)
                time.sleep(random.uniform(0.8, 1.4))
            # Type into the note field (textarea / contenteditable), shadow-aware.
            field = self._deep_find_field()
            if field is None:
                for sel in ("textarea#custom-message", "textarea[name='message']",
                            "dialog textarea", "textarea", "div[contenteditable='true']"):
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        field = els[0]
                        break
            if field is not None:
                try:
                    field.clear()
                except Exception:
                    pass
                try:
                    field.send_keys(note[:INVITE_NOTE_MAX])
                    print(f"  [connect] typed note ({len(note[:INVITE_NOTE_MAX])} chars)", flush=True)
                    time.sleep(random.uniform(0.5, 1.0))
                    if _click_text(send_texts, send_xps):
                        print("  [connect] clicked Send (with note)", flush=True)
                        return "noted"
                except Exception as e:
                    print(f"  [connect] note typing failed: {e}", flush=True)
            # Couldn't attach the note — send without it rather than abandon.
            if _click_text(send_wo_texts, send_wo_xps) or _click_text(send_texts, send_xps):
                return "no-note"
            return None

        # Note disabled — send without one.
        if _click_text(send_wo_texts, send_wo_xps) or _click_text(send_texts, send_xps):
            return "no-note"
        return None

    def _append_connection_row(self, record):
        self.df_connections = pd.concat(
            [self.df_connections, pd.DataFrame([record])], ignore_index=True
        )
        self.df_connections.to_csv(self.connections_path, index=False)

    def extract_emails(self, only_accepted=True, max_visits=None):
        """Stage 3 — visit each connection profile and read the email from
        "Contact info". LinkedIn only exposes an email after the person has
        accepted the invite, so by default we only revisit rows where status
        is "connected".

        Set `only_accepted=False` to try every row (pending invites usually
        fail). Writes results back into `connections.csv`.
        """
        if not os.path.exists(self.connections_path):
            print("No connections.csv yet — run Stage 2 first.")
            return

        df = pd.read_csv(self.connections_path)
        if "email" not in df.columns:
            df["email"] = None
        candidates = df[df["email"].isna() | (df["email"].astype(str).str.strip() == "")]
        if only_accepted and "status" in candidates.columns:
            candidates = candidates[candidates["status"].astype(str).str.lower() == "connected"]
        if max_visits is not None:
            candidates = candidates.head(int(max_visits))

        print(f"Stage 3: extracting emails from {len(candidates)} profiles…")

        for idx, row in tqdm(list(candidates.iterrows()), desc="Profiles"):
            url = row.get("profile_link")
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            try:
                self.driver.get(url)
                time.sleep(random.uniform(3, 5))
                email = self._read_contact_info_email()
                if email:
                    df.at[idx, "email"] = email
                    df.to_csv(self.connections_path, index=False)
                    print(f"  • {row.get('profile_name')} → {email}")
            except Exception as e:
                print(f"  ! Failed for {url}: {e}")
                continue

        print(f"Stage 3 done. Total emails on file: {df['email'].notna().sum()}")

    # ------------------------------------------------------- post search + emails
    def search_recent_posts(self, keywords: list[str] | None = None, max_per_keyword: int | None = None, recent_24_hours: bool = True, connect_with_posters: bool | None = None):
        """Search LinkedIn posts for `keywords`, collect *all* emails mentioned in
        each post along with the person who posted it (and a best-effort role +
        company parsed from the post), then automatically send a connection
        request with a note to each unique poster.

        Writes one row per discovered email (plus one row for posters with no
        email) to `posts_emails.csv` with columns:
          keyword, post_link, profile_name, profile_link, role, company,
          post_text, email, connect_status, note_sent, email_sent
        """
        keywords = list(keywords or self.config.get("postSearch", {}).get("keywords", []))
        if not keywords:
            print("No post-search keywords configured.")
            return
        max_per_keyword = max_per_keyword or self.config.get("postSearch", {}).get("maxPostsPerKeyword", 20)
        max_per_keyword = min(max(int(max_per_keyword), 20), 50)
        if connect_with_posters is None:
            connect_with_posters = self.config.get("connectWithPosters", True)
        # A post must signal hiring intent to count as a job post (not a random update).
        ps_cfg = self.config.get("postSearch", {}) or {}
        must_include = [
            str(p).lower() for p in ps_cfg.get("mustInclude", ["hiring", "looking for"])
        ] or ["hiring", "looking for"]
        # ...and must NOT look like a job-seeker / "open to work" post — we only
        # want to reach people who are HIRING, never candidates seeking jobs.
        must_exclude = [
            str(p).lower() for p in ps_cfg.get("mustExclude", DEFAULT_SEEKER_PHRASES)
        ]

        # ---------- Pass 1: scrape posts (no navigation away from results) -------
        # Diagnostics persisted to output/posts_debug.json so a 0-result run can
        # be understood without watching the browser (stdout is block-buffered).
        debug = {"keywords": keywords, "recent_24_hours": recent_24_hours, "per_keyword": []}
        scraped = []          # one entry per unique post
        seen_post_keys = set()
        print(f"Searching posts for keywords: {keywords}", flush=True)

        try:
            debug["logged_in"] = bool(self._is_logged_in())
        except Exception:
            debug["logged_in"] = None

        # Broad, class-agnostic selectors. `data-urn`/`data-id` carrying an
        # activity URN survives LinkedIn's frequent CSS class churn.
        TILE_SELECTORS = (
            "div[data-urn*='urn:li:activity']",
            "div[data-id*='urn:li:activity']",
            "div.feed-shared-update-v2",
            "div.update-components-update-v2",
            "div.occludable-update",
            "div.search-result__wrapper",
            # LinkedIn now serves content-search results as obfuscated <li>s with
            # hashed class names and no activity URN, rendered OUTSIDE <main>.
            # Fall back to every <li> and filter by content (actor link +
            # substantial text) below.
            "li",
        )

        for kw in keywords:
            kw_dbg = {"keyword": kw, "auth_wall": False, "raw_tiles": 0, "collected": 0, "sample": ""}
            try:
                q = quote_plus(kw)
                url = f"https://www.linkedin.com/search/results/content/?keywords={q}&origin=GLOBAL_SEARCH_HEADER"
                if recent_24_hours:
                    url += "&datePosted=%22past-24h%22"
                self.driver.get(url)
                time.sleep(random.uniform(2.5, 4.5))

                # Auth/login wall detection.
                cur = (self.driver.current_url or "").lower()
                if any(x in cur for x in ("/login", "authwall", "/checkpoint", "/uas/")):
                    kw_dbg["auth_wall"] = True
                    kw_dbg["landed_url"] = cur
                    print(f"  • {kw}: hit a login/auth wall ({cur}) — not logged in", flush=True)
                    debug["per_keyword"].append(kw_dbg)
                    continue

                # Actor-anchored scraping. LinkedIn's content-search DOM has no
                # stable post container (hashed classes, no role/article, no URN),
                # but every post has an actor profile link. So we start from each
                # `/in/` link and climb to the enclosing post container.
                collected = 0
                max_raw = 0
                seen_containers = set()
                for _ in range(6):
                    try:
                        actors = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/in/']")
                    except Exception:
                        actors = []
                    max_raw = max(max_raw, len(actors))

                    for actor in actors:
                        if collected >= max_per_keyword:
                            break
                        try:
                            href = (actor.get_attribute("href") or "").split("?")[0]
                            if "/in/" not in href:
                                continue

                            # Climb to the largest single-post ancestor: keep going
                            # up while the subtree text stays within one post's worth;
                            # stop before we reach the multi-post feed wrapper.
                            el = actor
                            container = None
                            for _ in range(15):
                                try:
                                    el = el.find_element(By.XPATH, "./..")
                                    t = el.text or ""
                                except Exception:
                                    break
                                if len(t) > 2200:
                                    break
                                container = el
                            if container is None:
                                continue
                            cid = container.id
                            if cid in seen_containers:
                                continue
                            seen_containers.add(cid)

                            post_text = (container.text or "").strip()
                            if len(post_text) < 60:
                                continue

                            # Keep only genuine job posts: the text must mention a
                            # hiring intent (settings.postSearch.mustInclude) and must
                            # NOT read like a job-seeker post (mustExclude).
                            low_text = post_text.lower()
                            if not any(p in low_text for p in must_include):
                                continue
                            if any(x in low_text for x in must_exclude):
                                print(f"  [skip] job-seeker post: {post_text[:60]!r}", flush=True)
                                continue

                            # Author = first /in/ link inside the container.
                            profile_link = href
                            profile_name = None
                            try:
                                a0 = container.find_element(By.CSS_SELECTOR, "a[href*='/in/']")
                                profile_link = (a0.get_attribute("href") or "").split("?")[0] or href
                                name = (a0.text or "").strip().split("\n")[0].strip()
                                if not name:
                                    try:
                                        name = a0.find_element(By.CSS_SELECTOR, "span[aria-hidden='true']").text.strip()
                                    except Exception:
                                        name = ""
                                profile_name = name or None
                            except Exception:
                                pass

                            # The actor anchor often has no visible text (avatar
                            # only). Recover the name from the post header, which
                            # reads "Feed post\n<Name>\n  • <degree>\n<headline>…".
                            lines = [ln.strip() for ln in post_text.split("\n") if ln.strip()]
                            if not profile_name and lines:
                                hdr = None
                                for i, ln in enumerate(lines):
                                    if ln.lower() == "feed post" and i + 1 < len(lines):
                                        hdr = lines[i + 1]
                                        break
                                profile_name = hdr or lines[0]

                            # Dedupe distinct posts by poster + first line of text.
                            dedupe_key = f"{profile_link}|{post_text[:80]}"
                            if dedupe_key in seen_post_keys:
                                continue
                            seen_post_keys.add(dedupe_key)

                            # Emails from the container's HTML (incl. mailto: and text
                            # collapsed behind "…more"), not just the visible text.
                            try:
                                tile_html = container.get_attribute("outerHTML") or ""
                            except Exception:
                                tile_html = ""
                            emails = self._extract_all_emails_from_text(
                                post_text + "\n" + tile_html.replace("mailto:", " ")
                            )

                            # Role/company come from the POST BODY, not the poster's
                            # job headline. The body starts after the "Follow" line.
                            body = post_text
                            if "\nFollow\n" in post_text:
                                body = post_text.split("\nFollow\n", 1)[1]
                            role, company = self._extract_role_company_from_post(body)

                            if not kw_dbg["sample"]:
                                kw_dbg["sample"] = post_text[:200]

                            scraped.append({
                                "keyword": kw,
                                "post_link": None,
                                "profile_name": profile_name,
                                "profile_link": profile_link,
                                "role": role,
                                "company": company,
                                "post_text": post_text,
                                "emails": emails,
                            })
                            collected += 1
                        except Exception:
                            continue
                    if collected >= max_per_keyword:
                        break
                    self.scroll_down_page(30)
                    time.sleep(random.uniform(1.2, 2.2))

                kw_dbg["raw_tiles"] = max_raw
                kw_dbg["collected"] = collected

                # When nothing was collected, capture the page so we can see WHY
                # (no-results state, different DOM, blocked, etc.).
                if collected == 0:
                    try:
                        kw_dbg["landed_url"] = self.driver.current_url
                        kw_dbg["page_title"] = self.driver.title
                    except Exception:
                        pass
                    try:
                        body = self.driver.find_element(By.TAG_NAME, "body").text or ""
                        kw_dbg["body_sample"] = body[:1200]
                    except Exception:
                        kw_dbg["body_sample"] = ""
                    probe = {
                        "li": "li",
                        "div[role=article]": "div[role='article']",
                        "search-results-container": "div.search-results-container",
                        "scaffold-finite-scroll": "div.scaffold-finite-scroll__content",
                        "feed-shared-update": "div.feed-shared-update-v2",
                        "update-components": "div.update-components-update-v2",
                        "no-results": "div.search-reusables__no-results, div.search-no-results",
                    }
                    counts = {}
                    for label, sel in probe.items():
                        try:
                            counts[label] = len(self.driver.find_elements(By.CSS_SELECTOR, sel))
                        except Exception:
                            counts[label] = -1
                    kw_dbg["selector_counts"] = counts
                    # Save a screenshot + HTML for the first failing keyword only.
                    if not debug.get("_dumped"):
                        debug["_dumped"] = True
                        try:
                            self.driver.save_screenshot(os.path.join(OUTPUT_DIR, "posts_debug.png"))
                            with open(os.path.join(OUTPUT_DIR, "posts_debug.html"), "w") as hf:
                                hf.write(self.driver.page_source or "")
                        except Exception:
                            pass
                print(f"  • {kw}: {max_raw} tiles on page, collected {collected} posts", flush=True)
            except Exception as e:
                kw_dbg["error"] = str(e)
                print(f"Search failed for '{kw}': {e}", flush=True)
            debug["per_keyword"].append(kw_dbg)

        # ---------- Pass 2: connect with each unique poster (with a note) -------
        # Done after scraping so navigating to profiles doesn't invalidate the
        # search-result elements we were iterating over.
        connect_map = {}      # profile_link -> {"connect_status": str, "note_sent": bool}
        if connect_with_posters:
            limit_hit = False
            posters = {}
            for item in scraped:
                link = item.get("profile_link")
                if link and "/in/" in link and link not in posters:
                    posters[link] = item
            print(f"Sending connection requests to {len(posters)} poster(s)...", flush=True)
            for link, item in posters.items():
                if limit_hit:
                    connect_map[link] = {"connect_status": "limit", "note_sent": False}
                    continue
                if link in self.contacted_profiles:
                    print(f"  connect[{link}] -> already-contacted", flush=True)
                    connect_map[link] = {"connect_status": "already-contacted", "note_sent": False}
                    continue
                note = self._build_post_invite_note(
                    name=item.get("profile_name") or "",
                    role=item.get("role") or "",
                    company=item.get("company") or "",
                    post_link=item.get("post_link") or "",
                )
                try:
                    self.driver.get(link)
                    time.sleep(random.uniform(3, 5))
                    # Already a 1st-degree connection?
                    try:
                        self.driver.find_element(By.XPATH, "//main//button[.//span[text()='Message']]")
                        print(f"  connect[{link}] -> connected (Message button present)", flush=True)
                        connect_map[link] = {"connect_status": "connected", "note_sent": False}
                        self.contacted_profiles.add(link)
                        continue
                    except NoSuchElementException:
                        pass
                    outcome = self._send_invite_from_profile_page(note)
                    print(f"  connect[{link}] -> {outcome}", flush=True)
                except Exception as e:
                    print(f"  connect[{link}] -> EXCEPTION {e}", flush=True)
                    connect_map[link] = {"connect_status": "error", "note_sent": False}
                    continue
                if outcome == "limit":
                    print("Weekly invitation limit reached — stopping connection requests.")
                    limit_hit = True
                    connect_map[link] = {"connect_status": "limit", "note_sent": False}
                    continue
                self.contacted_profiles.add(link)
                connect_map[link] = {
                    "connect_status": "pending" if outcome in {"noted", "no-note"} else outcome,
                    "note_sent": outcome == "noted",
                }
                time.sleep(random.uniform(1.5, 3.0))

        # ---------- Build rows: one per email (or one for emailless posters) ----
        rows = []
        for item in scraped:
            link = item.get("profile_link")
            conn = connect_map.get(link, {"connect_status": "", "note_sent": False})
            base = {
                "keyword": item["keyword"],
                "post_link": item["post_link"],
                "profile_name": item["profile_name"],
                "profile_link": link,
                "role": item["role"],
                "company": item["company"],
                "post_text": item["post_text"],
                "connect_status": conn["connect_status"],
                "note_sent": conn["note_sent"],
            }
            emails = item["emails"] or [None]
            for email in emails:
                rows.append({**base, "email": email, "email_sent": False})

        df = pd.DataFrame(rows)
        if os.path.exists(POSTS_CSV) and os.path.getsize(POSTS_CSV) > 1:
            try:
                prev = pd.read_csv(POSTS_CSV)
                df = pd.concat([prev, df], ignore_index=True)
            except pd.errors.EmptyDataError:
                pass
        # Drop duplicate (email, post_link) pairs accumulated across runs.
        if not df.empty and "email" in df.columns:
            df = df.drop_duplicates(subset=["email", "post_link"], keep="first").reset_index(drop=True)
        # Only overwrite the CSV when we actually have rows, so a 0-result run
        # doesn't blow away previously-collected data with an empty file.
        if not df.empty:
            df.to_csv(POSTS_CSV, index=False)
        n_emails = int(df["email"].astype(str).str.contains("@", na=False).sum()) if (not df.empty and "email" in df.columns) else 0
        debug["total_scraped"] = len(scraped)
        debug["rows_written"] = int(len(df))
        debug["emails_found"] = n_emails
        try:
            import json
            with open(os.path.join(OUTPUT_DIR, "posts_debug.json"), "w") as f:
                json.dump(debug, f, indent=2)
        except Exception:
            pass
        print(f"Saved {len(df)} post records ({n_emails} with emails) to {POSTS_CSV}", flush=True)
        if not scraped:
            print("No posts were scraped. See output/posts_debug.json for why "
                  "(login wall, zero tiles, or no recent posts).", flush=True)

    def send_emails_for_posts(self, subject_template: str | None = None, body_template: str | None = None, dry_run: bool = False, only_unsent: bool = True):
        """Send emails to addresses found in `posts_emails.csv` using Gmail creds from env.

        Marks `email_sent=True` in the CSV when successful.
        """
        if not os.path.exists(POSTS_CSV):
            print("No posts_emails.csv found — run post search first.")
            return
        import pandas as pd

        try:
            df = pd.read_csv(POSTS_CSV)
        except pd.errors.EmptyDataError:
            print("posts_emails.csv is empty — run post search first.")
            return
        if "email_sent" not in df.columns:
            df["email_sent"] = False
        # Normalise email_sent to real booleans (CSV round-trips can give "True"/NaN).
        df["email_sent"] = (
            df["email_sent"].astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
        )
        candidates = df[df["email"].astype(str).str.contains("@", na=False)]
        if only_unsent:
            candidates = candidates[~candidates["email_sent"]]

        creds = gmail_creds_from_env()
        if not creds:
            print("No Gmail creds found in environment (GMAIL_USER / GMAIL_APP_PASSWORD). Aborting.")
            return

        sent = 0
        already_emailed = set()   # lowercased addresses sent this run (dedupe)
        for idx, row in candidates.iterrows():
            to_addr = (str(row.get("email")) or "").strip()
            if not to_addr or "@" not in to_addr:
                continue
            # One email per unique address — skip if we already sent to it now.
            if to_addr.lower() in already_emailed:
                df.at[idx, "email_sent"] = True
                continue
            fields = {
                "name": (str(row.get("profile_name")) or "there").split()[0] if row.get("profile_name") else "there",
                "role": row.get("role") or "this role",
                "company": row.get("company") or "your company",
                "job_title": row.get("role") or "this role",
                **{
                    "candidate_name": self.config.get("candidateName"),
                    "candidate_first_name": self.config.get("candidateFirstName"),
                    "candidate_email": self.config.get("candidateEmail"),
                    "candidate_bio_long": self.config.get("candidateBioFullstack") or "",
                    "resume_link": self.config.get("resumeDriveLink", DEFAULT_RESUME_DRIVE_LINK),
                },
            }
            subject = (subject_template or self.config.get("emailSubjectTemplate") or "Hello")
            body = (body_template or self.config.get("emailBodyTemplate") or "")
            try:
                rendered_subject = subject.format(**fields)
                rendered_body = body.format(**fields)
            except Exception:
                rendered_subject, rendered_body = subject, body

            if dry_run:
                print(f"[dry-run] Would send to {to_addr}: {rendered_subject}")
                sent += 1
                already_emailed.add(to_addr.lower())
                df.at[idx, "email_sent"] = True
                continue

            try:
                send_one(creds=creds, to_addr=to_addr, subject=rendered_subject, body=rendered_body, from_name=self.config.get("candidateName"))
                already_emailed.add(to_addr.lower())
                # Mark every row sharing this address as sent.
                df.loc[df["email"].astype(str).str.lower() == to_addr.lower(), "email_sent"] = True
                sent += 1
                df.to_csv(POSTS_CSV, index=False)
                print(f"Sent email to {to_addr}")
            except Exception as e:
                print(f"Failed to send to {to_addr}: {e}")

        print(f"Email send complete. Sent to {sent} unique address(es).")

    def _read_contact_info_email(self):
        """On the currently-loaded profile, open the Contact Info overlay
        and scrape the email. Returns the email or None.
        """
        # Visible mailto in the page first (cheap)
        try:
            mailto = self.driver.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
            return mailto.get_attribute("href").replace("mailto:", "").split("?")[0].strip()
        except NoSuchElementException:
            pass

        # Otherwise open the Contact Info overlay.
        try:
            link = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "top-card-text-details-contact-info"))
            )
            link.click()
        except Exception:
            try:
                link = self.driver.find_element(By.XPATH, "//a[contains(@href,'overlay/contact-info')]")
                link.click()
            except Exception:
                return None

        time.sleep(random.uniform(1.5, 2.5))
        try:
            modal = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog']"))
            )
        except TimeoutException:
            return None

        email = None
        try:
            mailto = modal.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
            email = mailto.get_attribute("href").replace("mailto:", "").split("?")[0].strip()
        except NoSuchElementException:
            m = EMAIL_RE.search(modal.text or "")
            email = m.group(0) if m else None

        # Close the modal.
        try:
            self.driver.find_element(
                By.CSS_SELECTOR, "div[role='dialog'] button[aria-label='Dismiss']"
            ).click()
        except Exception:
            pass

        return email

    def populate_connections(self, continue_after_limit=False):
        print("Gathering and connecting recruiters per job!")
        if not os.path.exists(self.file_path):
            print("No jobs CSV yet — run start_applying first.")
            return

        df_jobs = pd.read_csv(self.file_path)
        if "connections" not in df_jobs.columns:
            df_jobs["connections"] = None

        for idx, row in tqdm(list(df_jobs.iterrows()), desc="Connecting per job"):
            existing = df_jobs.at[idx, "connections"]
            if isinstance(existing, str) and existing not in ("", "[]", "nan"):
                continue
            try:
                results, failed = self.get_connect_people_for_job(row.to_dict())
                df_jobs.at[idx, "connections"] = str(results)
                df_jobs.to_csv(self.file_path, index=False)
                if failed and not continue_after_limit:
                    print("connection limit reached — stopping.")
                    break
            except Exception as e:
                print(f"Error processing job '{row.get('job_title')}': {e}")
                continue


if __name__ == "__main__":
    bot = LinkedInBot(headless=False)
    bot.login()
    bot.start_applying()
    bot.populate_connections()
    bot.close()
