import asyncio
import re

from playwright.async_api import TimeoutError as PWTimeout, Error as PWError

from platforms.base import JobPortal
from utils import logger, tracker

log = logger.get("linkedin")


class LinkedInPortal(JobPortal):
    name = "linkedin"
    BASE = "https://www.linkedin.com"

    async def _handle_checkpoint(self):
        if any(x in self.page.url for x in ("checkpoint", "challenge", "captcha")):
            log.warning("LinkedIn security check — complete it in the browser, then press Enter")
            input("Press Enter after completing the LinkedIn verification...")
            await asyncio.sleep(2)

    async def login(self):
        await self.page.goto(f"{self.BASE}/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        await self.page.screenshot(path="linkedin_debug.png")
        log.info("LinkedIn loaded — URL: %s", self.page.url)

        if "/feed" in self.page.url or "/jobs" in self.page.url:
            log.info("Already logged in")
            return

        await self._handle_checkpoint()

        # Debug: log all input fields visible on the page
        inputs = await self.page.evaluate(
            "() => [...document.querySelectorAll('input')].map(i => ({name: i.name, id: i.id, type: i.type, placeholder: i.placeholder}))"
        )
        log.info("Inputs on page: %s", inputs)

        # Try all known LinkedIn email selectors
        email_sel = None
        for sel in ["input[name='session_key']", "input[autocomplete='username']",
                    "input[type='email']", "input[placeholder*='Email' i]", "input[placeholder*='phone' i]"]:
            try:
                await self.page.wait_for_selector(sel, timeout=5000)
                email_sel = sel
                break
            except Exception:
                continue

        if not email_sel:
            log.warning("No email input found — inputs on page logged above. Manual login needed.")
            input("Log in manually in the browser, then press Enter...")
            return

        await self.page.click(email_sel)
        await asyncio.sleep(0.3)
        await self.page.fill(email_sel, self.creds["email"])
        log.info("Filled email with selector: %s", email_sel)

        pass_sel = None
        for sel in ["input[name='session_password']", "input[type='password']"]:
            try:
                await self.page.wait_for_selector(sel, timeout=5000)
                pass_sel = sel
                break
            except Exception:
                continue

        if pass_sel:
            await self.page.click(pass_sel)
            await asyncio.sleep(0.3)
            await self.page.fill(pass_sel, self.creds["password"])
            log.info("Filled password")

        await self.page.locator("button[type='submit']").click()
        await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await self._handle_checkpoint()
        log.info("Logged in — URL: %s", self.page.url)

    async def _safe_goto(self, url: str):
        """Navigate and handle checkpoint redirects gracefully."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except PWError as e:
            if "checkpoint" in str(e) or "challenge" in str(e):
                # Wait for checkpoint page to fully load then pause for user
                await self.page.wait_for_load_state("domcontentloaded")
            else:
                raise
        await asyncio.sleep(2)
        await self._handle_checkpoint()

    async def search_and_apply(self):
        filters = self.cfg.get("filters", {})
        exclude = [k.lower() for k in filters.get("exclude_keywords", [])]
        exp = self.search_cfg["experience_years"]
        location = self.search_cfg["location"]
        remote = self.search_cfg.get("remote", False)

        exp_level = "4" if exp >= 5 else "3"  # director / mid-senior

        for keyword in self.search_cfg["keywords"]:
            if self._over_cap():
                break

            params = f"keywords={keyword}&f_AL=true&f_E={exp_level}&sortBy=DD"
            if location:
                params += f"&location={location}"
            if remote:
                params += "&f_WT=2"

            url = f"{self.BASE}/jobs/search/?{params}"
            log.info("Searching LinkedIn: %s", keyword)
            await self._safe_goto(url)
            await self._process_listings(exclude)

    async def _process_listings(self, exclude: list):
        for _ in range(3):
            await self.page.keyboard.press("End")
            await asyncio.sleep(1)

        cards = await self.page.query_selector_all("li.jobs-search-results__list-item")
        log.info("Found %d job cards", len(cards))

        for card in cards:
            if self._over_cap():
                break

            try:
                await card.click()
                await asyncio.sleep(1.5)

                # Check for checkpoint mid-browsing
                await self._handle_checkpoint()

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

                easy_apply_btn = await self.page.query_selector(
                    "button.jobs-apply-button span:has-text('Easy Apply')"
                )
                if not easy_apply_btn:
                    log.info("No Easy Apply: %s — skipping", title)
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
            except PWError as e:
                if "checkpoint" in str(e) or "challenge" in str(e):
                    await self._handle_checkpoint()
                else:
                    log.error("Error on listing: %s", e)
                continue

    async def _complete_easy_apply(self) -> bool:
        try:
            for step in range(10):
                await asyncio.sleep(1)

                upload_btn = await self.page.query_selector("label[for*='resume']")
                if upload_btn:
                    async with self.page.expect_file_chooser() as fc_info:
                        await upload_btn.click()
                    fc = await fc_info.value
                    await fc.set_files(self.resume_path)

                submit_btn = await self.page.query_selector("button[aria-label='Submit application']")
                if submit_btn:
                    await submit_btn.click()
                    await asyncio.sleep(2)
                    return True

                next_btn = await self.page.query_selector(
                    "button[aria-label='Continue to next step'], button[aria-label='Review your application']"
                )
                if next_btn:
                    await next_btn.click()
                else:
                    break

            return False
        except PWTimeout:
            discard = await self.page.query_selector("button[aria-label='Dismiss']")
            if discard:
                await discard.click()
            return False
