"""search_crawl.py"""

import asyncio, re, time, json, hashlib
from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
import aiohttp
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
import tldextract
from yarl import URL
import urllib.robotparser as robotparser
from context_store import save_context
# -------- Utility -------- #
USER_AGENT = "VibeCrawler/1.0 (+https://example.com; contact: ops@vibe.local)"

def normalize_url(base: str, href: str) -> Optional[str]:
    if not href:
        return None
    try:
        u = URL(href)
        if not u.scheme:
            u = URL(urljoin(base, href))
        # Drop fragments, normalize
        u = u.with_fragment(None)
        return str(u)
    except Exception:
        return None

def same_reg_domain(a: str, b: str) -> bool:
    ea, eb = tldextract.extract(a), tldextract.extract(b)
    return (ea.domain, ea.suffix) == (eb.domain, eb.suffix)

def guess_slug(url: str) -> str:
    path = URL(url).path
    if not path or path == "/":
        return "index"
    return path.strip("/").replace("/", "-")

# -------- DuckDuckGo HTML search (best-effort) -------- #
# NOTE: For production, consider a search API (Serper, Google Custom Search, Tavily).
SEARCH_ENDPOINT = "https://duckduckgo.com/html/"
HEADERS = {"User-Agent": USER_AGENT, "Referer": "https://duckduckgo.com/"}

async def ddg_search(session: aiohttp.ClientSession, query: str, max_results: int = 10) -> List[Dict[str, str]]:
    params = {"q": query}
    async with session.get(SEARCH_ENDPOINT, params=params, headers=HEADERS) as resp:
        html = await resp.text()
    soup = BeautifulSoup(html, "lxml")
    results = []
    for a in soup.select("a.result__a")[:max_results]:
        href = a.get("href")
        title = a.get_text(" ", strip=True)
        if href:
            results.append({"title": title, "url": href})
    return results

# -------- Robots + Sitemaps -------- #
async def read_robots_txt(session: aiohttp.ClientSession, site_root: str) -> Tuple[robotparser.RobotFileParser, List[str]]:
    robots_url = URL(site_root).with_path("/robots.txt").with_query(None)
    rp = robotparser.RobotFileParser()
    sitemaps: List[str] = []
    try:
        async with session.get(str(robots_url), headers=HEADERS) as resp:
            txt = await resp.text()
        rp.parse(txt.splitlines())
        # extract sitemaps
        for line in txt.splitlines():
            if line.lower().startswith("sitemap:"):
                sm = line.split(":", 1)[1].strip()
                if sm: sitemaps.append(sm)
    except Exception:
        pass
    return rp, sitemaps

async def fetch_url(session: aiohttp.ClientSession, url: str) -> Optional[Tuple[str, str]]:
    try:
        async with session.get(url, headers=HEADERS, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200 or "text/html" not in resp.headers.get("content-type", ""):
                return None
            text = await resp.text(errors="ignore")
            final_url = str(resp.url)
            return final_url, text
    except Exception:
        return None

def _identify_platform(html: str) -> str:
    """A simple heuristic to guess the website's platform."""
    if '/wp-content/' in html or '/wp-json/' in html:
        return "WordPress"
    if 'content="Webflow"' in html or 'class="w-' in html:
        return "Webflow"
    if 'Shopify.theme' in html or 'cdn.shopify.com' in html:
        return "Shopify"
    if '"@wix/thunderbolt"' in html:
        return "Wix"
    # Lovable seems to be a specific agency, harder to detect generically.
    # We can add more detectors here as needed.
    return "unknown"

def extract_page_data(url: str, html: str) -> Dict:
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")[:120]
    meta_desc = ""
    m = soup.find("meta", attrs={"name":"description"})
    if m and m.get("content"):
        meta_desc = m.get("content").strip()[:300]
    # canonical
    canonical = ""
    c = soup.find("link", rel=lambda v: v and "canonical" in v)
    if c and c.get("href"):
        canonical = normalize_url(url, c.get("href")) or ""
    # headings (first H1/H2s)
    h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")][:2]
    h2 = [h.get_text(" ", strip=True) for h in soup.find_all("h2")][:6]
    # internal links (same hostname)
    links = []
    for a in soup.find_all("a", href=True):
        u = normalize_url(url, a["href"])
        if u:
            links.append(u)
    platform = _identify_platform(html)
    return {
        "url": url,
        "slug": guess_slug(url),
        "title": title,
        "platform": platform,
        "meta_title": title or "",
        "meta_description": meta_desc,
        "canonical": canonical,
        "h1": h1,
        "h2": h2,
        "internal_links": links,
        "html": html
    }

async def parse_sitemap_urls(session: aiohttp.ClientSession, sitemap_url: str, limit: int = 2000) -> List[str]:
    try:
        async with session.get(sitemap_url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            xml = await resp.text()
    except Exception:
        return []
    urls: List[str] = []
    soup = BeautifulSoup(xml, "xml")
    if soup.find("sitemapindex"):
        for sm in soup.find_all("sitemap"):
            loc = sm.find("loc")
            if loc and loc.text:
                urls.extend(await parse_sitemap_urls(session, loc.text.strip(), limit))
                if len(urls) >= limit: break
    else:
        for u in soup.find_all("url"):
            loc = u.find("loc")
            if loc and loc.text:
                urls.append(loc.text.strip())
                if len(urls) >= limit: break
    return urls

# -------- Site crawler -------- #
@dataclass
class CrawlConfig:
    max_pages: int = 300
    same_domain_only: bool = True
    concurrency: int = 8
    rate_limit_per_host: int = 4  # requests/second

@dataclass
class CrawlResult:
    pages: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

async def crawl_site(root_url: str, config: CrawlConfig = CrawlConfig()) -> CrawlResult:
    root = str(URL(root_url))
    origin = f"{URL(root).scheme}://{URL(root).host}"
    limiter = AsyncLimiter(config.rate_limit_per_host, time_period=1.0)
    visited: Set[str] = set()
    q: asyncio.Queue[str] = asyncio.Queue()
    await q.put(root)
    result = CrawlResult()

    async with aiohttp.ClientSession() as session:
        rp, robots_sitemaps = await read_robots_txt(session, origin)
        # Try sitemaps first
        sitemap_urls: List[str] = []
        for sm in (robots_sitemaps + [str(URL(origin).with_path("/sitemap.xml")), str(URL(origin).with_path("/sitemap_index.xml"))]):
            sitemap_urls.extend(await parse_sitemap_urls(session, sm))
        for u in sitemap_urls[:config.max_pages]:
            await q.put(u)

        async def worker():
            nonlocal visited
            while len(result.pages) < config.max_pages:
                try:
                    url = await asyncio.wait_for(q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    break
                if url in visited:
                    q.task_done(); continue
                visited.add(url)

                # domain filter
                if config.same_domain_only and not same_reg_domain(root, url):
                    q.task_done(); continue

                # robots
                try:
                    if rp and not rp.can_fetch(USER_AGENT, url):
                        q.task_done(); continue
                except Exception:
                    pass

                # fetch with RL
                try:
                    async with limiter:
                        fetched = await fetch_url(session, url)
                except Exception as e:
                    result.errors.append(f"fetch error: {url} -> {e}")
                    q.task_done(); continue

                if not fetched:
                    q.task_done(); continue

                final_url, html = fetched
                page = extract_page_data(final_url, html)
                result.pages.append(page)

                # enqueue internal links (BFS)
                for link in page["internal_links"]:
                    if link not in visited and len(result.pages) + q.qsize() < config.max_pages:
                        await q.put(link)
                q.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(config.concurrency)]
        await asyncio.gather(*workers, return_exceptions=True)

    # Deduplicate pages by URL
    dedup: Dict[str, Dict] = {}
    for p in result.pages:
        dedup[p["url"]] = p
    result.pages = list(dedup.values())
    return result

# -------- Simple memory dump helper -------- #
def to_memory_snapshot(website_url: str, pages: List[Dict], socials: Optional[Dict] = None) -> Dict:
    platforms = [p.get("platform", "unknown") for p in pages if p.get("platform") != "unknown"]
    main_platform = max(set(platforms), key=platforms.count) if platforms else "unknown"
    return {
        "website": {
            "url": website_url,
            "platform": main_platform,
            "seo_plugin": "unknown",
            "pages": pages,
            "sitemaps": []
        },
        "social": socials or {},
        "business": {
            "name": urlparse(website_url).hostname.replace("www.","") if website_url else "",
            "icps": [], "offers": [], "locations": [],
            "constraints": {}, "goals": {}
        }
    }

async def build_weekly_snapshot(session_id: str, website_url: str, socials: Optional[dict] = None, max_pages: int = 300) -> dict:
    """
    High-level tool that crawl a site, identifies its platform,
    and saves a complete snapshot to the context file.
    """
    cfg = CrawlConfig(max_pages=max_pages)
    result = await crawl_site(website_url, cfg)
    pages = result.pages

    # Identify the primary platform from the crawled pages
    platform = [p.get("platform", "unknown") for p in pages if p.get("platform") != "unknown"]
    main_platform = max(set(platform), key=platform.count) if platform else "unknown"

    # Create the context structure
    ctx = {
        "website": {
            "url": website_url,
            "platform": main_platform,
            "pages": pages,
        },
        "social": socials or {},
        "business": { "name": urlparse(website_url).hostname.replace("www.", "")},
        "history": [],
        "state": "start",
    }

    save_context(session_id, ctx)
    return {"pages": len(pages), "platform": main_platform, "errors": len(result.errors)}