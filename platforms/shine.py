import asyncio
import re
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PWTimeout

from platforms.base import JobPortal
from utils import logger, tracker

log = logger.get("shine")


class ShinePortal(JobPortal):
    name = "shine"
    BASE = "https://www.shine.com"

    async def login(self):
        await self.page.goto(f"{self.BASE}/login/")
        await asyncio.sleep(1)
        await self.page.fill("input[name='email'], input[type='email']", self.creds["email"])
        await self.page.fill("input[name='password'], input[type='password']", self.creds["password"])
        await self.page.click("button[type='submit'], input[type='submit']")
        await self.page.wait_for_load_state("networkidle", timeout=15000)
        log.info("Logged in to Shine")

    async def search_and_apply(self):
        filters = self.cfg.get("filters", {})
        exclude = [k.lower() for k in filters.get("exclude_keywords", [])]
        location = self.search_cfg["location"]
        exp = self.search_cfg["experience_years"]

        for keyword in self.search_cfg["keywords"]:
            if self._over_cap():
                break

            q = quote_plus(keyword)
            l = quote_plus(location)
            url = f"{self.BASE}/job-search/{q}-jobs-in-{l}/?experience={exp}"
            log.info("Searching Shine: %s", keyword)
            await self.page.goto(url)
            await self.page.wait_for_load_state("networkidle")
            await self._process_listings(exclude)

    async def _process_listings(self, exclude: list):
        cards = await self.page.query_selector_all("div.job-card, li.job-listing-item")

        for card in cards:
            if self._over_cap():
                break

            try:
                title_el = await card.query_selector("a.job-title, h2 a")
                company_el = await card.query_selector("span.company-name, a.company-name")
                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip()
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                href = await title_el.get_attribute("href") or ""
                job_id = re.sub(r"[^a-z0-9]", "", href.lower())[-20:]
                job_url = f"{self.BASE}{href}" if href.startswith("/") else href

                if any(x in title.lower() for x in exclude):
                    log.info("Skipping (excluded): %s", title)
                    continue
                if tracker.already_applied("shine", job_id):
                    log.info("Already applied: %s", title)
                    continue

                log.info("Applying: %s @ %s", title, company)
                applied = await self._apply_to_job(job_url, job_id, title, company)
                if applied:
                    tracker.record("shine", job_id, title, company, job_url)
                    self.applied += 1
                    await asyncio.sleep(2)

            except PWTimeout:
                log.error("Timeout on Shine listing")
                continue

    async def _apply_to_job(self, url: str, job_id: str, title: str, company: str) -> bool:
        try:
            page2 = await self.page.context.new_page()
            await page2.goto(url, timeout=20000)
            await page2.wait_for_load_state("networkidle")

            apply_btn = await page2.query_selector(
                "button:has-text('Apply'), a:has-text('Apply Now')"
            )
            if not apply_btn:
                await page2.close()
                return False

            await apply_btn.click()
            await asyncio.sleep(2)

            # Upload resume if prompted
            file_input = await page2.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(self.resume_path)
                submit = await page2.query_selector("button[type='submit']")
                if submit:
                    await submit.click()
                await asyncio.sleep(2)

            success_el = await page2.query_selector(
                "div:has-text('Application submitted'), span:has-text('Applied')"
            )
            await page2.close()
            return success_el is not None
        except PWTimeout:
            log.error("Timeout applying to Shine job: %s", title)
            return False
