from __future__ import annotations

import os
import sys
current_file_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_file_path)

import re
import time
import random
import ast
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

        service = Service(ChromeDriverManager().install())
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
        try:
            user_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            if email and password:
                user_field.clear()
                user_field.send_keys(email)
                pw = self.driver.find_element(By.ID, "password")
                pw.clear()
                pw.send_keys(password)
                self.driver.find_element(By.CSS_SELECTOR, ".btn__primary--large").click()
                time.sleep(random.uniform(5, 8))
            else:
                print("No credentials in env — please login manually in the browser.")
        except TimeoutException:
            print("Login form not found — LinkedIn may be showing a different screen.")

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

    def _send_invite_from_profile_page(self, note):
        """Click Connect on the currently-loaded profile page and try to attach
        a personalised note. Same return contract as _send_invite_with_note.
        """
        try:
            connect_btn = self.driver.find_element(
                By.XPATH, "//main//button[.//span[text()='Connect']]"
            )
            connect_btn.click()
        except NoSuchElementException:
            # Try opening the "More" dropdown and finding Connect there.
            try:
                more_btn = self.driver.find_element(
                    By.XPATH, "//main//button[contains(@aria-label, 'More actions')]"
                )
                more_btn.click()
                time.sleep(random.uniform(1, 1.8))
                self.driver.find_element(
                    By.XPATH, "//div[@role='menu']//span[text()='Connect']"
                ).click()
            except Exception:
                return "skipped"

        time.sleep(random.uniform(1.5, 2.5))
        try:
            modal = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog']"))
            )
        except TimeoutException:
            return "pending-no-button"

        if "invitation limit" in (modal.text or "").lower() or "You've reached the weekly" in (modal.text or ""):
            return "limit"

        if not self.config.get("sendInviteNote", True) or not note:
            try:
                modal.find_element(
                    By.XPATH, ".//button[.//span[text()='Send without a note'] or @aria-label='Send now']"
                ).click()
                return "no-note"
            except Exception:
                return "skipped"

        # Click "Add a note" if present
        try:
            modal.find_element(By.XPATH, ".//button[.//span[text()='Add a note']]").click()
            time.sleep(random.uniform(0.8, 1.4))
        except NoSuchElementException:
            pass

        try:
            textarea = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div[role='dialog'] textarea"))
            )
            textarea.clear()
            textarea.send_keys(note[:INVITE_NOTE_MAX])
            time.sleep(random.uniform(0.5, 1.0))
            self.driver.find_element(
                By.XPATH, "//div[@role='dialog']//button[.//span[text()='Send'] or @aria-label='Send now']"
            ).click()
            return "noted"
        except Exception:
            try:
                self.driver.find_element(
                    By.XPATH, "//div[@role='dialog']//button[.//span[text()='Send without a note']]"
                ).click()
                return "no-note"
            except Exception:
                return "skipped"

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
    def search_recent_posts(self, keywords: list[str] | None = None, max_per_keyword: int | None = None, recent_24_hours: bool = True):
        """Search LinkedIn content (posts) for `keywords` and collect emails found in post text or profile snippets.

        Writes results to `posts_emails.csv` with columns:
          keyword, post_link, profile_name, profile_link, post_text, email, email_sent
        """
        keywords = list(keywords or self.config.get("postSearch", {}).get("keywords", []))
        if not keywords:
            print("No post-search keywords configured.")
            return
        max_per_keyword = max_per_keyword or self.config.get("postSearch", {}).get("maxPostsPerKeyword", 20)
        max_per_keyword = min(max(int(max_per_keyword), 20), 50)

        rows = []
        print(f"Searching posts for keywords: {keywords}")
        for kw in keywords:
            try:
                q = quote_plus(kw)
                url = f"https://www.linkedin.com/search/results/content/?keywords={q}&origin=GLOBAL_SEARCH_HEADER"
                if recent_24_hours:
                    url += "&datePosted=%22past-24h%22"
                self.driver.get(url)
                time.sleep(random.uniform(2.5, 4.5))
                # try scrolling and collecting post tiles
                collected = 0
                seen_links = set()
                for _ in range(6):
                    # try multiple common selectors for LinkedIn posts
                    candidates = []
                    for sel in ("div.feed-shared-update-v2", "div.occludable-update", "div.search-result__wrapper"):
                        try:
                            candidates.extend(self.driver.find_elements(By.CSS_SELECTOR, sel))
                        except Exception:
                            continue
                    for post in candidates:
                        if collected >= max_per_keyword:
                            break
                        try:
                            post_text = (post.text or "").strip()
                            # post link — try anchors that look like posts
                            post_link = None
                            try:
                                a = post.find_element(By.CSS_SELECTOR, "a[href*='/posts/'], a[href*='/feed/update/']")
                                post_link = a.get_attribute("href")
                            except Exception:
                                pass
                            # profile info
                            profile_name = None
                            profile_link = None
                            try:
                                actor = post.find_element(By.CSS_SELECTOR, "a.feed-shared-actor__container-link, a.feed-shared-actor__name")
                                profile_link = actor.get_attribute("href")
                                profile_name = actor.text.strip()
                            except Exception:
                                pass

                            email = self._extract_email_from_text(post_text)
                            # also check visible snippet for emails
                            if not email and profile_name:
                                email = self._extract_email_from_text(profile_name)

                            if post_link and post_link in seen_links:
                                continue
                            seen_links.add(post_link or f"{kw}-{collected}")

                            rows.append({
                                "keyword": kw,
                                "post_link": post_link,
                                "profile_name": profile_name,
                                "profile_link": profile_link,
                                "post_text": post_text,
                                "email": email,
                                "email_sent": False,
                            })
                            collected += 1
                        except Exception:
                            continue
                    if collected >= max_per_keyword:
                        break
                    self.scroll_down_page(30)
                    time.sleep(random.uniform(1.2, 2.2))
                print(f"  • {kw}: collected {collected} posts")
            except Exception as e:
                print(f"Search failed for '{kw}': {e}")
                continue

        # save CSV
        import pandas as pd

        df = pd.DataFrame(rows)
        if os.path.exists(POSTS_CSV):
            prev = pd.read_csv(POSTS_CSV)
            df = pd.concat([prev, df], ignore_index=True)
        df.to_csv(POSTS_CSV, index=False)
        print(f"Saved {len(df)} post records to {POSTS_CSV}")

    def send_emails_for_posts(self, subject_template: str | None = None, body_template: str | None = None, dry_run: bool = False, only_unsent: bool = True):
        """Send emails to addresses found in `posts_emails.csv` using Gmail creds from env.

        Marks `email_sent=True` in the CSV when successful.
        """
        if not os.path.exists(POSTS_CSV):
            print("No posts_emails.csv found — run post search first.")
            return
        import pandas as pd

        df = pd.read_csv(POSTS_CSV)
        if "email_sent" not in df.columns:
            df["email_sent"] = False
        candidates = df[df["email"].astype(str).str.contains("@", na=False)]
        if only_unsent:
            candidates = candidates[~candidates["email_sent"].astype(bool)]

        creds = gmail_creds_from_env()
        if not creds:
            print("No Gmail creds found in environment (GMAIL_USER / GMAIL_APP_PASSWORD). Aborting.")
            return

        sent = 0
        for idx, row in candidates.iterrows():
            to_addr = (row.get("email") or "").strip()
            if not to_addr or "@" not in to_addr:
                continue
            fields = {
                "name": (row.get("profile_name") or "there").split()[0],
                **{
                    "candidate_name": self.config.get("candidateName"),
                    "candidate_first_name": self.config.get("candidateFirstName"),
                    "candidate_email": self.config.get("candidateEmail"),
                    "candidate_bio_long": self.config.get("candidateBioFullstack") or "",
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
                df.at[idx, "email_sent"] = True
                continue

            try:
                send_one(creds=creds, to_addr=to_addr, subject=rendered_subject, body=rendered_body, from_name=self.config.get("candidateName"))
                df.at[idx, "email_sent"] = True
                sent += 1
                df.to_csv(POSTS_CSV, index=False)
                print(f"Sent email to {to_addr}")
            except Exception as e:
                print(f"Failed to send to {to_addr}: {e}")

        print(f"Email send complete. Sent: {sent}")

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
