"""Small, non-crawling fallback scraper for repository candidates."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from purl2repo.ecosystems.base import Metadata
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, RepositoryCandidate, ScrapedCandidate
from purl2repo.utils.text import normalize_label
from purl2repo.utils.urls import classify_host, normalize_repo_url, url_host

MAX_SCRAPE_PAGES = 3
SCRAPE_SCORE_CAP = 60.0
DIRECT_HOST_PURL_TYPES = {"github", "gitlab", "bitbucket"}
NO_UPSTREAM_SCRAPE_TYPES = {"huggingface", "mlflow"}


class _AnchorParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._active_href: str | None = None
        self._active_text: list[str] = []
        self.links: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._active_href = urljoin(self.base_url, href)
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            text = data.strip()
            if text:
                self._active_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._active_href:
            return
        label = " ".join(self._active_text).strip() or None
        self.links.append((self._active_href, label))
        self._active_href = None
        self._active_text = []


class FallbackScraper:
    """Extract repository-like links from a small set of explicitly allowed pages."""

    def __init__(self, client: HttpClient, max_pages: int = MAX_SCRAPE_PAGES) -> None:
        self.client = client
        self.max_pages = max_pages

    def scrape(self, parsed: ParsedPurl, pages: list[str]) -> list[ScrapedCandidate]:
        if not should_scrape_purl(parsed):
            return []

        scraped: list[ScrapedCandidate] = []
        for page in _dedupe_pages(pages)[: self.max_pages]:
            html = self.client.get_text(page)
            parser = _AnchorParser(page)
            parser.feed(html)
            for url, label in parser.links:
                normalized = normalize_repo_url(url)
                if not normalized or normalized == page.rstrip("/"):
                    continue
                if not _looks_like_scraped_repo_candidate(url, normalized, label):
                    continue
                scraped.append(
                    ScrapedCandidate(
                        url=url,
                        normalized_url=normalized,
                        source_page=page,
                        extraction_method="html_anchor",
                        label_context=label,
                        score_cap=SCRAPE_SCORE_CAP,
                        reasons=[
                            f"Scraped repository-like link from {page}",
                            _label_reason(label),
                        ],
                    )
                )
        return _dedupe_scraped(scraped)


def should_scrape_purl(parsed: ParsedPurl) -> bool:
    return parsed.type not in DIRECT_HOST_PURL_TYPES | NO_UPSTREAM_SCRAPE_TYPES


def scraped_to_repository_candidate(scraped: ScrapedCandidate) -> RepositoryCandidate | None:
    normalized = scraped.normalized_url
    if not normalized:
        return None
    host = url_host(normalized)
    reasons = [
        *[reason for reason in scraped.reasons if reason],
        f"Extraction method: {scraped.extraction_method}",
        f"Source page: {scraped.source_page}",
        f"Score cap: {scraped.score_cap:g}",
    ]
    return RepositoryCandidate(
        url=scraped.url,
        normalized_url=normalized,
        host=host,
        repository_type=classify_host(host),
        source="scrape",
        score=0.0,
        reasons=reasons,
    )


def default_fallback_pages(parsed: ParsedPurl, metadata: Metadata) -> list[str]:
    _ = metadata
    if parsed.type == "pypi":
        return [f"https://pypi.org/project/{parsed.name}/"]
    if parsed.type == "npm":
        package = f"{parsed.namespace}/{parsed.name}" if parsed.namespace else parsed.name
        return [f"https://www.npmjs.com/package/{package}"]
    if parsed.type == "cargo":
        return [f"https://crates.io/crates/{parsed.name}"]
    if parsed.type == "maven" and parsed.namespace:
        return [f"https://central.sonatype.com/artifact/{parsed.namespace}/{parsed.name}"]
    return []


def _dedupe_pages(pages: list[str]) -> list[str]:
    deduped: list[str] = []
    for page in pages:
        if page.startswith(("https://", "http://")) and page not in deduped:
            deduped.append(page)
    return deduped


def _dedupe_scraped(candidates: list[ScrapedCandidate]) -> list[ScrapedCandidate]:
    deduped: dict[str, ScrapedCandidate] = {}
    for candidate in candidates:
        if candidate.normalized_url and candidate.normalized_url not in deduped:
            deduped[candidate.normalized_url] = candidate
    return list(deduped.values())


def _looks_like_scraped_repo_candidate(
    original_url: str,
    normalized_url: str,
    label: str | None,
) -> bool:
    if _is_blocked_navigation_url(normalized_url):
        return False
    host = url_host(normalized_url)
    if classify_host(host) != "generic_git":
        return True
    if original_url.rstrip("/").endswith(".git"):
        return True
    return bool(label and _is_generic_source_label(label))


def _is_generic_source_label(label: str) -> bool:
    normalized = normalize_label(label)
    if any(
        word in normalized.split() for word in {"conduct", "policy", "privacy", "support", "terms"}
    ):
        return False
    if normalized in {"code", "source", "source code", "repo", "repository", "scm"}:
        return True
    return any(word in normalized for word in ("source", "repository", "repo", "scm"))


def _is_blocked_navigation_url(url: str) -> bool:
    parsed = urlsplit(url)
    path_segments = {segment.lower() for segment in parsed.path.split("/") if segment}
    if path_segments & {
        "about",
        "conduct",
        "contact",
        "help",
        "policies",
        "policy",
        "privacy",
        "security",
        "support",
        "terms",
    }:
        return True
    return parsed.hostname in {"www.npmjs.com", "npmjs.com"} and not parsed.path.startswith(
        "/package/"
    )


def _label_reason(label: str | None) -> str:
    if not label:
        return "No anchor label context was available"
    return f"Anchor label context: {label}"
