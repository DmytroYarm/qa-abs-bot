import asyncio
import os
import re
import time
from typing import Tuple, Any
from playwright.async_api import async_playwright
from ..browser_manager import BrowserManager
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
import json

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
MAX_CACHE_SIZE = int(os.environ.get('MAX_CACHE_SIZE', 100000))

redis_client = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)


class LanguageScraper:
    def __init__(self, page):
        self.page = page
        self.lang_to_url = {}

    async def collect_languages(self, max_wait_time=150) -> Tuple[dict[str, str], int]:
        try:
            if self.page.is_closed():
                return {}, 0

            active_lang_element = self.page.locator('[data-testid="langsblock"] [data-active="true"]')
            active_lang = await active_lang_element.get_attribute("aria-label")

            self.lang_to_url[active_lang] = self.page.url

            available_langs = await self.page.locator('[data-testid="langsblock"] *[data-active="false"]').all()
            expected_count = len(available_langs) + 1

            start_time = time.time()
            click_attempts = 0

            while len(self.lang_to_url) < expected_count:
                if time.time() - start_time > max_wait_time:
                    print(f"TIMEOUT ERROR. {max_wait_time} seconds have passed")
                    break

                if self.page.is_closed():
                    break

                if available_langs:
                    for lang_element in available_langs:
                        await asyncio.sleep(0.7)
                        if self.page.is_closed():
                            break

                        lang = await lang_element.get_attribute("aria-label")
                        if lang and lang not in self.lang_to_url:
                            try:
                                click_attempts += 1
                                url_before = self.page.url
                                await lang_element.click()
                                try:
                                    # Same-domain SPA: wait for active selector
                                    await self.page.wait_for_selector(f'[data-active="true"][aria-label="{lang}"]',
                                                                      timeout=8000)
                                    self.lang_to_url[lang] = self.page.url
                                except Exception:
                                    # Cross-domain: navigation to another site
                                    await self.page.wait_for_load_state('domcontentloaded', timeout=8000)
                                    if self.page.url != url_before:
                                        self.lang_to_url[lang] = self.page.url
                                        await self.page.go_back(wait_until='domcontentloaded', timeout=10000)
                                    else:
                                        raise Exception(f"Click had no effect for lang={lang}")
                                available_langs = await self.page.locator(
                                    '[data-testid="langsblock"] *[data-active="false"]').all()
                                expected_count = len(available_langs) + 1
                                click_attempts = 0
                                break
                            except Exception as e:
                                print(f"Ошибка клика: {e}")
                                if click_attempts > 5:
                                    break
                    else:
                        break
                else:
                    break

            return self.lang_to_url, expected_count
        except Exception as e:
            print(f"Ошибка в collect_languages: {e}")
            return self.lang_to_url, 0


async def check_redis_connection():
    try:
        await redis_client.ping()
        print("Successfully connected to Redis")
        return True
    except RedisConnectionError as e:
        print(f"Failed to connect to Redis: {e}")
        return False


async def scrape_single_url(url: str, semaphore: asyncio.Semaphore) -> Tuple[str, dict[Any, Any] | str | dict[str, str]]:
    redis_available = await check_redis_connection()

    if redis_available:
        try:
            cached_result = await redis_client.hget('cache', url)
            if cached_result:
                print(f"Cache hit for {url}")
                return url, json.loads(cached_result)
            print(f"Cache miss for {url}")
        except Exception as e:
            print(f"Error checking cache: {e}")
            redis_available = False

    browser_manager = BrowserManager(headless=True)
    try:
        async with semaphore:
            async with async_playwright() as playwright:
                await browser_manager.start(playwright)
                await browser_manager.goto(url)

                if browser_manager.page and not browser_manager.page.is_closed():
                    scraper = LanguageScraper(browser_manager.page)
                    result, expected_count = await scraper.collect_languages()

                    if result:
                        print(f"Got results for {url}")

                        if redis_available:
                            try:
                                async with redis_client.pipeline(transaction=True) as pipe:
                                    await pipe.hset('cache', url, json.dumps(result))
                                    await pipe.lpush('cache_keys', url)

                                    cache_size = await redis_client.llen('cache_keys')
                                    if cache_size > MAX_CACHE_SIZE:
                                        oldest_url = await redis_client.rpop('cache_keys')
                                        if oldest_url:
                                            await redis_client.hdel('cache', oldest_url)
                                            print(f"Removed oldest cache entry: {oldest_url}")

                                    await pipe.execute()
                                if len(result) < expected_count:
                                    print(f"Partial result cached ({len(result)} of {expected_count}): {url}")
                                else:
                                    print(f"Saved to cache: {url}")
                            except Exception as e:
                                print(f"Error saving to cache: {e}")

                    else:
                        print(f"No results found for {url}")
                    return url, result
                else:
                    print(f"Browser page is closed for {url}")
                    return url, {"error": f"Browser page is closed for {url}"}
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return url, {}
    finally:
        await browser_manager.close()


async def scrape_languages(urls: str, max_concurrent: int = 4) -> tuple[
    list[dict[Any, Any] | str | dict[str, str]], str]:
    urls = re.findall(r'https:/[^\s,"]+', urls)
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [scrape_single_url(url, semaphore) for url in urls]

    results = await asyncio.gather(*tasks)
    ordered_results = sorted(results, key=lambda x: urls.index(x[0]))

    return [result[1] for result in ordered_results], ""
