RESUME_PATH = "/path/to/your/resume.pdf"

SEARCH = {
    "keywords": [
        "Senior Data Engineer",
        "Data Engineer",
        "AWS Data Engineer",
        "Analytics Engineer",
        "Data Platform Engineer",
        "Big Data Engineer",
    ],
    "location": "Bengaluru",
    "experience_years": 5,
    "job_type": "full_time",
    "remote": True,
    "max_applications_per_run": 20,
}

FILTERS = {
    "min_salary": 2500000,
    "exclude_keywords": ["intern", "fresher", "trainee", "junior", "entry level", "0-2 years"],
}

CREDENTIALS = {
    "naukri":   {"email": "", "password": ""},
    "linkedin": {"email": "", "password": ""},
    "indeed":   {"email": "", "password": ""},
    "shine":    {"email": "", "password": ""},
}

BROWSER = {
    "headless": False,
    "slow_mo": 800,
    "timeout": 30000,
}
