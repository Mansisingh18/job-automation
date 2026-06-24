import asyncio
import re
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PWTimeout

from platforms.base import JobPortal
from utils import logger, tracker

log = logger.get("wellfound")


class WellfoundPortal(JobPortal):
    name = "wellfound"
    BASE = "https://wellfound.com"

    async def login(self):
        await self.page.goto(f"{self.BASE}/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Check if already logged in
        if "/jobs" in self.page.url or "/talent" in self.page.url:
            log.info("Already logged in to Wellfound")
            return

        await self.page.wait_for_selector("input[name='user[email]'], input[type='email']", timeout=15000)
        await self.page.fill("input[name='user[email]'], input[type='email']", self.creds["email"])
        await self.page.fill("input[name='user[password]'], input[type='password']", self.creds["password"])
        await self.page.click("input[type='submit'], button[type='submit']")
        await self.page.wait_for_load_state("domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        log.info("Logged in to Wellfound — URL: %s", self.page.url)

    async def search_and_apply(self):
        filters = self.cfg.get("filters", {})
        exclude = [k.lower() for k in filters.get("exclude_keywords", [])]
        remote = self.search_cfg.get("remote", False)

        for keyword in self.search_cfg["keywords"]:
            if self._over_cap():
                break
            q = quote_plus(keyword)
            url = f"{self.BASE}/jobs?q={q}"
            if remote:
                url += "&remote=true"
            log.info("Searching Wellfound: %s", keyword)
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await self._process_listings(exclude)

    async def _process_listings(self, exclude: list):
        # Scroll to load more
        for _ in range(2):
            await self.page.keyboard.press("End")
            await asyncio.sleep(1)

        cards = await self.page.query_selector_all(
            "div[data-test='StartupResult'], div.styles_component__listings__item, div.job-listing"
        )
        log.info("Wellfound: found %d cards", len(cards))

        for card in cards:
            if self._over_cap():
                break
            try:
                title_el = await card.query_selector("a[data-test='job-link'], a.job-title, h2 a")
                company_el = await card.query_selector("a[data-test='company-link'], span.company-name")
                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip()
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                href = await title_el.get_attribute("href") or ""
                job_id = re.sub(r"[^a-z0-9]", "", href.lower())[-20:] or title[:20]
                job_url = f"{self.BASE}{href}" if href.startswith("/") else href

                if any(x in title.lower() for x in exclude):
                    continue
                if tracker.already_applied("wellfound", job_id):
                    log.info("Already applied: %s", title)
                    continue

                log.info("Applying: %s @ %s", title, company)
                page2 = await self.page.context.new_page()
                await page2.goto(job_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)

                apply_btn = await page2.query_selector(
                    "button:has-text('Apply'), a:has-text('Apply'), button[data-test='apply-button']"
                )
                if apply_btn:
                    await apply_btn.click()
                    await asyncio.sleep(3)
                    tracker.record("wellfound", job_id, title, company, job_url)
                    self.applied += 1
                await page2.close()

            except PWTimeout:
                log.error("Timeout on Wellfound listing")
                continue
