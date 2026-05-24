"""Go module adapter."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import quote

from purl2repo.ecosystems.base import EcosystemResolver, Metadata, dedupe_candidates, make_candidate
from purl2repo.errors import MetadataFetchError
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, RepositoryCandidate
from purl2repo.utils.urls import is_repo_like_url

DIRECT_GO_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}


class GoResolver(EcosystemResolver):
    ecosystem = "golang"
    metadata_source = "go-module-proxy"

    def fetch_metadata(self, parsed: ParsedPurl, client: HttpClient) -> Metadata:
        module_path = go_module_path(parsed)
        escaped = quote(module_path, safe="/")
        if parsed.version:
            url = f"https://proxy.golang.org/{escaped}/@v/{parsed.version}.info"
        else:
            url = f"https://proxy.golang.org/{escaped}/@latest"
        metadata: Metadata = {"module_path": module_path}
        proxy_error: MetadataFetchError | None = None
        try:
            metadata["proxy_info"] = client.get_json(url)
        except MetadataFetchError as exc:
            proxy_error = exc

        go_import_repo = _fetch_go_import_repo(module_path, client)
        if go_import_repo:
            metadata["go_import_repo"] = go_import_repo

        if proxy_error:
            metadata["_purl2repo_metadata_warning"] = (
                f"Could not fetch metadata from go-module-proxy: {proxy_error}"
            )
        if metadata.get("proxy_info") or go_import_repo or is_repo_like_url(module_path):
            return metadata
        raise proxy_error or MetadataFetchError(f"No Go metadata found for {module_path}")

    def extract_candidates(
        self, parsed: ParsedPurl, metadata: Metadata
    ) -> list[RepositoryCandidate]:
        module_path = metadata.get("module_path")
        if not isinstance(module_path, str):
            module_path = go_module_path(parsed)
        candidates: list[RepositoryCandidate | None] = []
        go_import_repo = metadata.get("go_import_repo")
        if isinstance(go_import_repo, str):
            candidates.append(
                make_candidate(
                    go_import_repo,
                    "go_import_meta",
                    "Candidate from Go go-import metadata",
                )
            )
        if is_repo_like_url(module_path):
            candidates.append(
                make_candidate(
                    module_path,
                    "module_path",
                    "Candidate inferred from Go module path",
                )
            )
        return dedupe_candidates(candidates)

    def metadata_fetch_fallback(self, parsed: ParsedPurl) -> Metadata | None:
        module_path = go_module_path(parsed)
        if is_repo_like_url(module_path):
            return {"module_path": module_path, "proxy_info": None}
        return None


def go_module_path(parsed: ParsedPurl) -> str:
    return f"{parsed.namespace}/{parsed.name}" if parsed.namespace else parsed.name


class _GoImportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        values = dict(attrs)
        if values.get("name") != "go-import":
            return
        content = values.get("content")
        if not content:
            return
        parts = content.split()
        if len(parts) == 3:
            self.entries.append((parts[0], parts[1], parts[2]))


def _fetch_go_import_repo(module_path: str, client: HttpClient) -> str | None:
    host = module_path.split("/", 1)[0].lower()
    if host in DIRECT_GO_HOSTS:
        return None
    try:
        html = client.get_text(f"https://{module_path}?go-get=1")
    except MetadataFetchError:
        return None
    parser = _GoImportParser()
    parser.feed(html)
    for prefix, vcs, repo_url in parser.entries:
        if vcs == "mod":
            continue
        if module_path == prefix or module_path.startswith(f"{prefix}/"):
            return repo_url
    return None
