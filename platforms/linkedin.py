import asyncio
import re

from playwright.async_api import TimeoutError as PWTimeout

from platforms.base import JobPortal
from utils import logger, tracker

log = logger.get("linkedin")


class LinkedInPortal(JobPortal):
    name = "linkedin"
    BASE = "https://www.linkedin.com"

    async def login(self):
        await self.page.goto(f"{self.BASE}/login", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        log.info("LinkedIn page loaded — URL: %s", self.page.url)

        # Take screenshot to see what LinkedIn is showing
        await self.page.screenshot(path="linkedin_debug.png")
        log.info("Screenshot saved to linkedin_debug.png — check it if login fails")

        # If already logged in, skip
        if "/feed" in self.page.url or "/jobs" in self.page.url:
            log.info("Already logged in to LinkedIn")
            return

        # Handle security/captcha wall before the login form
        if "checkpoint" in self.page.url or "challenge" in self.page.url or "captcha" in self.page.url:
            log.warning("LinkedIn security check before login — complete it in the browser, then press Enter")
            input("Press Enter after completing the check...")

        # Wait up to 60s for the username field (CAPTCHA might need manual solve)
        try:
            await self.page.wait_for_selector("input#username", timeout=60000)
        except Exception:
            log.warning("input#username not found — pausing for manual login. Press Enter when logged in.")
            input("Log in manually in the browser, then press Enter...")
            return

        await asyncio.sleep(1)
        await self.page.fill("input#username", self.creds["email"])
        await asyncio.sleep(0.5)
        await self.page.fill("input#password", self.creds["password"])
        await asyncio.sleep(0.5)
        await self.page.click("button[type='submit']")
        await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        if "checkpoint" in self.page.url or "challenge" in self.page.url:
            log.warning("LinkedIn 2FA/checkpoint — complete it in the browser, then press Enter")
            input("Press Enter after completing the check...")
        log.info("Logged in to LinkedIn — URL: %s", self.page.url)

    async def search_and_apply(self):
        filters = self.cfg.get("filters", {})
        exclude = [k.lower() for k in filters.get("exclude_keywords", [])]
        exp = self.search_cfg["experience_years"]
        location = self.search_cfg["location"]
        remote = self.search_cfg.get("remote", False)

        # LinkedIn experience level mapping
        exp_level = "3"  # mid-senior
        if exp <= 1:
            exp_level = "1"  # internship/entry
        elif exp <= 3:
            exp_level = "2"  # entry level

        for keyword in self.search_cfg["keywords"]:
            if self._over_cap():
                break

            params = (
                f"keywords={keyword}&location={location}"
                f"&f_AL=true"          # Easy Apply only
                f"&f_E={exp_level}"
                f"&sortBy=DD"          # date posted
            )
            if remote:
                params += "&f_WT=2"   # remote

            url = f"{self.BASE}/jobs/search/?{params}"
            log.info("Searching LinkedIn: %s", keyword)
            await self.page.goto(url)
            await self.page.wait_for_load_state("networkidle")
            await self._process_listings(exclude)

    async def _process_listings(self, exclude: list):
        # Scroll to load more jobs
        for _ in range(3):
            await self.page.keyboard.press("End")
            await asyncio.sleep(1)

        cards = await self.page.query_selector_all("li.jobs-search-results__list-item")

        for card in cards:
            if self._over_cap():
                break

            try:
                await card.click()
                await asyncio.sleep(1.5)

                title_el = await self.page.query_selector("h1.job-details-jobs-unified-top-card__job-title")
                company_el = await self.page.query_selector("div.job-details-jobs-unified-top-card__company-name")
                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip()
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                job_id = re.search(r"/jobs/view/(\d+)/", self.page.url)
                job_id = job_id.group(1) if job_id else self.page.url[-15:]

                if any(x in title.lower() for x in exclude):
                    log.info("Skipping (excluded): %s", title)
                    continue
                if tracker.already_applied("linkedin", job_id):
                    log.info("Already applied: %s", title)
                    continue

                easy_apply_btn = await self.page.query_selector("button.jobs-apply-button span:has-text('Easy Apply')")
                if not easy_apply_btn:
                    log.info("No Easy Apply for: %s — skipping", title)
                    continue

                log.info("Applying (Easy Apply): %s @ %s", title, company)
                await easy_apply_btn.click()
                success = await self._complete_easy_apply()
                if success:
                    tracker.record("linkedin", job_id, title, company, self.page.url)
                    self.applied += 1
                    await asyncio.sleep(2)

            except PWTimeout:
                log.error("Timeout on LinkedIn listing")
                continue

    async def _complete_easy_apply(self) -> bool:
        """Step through Easy Apply modal, filling in basic fields and submitting."""
        try:
            for step in range(10):  # max 10 pages in the modal
                await asyncio.sleep(1)

                # Phone field
                phone_field = await self.page.query_selector("input[id*='phoneNumber']")
                if phone_field and not await phone_field.input_value():
                    await phone_field.fill("")   # user can pre-fill or leave blank

                # Resume — LinkedIn stores last-used resume; no re-upload needed unless prompted
                upload_btn = await self.page.query_selector("label[for*='resume']")
                if upload_btn:
                    async with self.page.expect_file_chooser() as fc_info:
                        await upload_btn.click()
                    fc = await fc_info.value
                    await fc.set_files(self.resume_path)

                # Check for "Submit application" button (final step)
                submit_btn = await self.page.query_selector("button[aria-label='Submit application']")
                if submit_btn:
                    await submit_btn.click()
                    await asyncio.sleep(2)
                    return True

                # Next / Review button
                next_btn = await self.page.query_selector(
                    "button[aria-label='Continue to next step'], button[aria-label='Review your application']"
                )
                if next_btn:
                    await next_btn.click()
                else:
                    break

            return False
        except PWTimeout:
            # Close modal if still open
            discard = await self.page.query_selector("button[aria-label='Dismiss']")
            if discard:
                await discard.click()
            return False
