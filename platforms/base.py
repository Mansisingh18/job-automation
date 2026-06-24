from abc import ABC, abstractmethod
from playwright.async_api import Page


class JobPortal(ABC):
    name: str = ""

    def __init__(self, page: Page, config: dict):
        self.page = page
        self.cfg = config
        self.creds = config["credentials"].get(self.name, {})
        self.search_cfg = config["search"]
        self.resume_path = config["resume"]["path"]
        self.applied = 0
        self.cap = config["search"]["max_applications_per_run"]

    @abstractmethod
    async def login(self): ...

    @abstractmethod
    async def search_and_apply(self): ...

    def _over_cap(self) -> bool:
        return self.applied >= self.cap
