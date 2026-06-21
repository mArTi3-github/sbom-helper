from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

from purl_resolver.resolver.librariesio import LibrariesIoResolver
from purl_resolver.resolver.purl2repo import Purl2RepoResolver
from purl_resolver.settings_store import AppSettings


class TestResolverRegistration:
    def test_librariesio_registered_when_enabled(self) -> None:
        mock_store = MagicMock()
        mock_store.load.return_value = AppSettings(
            librariesio_enabled=True,
            librariesio_api_key="test_key",
        )

        resolvers = []
        settings = mock_store.load()
        resolvers.append(Purl2RepoResolver())
        if settings.librariesio_enabled and settings.librariesio_api_key:
            resolvers.append(LibrariesIoResolver(api_key=settings.librariesio_api_key))

        assert len(resolvers) == 2
        assert isinstance(resolvers[1], LibrariesIoResolver)

    def test_librariesio_not_registered_when_disabled(self) -> None:
        mock_store = MagicMock()
        mock_store.load.return_value = AppSettings(
            librariesio_enabled=False,
            librariesio_api_key=None,
        )
        settings = mock_store.load()

        resolvers = [Purl2RepoResolver()]
        if settings.librariesio_enabled and settings.librariesio_api_key:
            resolvers.append(LibrariesIoResolver(api_key=settings.librariesio_api_key))

        assert len(resolvers) == 1

    def test_librariesio_not_registered_without_key(self) -> None:
        mock_store = MagicMock()
        mock_store.load.return_value = AppSettings(
            librariesio_enabled=True,
            librariesio_api_key=None,
        )
        settings = mock_store.load()

        resolvers = [Purl2RepoResolver()]
        if settings.librariesio_enabled and settings.librariesio_api_key:
            resolvers.append(LibrariesIoResolver(api_key=settings.librariesio_api_key))

        assert len(resolvers) == 1


class TestFindSpaDir:
    def test_returns_none_when_no_dir_exists(self, tmp_path: pathlib.Path) -> None:
        """_find_spa_dir returns None when no SPA directory is found anywhere."""
        from purl_resolver.main import _find_spa_dir

        with (
            patch("purl_resolver.main.pathlib.Path.is_dir", return_value=False),
        ):
            result = _find_spa_dir()
        assert result is None

    def test_returns_path_when_docker_dir_exists(self, tmp_path: pathlib.Path) -> None:
        """_find_spa_dir returns /app/frontend/dist when it exists."""
        docker_dir = pathlib.Path("/app/frontend/dist")
        from purl_resolver.main import _find_spa_dir

        def fake_is_dir(self_):
            return self_ == docker_dir

        with patch("purl_resolver.main.pathlib.Path.is_dir", fake_is_dir):
            result = _find_spa_dir()
        assert result == docker_dir
