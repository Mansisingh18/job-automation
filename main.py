"""
Job Apply Bot — entry point

Usage:
    python main.py                         # run all portals
    python main.py --portals naukri        # specific portals
    python main.py --portals naukri linkedin
    python main.py --stats                 # show application summary
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml
from playwright.async_api import async_playwright

from platforms import PORTALS
from utils import logger, tracker

log = logger.get("main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_config(cfg: dict):
    resume = cfg["resume"]["path"]
    if not Path(resume).exists():
        sys.exit(f"Resume not found at: {resume}\nUpdate config.yaml → resume.path")
    for portal, creds in cfg["credentials"].items():
        if not creds.get("email"):
            log.warning("No credentials for %s — it will be skipped", portal)


async def run_portal(portal_name: str, cfg: dict):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=cfg["browser"]["headless"],
            slow_mo=cfg["browser"]["slow_mo"],
            args=["--start-maximized"],
        )
        context = await browser.new_context(
            viewport=None,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        PortalClass = PORTALS[portal_name]
        portal = PortalClass(page, cfg)

        try:
            log.info("=== Starting %s ===", portal_name.upper())
            await portal.login()
            await portal.search_and_apply()
            log.info("=== %s done — %d applications this run ===", portal_name.upper(), portal.applied)
        except Exception as e:
            log.error("%s failed: %s", portal_name, e, exc_info=True)
        finally:
            await browser.close()


async def main():
    parser = argparse.ArgumentParser(description="Job Apply Bot")
    parser.add_argument("--portals", nargs="+", choices=list(PORTALS), help="Portals to run")
    parser.add_argument("--stats", action="store_true", help="Show application stats and exit")
    args = parser.parse_args()

    if args.stats:
        totals = tracker.summary()
        if not totals:
            print("No applications tracked yet.")
        else:
            print("\nApplications by portal:")
            for portal, count in sorted(totals.items()):
                print(f"  {portal:12s}: {count}")
            print(f"  {'TOTAL':12s}: {sum(totals.values())}")
        return

    cfg = load_config()
    validate_config(cfg)

    portals_to_run = args.portals or list(PORTALS.keys())
    # Only run portals that have credentials configured
    portals_to_run = [p for p in portals_to_run if cfg["credentials"].get(p, {}).get("email")]

    if not portals_to_run:
        sys.exit("No portals configured — fill in credentials in config.yaml")

    log.info("Running portals: %s", ", ".join(portals_to_run))

    for portal_name in portals_to_run:
        await run_portal(portal_name, cfg)

    log.info("All done. Run with --stats to see totals.")


if __name__ == "__main__":
    asyncio.run(main())
