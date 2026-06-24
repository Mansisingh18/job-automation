# job-apply-bot

Automates job applications across **Naukri**, **LinkedIn**, **Indeed**, and **Shine** using Python + Playwright. Searches by keyword and location, applies to matching roles, and tracks every application in a local SQLite database to prevent duplicates.

## Features

- Searches multiple portals in one run
- Applies to jobs automatically (Naukri native apply, LinkedIn Easy Apply, Indeed Quick Apply, Shine direct apply)
- Resume picked from disk — uploaded or refreshed per portal
- Skips already-applied jobs (SQLite tracker)
- Configurable keyword/location/experience/salary filters
- Visible browser (`headless: false`) so you can handle OTPs and captchas
- All activity logged to console + `run.log`

## Setup

```bash
git clone https://github.com/Mansisingh18/job-apply-bot.git
cd job-apply-bot

pip install -r requirements.txt
playwright install chromium
```

Copy the example config and fill in your details:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:
- `resume.path` — absolute path to your PDF resume
- `credentials` — email + password for each portal you want to use
- `search.keywords`, `location`, `experience_years` — tune to your profile

## Usage

```bash
# Run all configured portals
python main.py

# Run specific portals
python main.py --portals naukri linkedin

# Check application stats
python main.py --stats
```

## How it works

| Portal | Apply method | Notes |
|--------|-------------|-------|
| Naukri | Native apply + resume refresh | Refreshes resume on profile each run |
| LinkedIn | Easy Apply only | Skips jobs requiring external redirect |
| Indeed | Quick Apply | Uploads resume if form requests it |
| Shine | Direct apply button | Opens job page in new tab |

## Config reference

```yaml
search:
  keywords: ["Senior Data Engineer", "Analytics Engineer"]
  location: "Bengaluru"
  experience_years: 5
  remote: true
  max_applications_per_run: 20   # safety cap per portal

filters:
  min_salary: 2000000            # INR annual
  exclude_keywords: ["intern", "fresher"]

browser:
  headless: false    # keep false — handles OTPs/captchas
  slow_mo: 800       # ms between actions
```

## Notes

- `config.yaml` and `applied_jobs.db` are gitignored — credentials and application history stay local
- Portal selectors may need updating if sites change their HTML — check `run.log` for failures
- Tested on Python 3.10+, Windows 11

## Tech

Python · Playwright · PyYAML · SQLite
