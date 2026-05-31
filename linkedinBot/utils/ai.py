import google.genai as genai
from google.genai import types
import fitz
import re
import os

# LinkedIn connection invite note hard limit
INVITE_NOTE_MAX = 300

# Defaults — every value here is overridable from config.yaml / the UI.
DEFAULT_RESUME_DRIVE_LINK = "https://drive.google.com/file/d/1VQh9qPqK4yIw4ebxQ4KjKaKpZo_ajujz/view?usp=sharing"

DEFAULT_CANDIDATE_NAME = "Mohnish Sawlani"
DEFAULT_CANDIDATE_FIRST_NAME = "Mohnish"
DEFAULT_CANDIDATE_EMAIL = "sawlanimohnish@gmail.com"
DEFAULT_CANDIDATE_BIO_FULLSTACK = (
    "Full Stack Dev (4+ yrs, React/Node/Python)"
)
DEFAULT_CANDIDATE_BIO_FRONTEND = (
    "Frontend Dev (4+ yrs, React/Next.js/UI/UX)"
)

# Recruiter / hirer invite templates. Placeholders supported:
#   {name} {job_title} {company} {resume_link} {candidate_first_name} {candidate_bio}
DEFAULT_INVITE_NOTE_TEMPLATE = (
    "Hi {name}, I'm {candidate_first_name} — {candidate_bio}. "
    "Saw the {job_title} role; strong fit, would love a referral. "
    "Resume: {resume_link}"
)
DEFAULT_INVITE_NOTE_TEMPLATE_FRONTEND = DEFAULT_INVITE_NOTE_TEMPLATE  # same skeleton; bio differs at render time
DEFAULT_INVITE_NOTE_TEMPLATE_HIRER = (
    "Hi {name}, I'm {candidate_first_name} — {candidate_bio}. "
    "Saw you posted the {job_title} role at {company}; strong fit. "
    "Resume: {resume_link}"
)
DEFAULT_INVITE_NOTE_TEMPLATE_HIRER_FRONTEND = DEFAULT_INVITE_NOTE_TEMPLATE_HIRER

# Email composer defaults (used in Stage 4). Placeholders match the invite templates.
DEFAULT_EMAIL_SUBJECT_TEMPLATE = (
    "Referral request: {job_title} at {company}"
)
DEFAULT_EMAIL_BODY_TEMPLATE = """Hi {name},

I came across the {job_title} opening at {company} and felt my background is a strong match.

Quick context — I'm {candidate_first_name}, a {candidate_bio_long}. Resume: {resume_link}

If the role is still open, I'd be grateful for a referral or any pointer toward the hiring manager.

Thanks!
{candidate_name}
{candidate_email}
"""

DEFAULT_AI_SYSTEM_PROMPT_TEMPLATE = """You are an AI evaluating {candidate_name}'s fit for a software engineering role.

Candidate profile:
{candidate_profile_block}

### Decision Criteria
Recommend **YES** if:
- The role is a software engineering / web / frontend / backend / full-stack / SaaS / cloud / automation role.
- Candidate meets at least 60% of the core technical requirements (or has equivalent transferable tech).
- Experience gap is 3 years or less (i.e. role asks for <= 7 yrs).
- Role is NOT a pure data-science / ML-research / mobile-only (iOS/Android native) / embedded / DevOps-SRE-only / QA-only role unless the candidate has matching exposure.

Recommend **NO** if:
- Role demands deep niche tech not in the profile (Rust, Go primary, Solidity, Salesforce, SAP, .NET, Java backend primary, Android/iOS native, etc.) and lists them as required.
- Senior+ role demanding 8+ yrs experience.
- Pure non-engineering role (PM, BA, sales, support, marketing).

### Response Format (strict)
First line: `Match Status: YES` or `Match Status: NO`.

If YES, next list 7 short (2–4 word) keywords that either don't appear in the resume verbatim or should be reworded to mirror the JD's terminology. At least 3 must be technical (frameworks, tools, services). Use bullet lines starting with `- `.

Then output `Referral Message:` on its own line followed by a longer (multi-line) friendly referral request — used as a follow-up DM after connection accepts. Format:

Hi {{Name}},
Thanks for connecting!

I'm interested in the **{{job_title}}** role at **{{company}}** and noticed you're a recruiter / hiring there.
I'd really appreciate it if you could refer me for this role.

Job link: {{job_link or job id}}

Quick context — {candidate_pitch}

Resume: {resume_link}

Thanks so much for your support!
{candidate_name}
{candidate_email}

If NO, return ONLY the line `Match Status: NO` and nothing else.
"""

# Default candidate profile block used to fill the AI prompt — also configurable.
DEFAULT_CANDIDATE_PROFILE_BLOCK = """- 4+ years building scalable SaaS, e-commerce, real-time apps, cloud-native products.
- Frontend: React.js, Next.js, JavaScript, TypeScript, Redux, Tailwind CSS, Material UI.
- Backend: Node.js, Express.js, Python, FastAPI, REST APIs, GraphQL, WebSockets, SSE.
- DB: MongoDB, DynamoDB, PostgreSQL, Supabase.
- Cloud/DevOps: AWS Lambda, EC2, S3, SQS, GitHub Actions, Azure DevOps, CI/CD, Docker.
- Automation: Playwright, Chromium, ETL pipelines.
- Commerce: Shopify Plus, Liquid, Storefront API, Admin GraphQL API.
- Currently SDE II / Frontend Lead at Wednesday Solutions."""

DEFAULT_CANDIDATE_PITCH = (
    "I'm a Full Stack Developer with 4+ years of experience building scalable "
    "SaaS platforms, e-commerce systems, and real-time apps using React.js, "
    "Node.js, Python, GraphQL, and AWS. Most recently SDE II / Frontend Lead "
    "at Wednesday Solutions."
)


# Title / JD keywords used to route a job to the frontend resume.
_FRONTEND_TITLE_HINTS = (
    "frontend", "front-end", "front end", "ui developer", "ui/ux",
    "ux developer", "ux engineer", "react developer", "next.js developer",
    "webflow developer", "ui engineer",
)
_FULLSTACK_TITLE_HINTS = (
    "full stack", "fullstack", "full-stack", "backend", "back-end",
    "node developer", "node.js developer", "python developer",
)
_FRONTEND_JD_HINTS = (
    "figma", "design system", "framer motion", "responsive design",
    "ui/ux", "ux design", "animation system", "tailwind", "webflow",
    "pixel-perfect", "css", "storybook",
)
_BACKEND_JD_HINTS = (
    "rest api", "microservice", "node.js server", "database design",
    "fastapi", "graphql server", "kafka", "sqs", "lambda", "redis",
    "postgres", "schema design", "api development",
)


def classify_role(job_title, job_description=""):
    """Decide whether this job should be matched with Mohnish's Frontend or
    Full Stack resume. Returns "frontend" or "fullstack".
    """
    title = (job_title or "").lower()
    desc = (job_description or "").lower()

    title_fe = any(h in title for h in _FRONTEND_TITLE_HINTS)
    title_fs = any(h in title for h in _FULLSTACK_TITLE_HINTS)

    # Strong signal from title.
    if title_fe and not title_fs:
        return "frontend"
    if title_fs:
        return "fullstack"

    # Ambiguous title — count keyword hits in the JD.
    fe_score = sum(1 for h in _FRONTEND_JD_HINTS if h in desc)
    be_score = sum(1 for h in _BACKEND_JD_HINTS if h in desc)
    if fe_score >= 3 and fe_score > be_score + 1:
        return "frontend"
    return "fullstack"


class JobMatchEvaluator:
    def __init__(
        self,
        resume_path=None,
        resume_paths=None,
        candidate_context=None,
        system_prompt_template=None,
    ):
        """`resume_paths` is a dict mapping variant -> file path, e.g.
        {"fullstack": "/path/to/fullstack.pdf", "frontend": "/path/to/frontend.pdf"}.
        `candidate_context` is a dict used to fill the system prompt placeholders
        (candidate_name, candidate_email, candidate_profile_block, candidate_pitch,
        resume_link). `system_prompt_template` overrides the default template.
        """
        self.gemini_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
        self.resume_paths = dict(resume_paths or {})
        if resume_path and "fullstack" not in self.resume_paths:
            self.resume_paths["fullstack"] = resume_path
        self._resume_cache = {}
        self.candidate_context = candidate_context or {}
        self.system_prompt_template = system_prompt_template or DEFAULT_AI_SYSTEM_PROMPT_TEMPLATE

    def _resolve_resume_path(self, variant):
        return self.resume_paths.get(variant) or self.resume_paths.get("fullstack")

    def extract_resume_content(self, variant="fullstack"):
        if variant in self._resume_cache:
            return self._resume_cache[variant]
        path = self._resolve_resume_path(variant)
        if not path:
            self._resume_cache[variant] = ""
            return ""
        try:
            document = fitz.open(path)
            content = [page.get_text() for page in document]
            self._resume_cache[variant] = "\n".join(content)
        except Exception as e:
            print(f"Could not extract text from resume PDF ({variant}): {str(e)}")
            self._resume_cache[variant] = ""
        return self._resume_cache[variant]

    def get_gemini_insights(self, prompt, system_prompt):
        models = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        for model in models:
            try:
                print(f"Using model: {model}")
                response = self.gemini_client.models.generate_content(
                    model=model,
                    config=types.GenerateContentConfig(system_instruction=system_prompt),
                    contents=prompt)
                return response.text
            except Exception as e:
                error_message = str(e).lower()
                if "rate limit" in error_message or "exceeded" in error_message or "quota" in error_message:
                    print(f"Rate limit reached for {model}, switching to next model...")
                    continue
                else:
                    raise e

        return "Error: All Gemini models reached rate limit. Try again later."

    def check_job_match(self, job_description, job_title=""):
        """Evaluate whether Mohnish is a fit for the supplied job.

        Auto-routes to the Frontend resume when the role is UI/UX/Frontend
        focused (via `classify_role`), otherwise uses the Full Stack resume.

        Returns (status, skills, referral_message, variant).
        """
        variant = classify_role(job_title, job_description)
        resume_text = self.extract_resume_content(variant)

        ctx = {
            "candidate_name": self.candidate_context.get("candidate_name", DEFAULT_CANDIDATE_NAME),
            "candidate_email": self.candidate_context.get("candidate_email", DEFAULT_CANDIDATE_EMAIL),
            "candidate_profile_block": self.candidate_context.get(
                "candidate_profile_block", DEFAULT_CANDIDATE_PROFILE_BLOCK
            ),
            "candidate_pitch": self.candidate_context.get(
                "candidate_pitch", DEFAULT_CANDIDATE_PITCH
            ),
            "resume_link": (
                self.candidate_context.get("resume_link_frontend") if variant == "frontend"
                else self.candidate_context.get("resume_link_fullstack")
            ) or self.candidate_context.get("resume_link", DEFAULT_RESUME_DRIVE_LINK),
        }
        try:
            system_prompt = self.system_prompt_template.format(**ctx)
        except (KeyError, IndexError):
            # Template references an unknown placeholder — fall back to raw template.
            system_prompt = self.system_prompt_template

        prompt = (
            f"Resume ({variant}):\n{resume_text}\n\n"
            f"Job Title: {job_title}\n"
            f"Job Description:\n{job_description}\n\n"
            f"Evaluate the job fit based on the criteria and format specified above."
        )

        response = self.get_gemini_insights(prompt, system_prompt)

        if not response:
            return "No", [], "", variant

        lines = response.split('\n')

        match_status_line = next((line for line in lines if "Match Status:" in line), "Match Status: NO")
        match_status = "YES" if "YES" in match_status_line.upper() else "NO"
        if match_status == "NO":
            return "No", [], "", variant

        # Skills as bullet lines BEFORE "Referral Message:"
        referral_index = next((i for i, line in enumerate(lines) if "Referral Message:" in line), None)
        skill_section = lines[:referral_index] if referral_index is not None else lines
        skill_lines = [line.strip() for line in skill_section if re.match(r'^\s*[-*]\s+', line)]
        missing_skills = [re.sub(r'^\s*[-*]\s+', '', s) for s in skill_lines if s]

        referral_message = "\n".join(lines[referral_index + 1:]).strip() if referral_index is not None else ""

        return match_status, missing_skills, referral_message, variant


def build_invite_note(
    template,
    name,
    job_title,
    company,
    job_link,
    resume_link=DEFAULT_RESUME_DRIVE_LINK,
    candidate_first_name=DEFAULT_CANDIDATE_FIRST_NAME,
    candidate_bio=DEFAULT_CANDIDATE_BIO_FULLSTACK,
):
    """Render the connection-invite note from a template and truncate to LinkedIn's
    300-char limit. Every value is overridable so the bot can be used for any
    candidate.
    """
    name = (name or "there").split()[0]
    job_title = (job_title or "this role").strip()
    company = (company or "your company").strip()
    job_link = (job_link or "").strip()
    resume_link = (resume_link or DEFAULT_RESUME_DRIVE_LINK).strip()
    candidate_first_name = (candidate_first_name or "I").strip()
    candidate_bio = (candidate_bio or "").strip()

    fields = dict(
        name=name,
        job_title=job_title,
        company=company,
        job_link=job_link,
        resume_link=resume_link,
        candidate_first_name=candidate_first_name,
        candidate_bio=candidate_bio,
    )

    note = template.format(**fields)
    if len(note) <= INVITE_NOTE_MAX:
        return note

    # Truncate by shortening job_title progressively.
    overflow = len(note) - INVITE_NOTE_MAX
    if len(job_title) > overflow + 3:
        fields["job_title"] = job_title[: max(8, len(job_title) - overflow - 3)].rstrip() + "..."
        note = template.format(**fields)
    if len(note) > INVITE_NOTE_MAX:
        note = note[: INVITE_NOTE_MAX - 1].rstrip() + "…"
    return note
