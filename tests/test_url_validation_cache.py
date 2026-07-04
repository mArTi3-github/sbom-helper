from __future__ import annotations

import time
import tempfile
import pytest
from purl_resolver.url_validation_cache import UrlValidationCache


@pytest.fixture
def cache():
    tmpdir = tempfile.mkdtemp()
    c = UrlValidationCache(tmpdir)
    yield c
    c.clear()


class TestUrlValidationCache:
    def test_get_miss_before_put(self, cache):
        assert cache.get("https://example.com", max_age_seconds=3600) is None

    def test_get_hit_within_ttl(self, cache):
        cache.put("https://example.com")
        assert cache.get("https://example.com", max_age_seconds=3600) == "https://example.com"

    def test_get_miss_after_ttl(self, cache):
        cache.put("https://example.com")
        time.sleep(0.01)
        assert cache.get("https://example.com", max_age_seconds=0) is None

    def test_get_miss_different_url(self, cache):
        cache.put("https://example.com")
        assert cache.get("https://other.com", max_age_seconds=3600) is None

    def test_expire_removes_old_entries(self, cache):
        cache.put("https://old.com")
        time.sleep(0.01)
        cache.put("https://new.com")
        time.sleep(0.001)
        cache.expire(max_age_seconds=0.005)
        assert cache.get("https://old.com", max_age_seconds=3600) is None
        assert cache.get("https://new.com", max_age_seconds=3600) == "https://new.com"

    def test_expire_preserves_young_entries(self, cache):
        cache.put("https://example.com")
        cache.expire(max_age_seconds=3600)
        assert cache.get("https://example.com", max_age_seconds=3600) == "https://example.com"

    def test_clear_removes_all_entries(self, cache):
        cache.put("https://a.com")
        cache.put("https://b.com")
        cache.clear()
        assert cache.get("https://a.com", 3600) is None
        assert cache.get("https://b.com", 3600) is None

    def test_put_refreshes_timestamp(self, cache):
        cache.put("https://example.com")
        time.sleep(0.01)
        cache.put("https://example.com")
        assert cache.get("https://example.com", max_age_seconds=0.005) == "https://example.com"

    def test_persistence_across_instances(self, cache):
        cache.put("https://persist.com")
        dirpath = cache._cache.directory
        cache2 = UrlValidationCache(dirpath)
        assert cache2.get("https://persist.com", max_age_seconds=3600) == "https://persist.com"
        cache2.clear()