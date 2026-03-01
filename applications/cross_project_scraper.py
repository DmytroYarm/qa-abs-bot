import asyncio
import logging
from playwright.async_api import async_playwright, Page
from .browser_manager import BrowserManager
from .language_scraper.scraper import LanguageScraper

logger = logging.getLogger(__name__)


async def get_brand_and_article(page: Page) -> tuple[str, str]:
    """
    Extract brand and article from an exist.ua product page.
    Brand comes from the <a> inside the 'Бренд:' span.
    Article comes from the <strong> inside the 'Номер товару:' span.
    """
    result = await page.evaluate("""
        () => {
            const spans = document.querySelectorAll('[data-testid="page-title"] span');
            let brand = null, article = null;
            for (const span of spans) {
                const text = span.innerText || '';
                if (text.includes('Бренд')) {
                    const a = span.querySelector('a');
                    if (a) brand = a.innerText.trim();
                }
                if (text.includes('Номер товару') || text.includes('Номер товара')) {
                    const strong = span.querySelector('strong');
                    if (strong) article = strong.innerText.trim();
                }
            }
            return { brand, article };
        }
    """)
    brand = result.get('brand')
    article = result.get('article')
    if not brand or not article:
        raise ValueError(f"Could not extract brand/article (got brand={brand!r}, article={article!r})")
    return brand, article


async def find_on_2407(brand: str, article: str, browser_manager: BrowserManager) -> str | None:
    """
    Search 2407.pl for a product by brand+article.
    Clicks the 'Детальнее про товар' button next to the matching product
    and returns the resulting product page URL.
    """
    page = browser_manager.page

    await browser_manager.goto('https://2407.pl/uk/')
    await page.wait_for_load_state('domcontentloaded', timeout=15000)
    await asyncio.sleep(2)

    # Dismiss cookie consent overlay
    await page.evaluate("""
        () => ['CybotCookiebotDialogBodyUnderlay', 'CybotCookiebotDialog']
              .forEach(id => { const e = document.getElementById(id); if (e) e.remove(); })
    """)

    # Open the search panel via the header search button
    search_btn = page.locator('button[aria-label="search"]').last
    await search_btn.dispatch_event('click')
    await asyncio.sleep(1)

    # Type brand + article into the HeaderSearchBlockInner input
    search_input = page.locator('[class*="HeaderSearchBlockInner"] input, input[name="input"]').first
    await search_input.wait_for(state='visible', timeout=5000)
    await search_input.fill(f'{brand} {article}')
    logger.info(f"Searching 2407.pl for: {brand} {article}")
    await asyncio.sleep(4)  # wait for dropdown to fully populate

    # Normalize for comparison (strip spaces, hyphens, lowercase)
    def normalize(s: str) -> str:
        return s.replace('-', '').replace(' ', '').lower()

    article_norm = normalize(article)
    brand_norm = normalize(brand)

    # Find the 'Детальнее про товар' link adjacent to our matching product.
    # Each dropdown result row contains: product text link + Детальнее button.
    # We look for the row whose text contains both brand and article.
    detail_href = await page.evaluate(f"""
        () => {{
            const articleNorm = '{article_norm}';
            const brandNorm = '{brand_norm}';

            function norm(s) {{
                return (s || '').replace(/-/g, '').replace(/\\s/g, '').toLowerCase();
            }}

            const detailLinks = [...document.querySelectorAll('a[title*="Детальн"]')];
            for (const link of detailLinks) {{
                // Walk up to find the row container that holds both the product info and this button
                let container = link.parentElement;
                for (let i = 0; i < 5; i++) {{
                    if (!container) break;
                    const text = norm(container.innerText || '');
                    if (text.includes(articleNorm) && text.includes(brandNorm)) {{
                        return link.href;
                    }}
                    container = container.parentElement;
                }}
            }}
            // Fallback: return first Детальнее link if any found
            return detailLinks.length > 0 ? detailLinks[0].href : null;
        }}
    """)

    if not detail_href:
        logger.warning(f"No 'Детальнее' link found for {brand} {article}")
        return None

    logger.info(f"Found 'Детальнее' link: {detail_href}")

    # Click the matching button and wait for navigation to the product card
    try:
        detail_locator = page.locator(f'a[title*="Детальн"][href*="{detail_href.split("2407.pl")[-1][:40]}"]').first
        async with page.expect_navigation(wait_until='domcontentloaded', timeout=15000):
            await detail_locator.click()
        product_url = page.url
        logger.info(f"Navigated to product card: {product_url}")
        return product_url
    except Exception as e:
        logger.warning(f"Click navigation failed ({e}), using href directly: {detail_href}")
        return detail_href


async def scrape_cross_project(exist_url: str) -> dict:
    """
    Given an exist.ua product URL, scrapes language links from:
      - exist.ua (ua, ru)
      - 2407.pl (pl, ua, en, ru, de → wunderautoteile.de)

    Returns a dict with keys 'exist_ua' and '2407_pl', each containing
    a dict of {lang: url}, or an error string.
    """
    result = {}
    brand, article = None, None
    browser_manager = BrowserManager(headless=True)

    async with async_playwright() as playwright:
        await browser_manager.start(playwright)

        # ── Step 1: scrape exist.ua ───────────────────────────────────────────
        await browser_manager.goto(exist_url)
        page = browser_manager.page

        if page.is_closed():
            return {'error': 'Browser page closed unexpectedly'}

        try:
            brand, article = await get_brand_and_article(page)
            logger.info(f"Extracted: brand={brand!r}, article={article!r}")
        except Exception as e:
            logger.warning(f"Could not extract brand/article: {e}")

        exist_scraper = LanguageScraper(page)
        exist_langs, _ = await exist_scraper.collect_languages()
        result['exist_ua'] = exist_langs if exist_langs else 'No language links found'

    await browser_manager.close()

    # ── Step 2: search and scrape 2407.pl (Chrome channel bypasses Cloudflare) ─
    if brand and article:
        bm_2407 = BrowserManager(headless=True, channel='chrome')
        async with async_playwright() as playwright:
            await bm_2407.start(playwright)

            product_url_2407 = await find_on_2407(brand, article, bm_2407)

            if product_url_2407:
                # If find_on_2407 already navigated via click, page is on the product card.
                # If it returned a fallback href, navigate there explicitly.
                if bm_2407.page.url != product_url_2407:
                    await bm_2407.goto(product_url_2407)

                page_2407 = bm_2407.page
                if not page_2407.is_closed():
                    scraper_2407 = LanguageScraper(page_2407)
                    langs_2407, _ = await scraper_2407.collect_languages()
                    result['2407_pl'] = langs_2407 if langs_2407 else 'No language links found'
                else:
                    result['2407_pl'] = 'Browser page closed'
            else:
                result['2407_pl'] = f'Product not found on 2407.pl for {brand} {article}'

            await bm_2407.close()
    else:
        result['2407_pl'] = 'Could not extract brand/article from exist.ua page'

    return result
