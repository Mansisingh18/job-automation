import asyncio
import re
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PWTimeout

from platforms.base import JobPortal
from utils import logger, tracker

log = logger.get("indeed")


class IndeedPortal(JobPortal):
    name = "indeed"
    BASE = "https://in.indeed.com"

    async def login(self):
        await self.page.goto(f"{self.BASE}/account/login")
        await self.page.fill("input#emailOrUsername", self.creds["email"])
        await self.page.click("button[type='submit']")
        await asyncio.sleep(1)
        try:
            await self.page.fill("input#password", self.creds["password"], timeout=5000)
            await self.page.click("button[type='submit']")
        except PWTimeout:
            pass  # password may appear on same page
        await self.page.wait_for_load_state("networkidle", timeout=20000)

        if "challenge" in self.page.url or "security" in self.page.url:
            log.warning("Indeed verification — complete manually, then press Enter")
            input("Press Enter after completing verification...")
        log.info("Logged in to Indeed")

    async def search_and_apply(self):
        filters = self.cfg.get("filters", {})
        exclude = [k.lower() for k in filters.get("exclude_keywords", [])]
        location = self.search_cfg["location"]
        remote = self.search_cfg.get("remote", False)

        for keyword in self.search_cfg["keywords"]:
            if self._over_cap():
                break

            q = quote_plus(keyword)
            l = quote_plus(location)
            params = f"q={q}&l={l}&fromage=7&sort=date"  # last 7 days, sorted by date
            if remote:
                params += "&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11"

            url = f"{self.BASE}/jobs?{params}"
            log.info("Searching Indeed: %s", keyword)
            await self.page.goto(url)
            await self.page.wait_for_load_state("networkidle")
            await self._process_listings(exclude)

    async def _process_listings(self, exclude: list):
        cards = await self.page.query_selector_all("div.job_seen_beacon, div.tapItem")

        for card in cards:
            if self._over_cap():
                break

            try:
                title_el = await card.query_selector("h2.jobTitle span[title], h2.jobTitle a")
                company_el = await card.query_selector("span.companyName, a.companyName")
                link_el = await card.query_selector("h2.jobTitle a")
                if not title_el or not link_el:
                    continue

                title = (await title_el.get_attribute("title") or await title_el.inner_text()).strip()
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                href = await link_el.get_attribute("href") or ""
                job_id = re.search(r"jk=([a-f0-9]+)", href)
                job_id = job_id.group(1) if job_id else href[-15:]
                job_url = f"{self.BASE}{href}" if href.startswith("/") else href

                if any(x in title.lower() for x in exclude):
                    log.info("Skipping (excluded): %s", title)
                    continue
                if tracker.already_applied("indeed", job_id):
                    log.info("Already applied: %s", title)
                    continue

                await card.click()
                await asyncio.sleep(1.5)

                apply_btn = await self.page.query_selector(
                    "button#indeedApplyButton, span:has-text('Easily apply')"
                )
                if not apply_btn:
                    log.info("No Quick Apply for: %s — skipping", title)
                    continue

                log.info("Applying: %s @ %s", title, company)
                await apply_btn.click()
                success = await self._complete_apply(title)
                if success:
                    tracker.record("indeed", job_id, title, company, job_url)
                    self.applied += 1
                    await asyncio.sleep(2)

            except PWTimeout:
                log.error("Timeout on Indeed listing")
                continue

    async def _complete_apply(self, title: str) -> bool:
        try:
            # Switch to application iframe if present
            frame = self.page.frame("indeedapply-modal-preload-iframe")
            ctx = frame if frame else self.page

            for _ in range(8):
                await asyncio.sleep(1.5)

                # Resume upload
                file_input = await ctx.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(self.resume_path)

                # Continue / Next
                next_btn = await ctx.query_selector(
                    "button[data-testid='IndeedApplyButton'], "
                    "button:has-text('Continue'), button:has-text('Next')"
                )
                if next_btn:
                    text = (await next_btn.inner_text()).strip().lower()
                    if "submit" in text:
                        await next_btn.click()
                        log.info("Submitted Indeed application: %s", title)
                        await asyncio.sleep(2)
                        return True
                    await next_btn.click()

            return False
        except Exception as e:
            log.error("Indeed apply error: %s", e)
            return False
