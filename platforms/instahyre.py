import asyncio
import re

from playwright.async_api import TimeoutError as PWTimeout

from platforms.base import JobPortal
from utils import logger, tracker

log = logger.get("instahyre")


class InstahyrePortal(JobPortal):
    name = "instahyre"
    BASE = "https://www.instahyre.com"

    async def login(self):
        await self.page.goto(f"{self.BASE}/candidate/login/", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        await self.page.wait_for_selector("input[name='email'], input[type='email']", timeout=15000)
        await self.page.fill("input[name='email'], input[type='email']", self.creds["email"])
        await self.page.fill("input[name='password'], input[type='password']", self.creds["password"])
        await self.page.click("button[type='submit'], input[type='submit']")
        await self.page.wait_for_load_state("domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        log.info("Logged in to Instahyre — URL: %s", self.page.url)

    async def search_and_apply(self):
        filters = self.cfg.get("filters", {})
        exclude = [k.lower() for k in filters.get("exclude_keywords", [])]

        for keyword in self.search_cfg["keywords"]:
            if self._over_cap():
                break
            url = f"{self.BASE}/jobs/?q={keyword.replace(' ', '+')}"
            log.info("Searching Instahyre: %s", keyword)
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await self._process_listings(exclude)

    async def _process_listings(self, exclude: list):
        cards = await self.page.query_selector_all("div.job-card, div.opportunity-card, li.job-item")
        log.info("Instahyre: found %d cards", len(cards))

        for card in cards:
            if self._over_cap():
                break
            try:
                title_el = await card.query_selector("h2, h3, a.job-title, span.job-title")
                company_el = await card.query_selector("span.company-name, a.company-name, p.company")
                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip()
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"

                if any(x in title.lower() for x in exclude):
                    continue

                link_el = await card.query_selector("a[href*='/jobs/'], a[href*='/opportunity/']")
                href = await link_el.get_attribute("href") if link_el else ""
                job_id = re.sub(r"[^a-z0-9]", "", href.lower())[-20:] or title[:20]
                job_url = f"{self.BASE}{href}" if href.startswith("/") else href

                if tracker.already_applied("instahyre", job_id):
                    log.info("Already applied: %s", title)
                    continue

                log.info("Applying: %s @ %s", title, company)
                if href:
                    page2 = await self.page.context.new_page()
                    await page2.goto(job_url, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    apply_btn = await page2.query_selector("button:has-text('Apply'), a:has-text('Apply Now')")
                    if apply_btn:
                        await apply_btn.click()
                        await asyncio.sleep(2)
                        tracker.record("instahyre", job_id, title, company, job_url)
                        self.applied += 1
                    await page2.close()

            except PWTimeout:
                log.error("Timeout on Instahyre listing")
                continue
