from urllib.parse import urlparse
from playwright.async_api import Playwright, Browser, BrowserContext, Page


class BrowserManager:
    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._is_closed = False

    async def get_domain(self, url: str) -> str:
        parsed_url = urlparse(url)
        return parsed_url.netloc

    async def start(self, playwright: Playwright) -> None:
        self.browser = await playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        # await self.add_base_cookies()
        self._is_closed = False

    async def close(self) -> None:
        if self._is_closed:
            return

        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass

        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass

        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass

        self._is_closed = True

    async def goto(self, url: str) -> None:
        if self.page and not self.page.is_closed():
            await self.add_base_cookies(url)
            await self.page.goto(url)

    async def add_base_cookies(self, url: str) -> None:
        if not self.context:
            return

        cookies = [
            {
                "name": "CookieConsent",
                "value": "true",
                "domain": await self.get_domain(url),
                "path": "/"
            }
        ]
        try:
            await self.context.add_cookies(cookies)
        except Exception:
            pass
