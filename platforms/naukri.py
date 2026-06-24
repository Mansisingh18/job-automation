import asyncio
import re
from urllib.parse import quote_plus

from playwright.async_api import Page, TimeoutError as PWTimeout

from platforms.base import JobPortal
from utils import logger, tracker

log = logger.get("naukri")


class NaukriPortal(JobPortal):
    name = "naukri"
    BASE = "https://www.naukri.com"

    async def login(self):
        await self.page.goto(f"{self.BASE}/nlogin/login")
        await self.page.fill("input[placeholder='Enter your active Email ID']", self.creds["email"])
        await self.page.fill("input[placeholder='Enter your password']", self.creds["password"])
        await self.page.click("button[type='submit']")
        await self.page.wait_for_load_state("networkidle", timeout=15000)
        log.info("Logged in to Naukri")

    async def _upload_resume(self):
        try:
            await self.page.click("a[title='Update Resume']", timeout=5000)
            async with self.page.expect_file_chooser() as fc_info:
                await self.page.click("label[for='resumeFile']")
            fc = await fc_info.value
            await fc.set_files(self.resume_path)
            await self.page.click("button:has-text('Save')")
            log.info("Resume uploaded/refreshed on Naukri profile")
        except PWTimeout:
            log.warning("Resume upload widget not found — skipping")

    async def search_and_apply(self):
        await self._upload_resume()
        filters = self.cfg.get("filters", {})
        exclude = [k.lower() for k in filters.get("exclude_keywords", [])]

        for keyword in self.search_cfg["keywords"]:
            if self._over_cap():
                break
            location = self.search_cfg["location"]
            exp = self.search_cfg["experience_years"]
            url = (
                f"{self.BASE}/{quote_plus(keyword.lower().replace(' ', '-'))}-jobs-in-"
                f"{quote_plus(location.lower())}?experience={exp}"
            )
            log.info("Searching: %s", url)
            await self.page.goto(url)
            await self.page.wait_for_load_state("networkidle")
            await self._process_listings(exclude)

    async def _process_listings(self, exclude: list):
        cards = await self.page.query_selector_all("article.jobTuple")
        if not cards:
            cards = await self.page.query_selector_all("div.srp-jobtuple-wrapper")

        for card in cards:
            if self._over_cap():
                break

            title_el = await card.query_selector("a.title, a.jobTitle")
            company_el = await card.query_selector("a.subTitle, a.companyName")
            if not title_el:
                continue

            title = (await title_el.inner_text()).strip()
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"
            job_url = await title_el.get_attribute("href") or ""
            job_id = re.search(r"-(\d+)\.htm", job_url)
            job_id = job_id.group(1) if job_id else job_url[-20:]

            if any(x in title.lower() for x in exclude):
                log.info("Skipping (excluded keyword): %s", title)
                continue
            if tracker.already_applied("naukri", job_id):
                log.info("Already applied: %s", title)
                continue

            log.info("Applying: %s @ %s", title, company)
            applied = await self._apply_to_job(job_url, job_id, title, company)
            if applied:
                tracker.record("naukri", job_id, title, company, job_url)
                self.applied += 1
                await asyncio.sleep(2)

    async def _apply_to_job(self, url: str, job_id: str, title: str, company: str) -> bool:
        try:
            page2 = await self.page.context.new_page()
            await page2.goto(url, timeout=20000)
            await page2.wait_for_load_state("networkidle")

            apply_btn = await page2.query_selector("button#apply-button, button:has-text('Apply')")
            if not apply_btn:
                log.warning("No Apply button found for: %s", title)
                await page2.close()
                return False

            await apply_btn.click()
            await asyncio.sleep(2)

            # Handle "Apply on company site" vs native Naukri apply
            chatbot = await page2.query_selector("div.botBody")
            if chatbot:
                # Naukri chatbot apply — submit with resume
                send_btn = await page2.query_selector("button.sendMsg, button:has-text('Send')")
                if send_btn:
                    await send_btn.click()
                await asyncio.sleep(1)

            confirm = await page2.query_selector("div.applied-text, span:has-text('Applied')")
            success = confirm is not None
            await page2.close()
            if success:
                log.info("Applied: %s @ %s", title, company)
            return success
        except PWTimeout:
            log.error("Timeout applying to %s", title)
            return False
