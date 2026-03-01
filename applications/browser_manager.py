from urllib.parse import urlparse
from playwright.async_api import Playwright, Browser, BrowserContext, Page


class BrowserManager:
    def __init__(self, headless: bool = True, channel: str | None = None) -> None:
        self.headless = headless
        self.channel = channel
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._is_closed = False

    async def get_domain(self, url: str) -> str:
        parsed_url = urlparse(url)
        return parsed_url.netloc

    async def start(self, playwright: Playwright) -> None:
        launch_kwargs = dict(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        if self.channel:
            launch_kwargs["channel"] = self.channel
        self.browser = await playwright.chromium.launch(**launch_kwargs)
        self.context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        # Hide webdriver flag from JS
        await self.context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.page = await self.context.new_page()
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
