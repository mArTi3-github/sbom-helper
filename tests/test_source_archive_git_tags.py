import asyncio
import os
import stat

import pytest

from purl_resolver.source_archive.git_tags import (
    GitTagsError,
    fetch_tags,
    parse_ls_remote,
)


def test_parse_lightweight_and_annotated_tags() -> None:
    output = (
        "aaa\trefs/tags/v1.0.0\n"
        "bbb\trefs/tags/v1.1.0\n"
        "ccc\trefs/tags/v1.1.0^{}\n"
        "ddd\trefs/heads/main\n"
    )
    parsed = {t.name: t.commit_sha for t in parse_ls_remote(output)}
    assert parsed == {"v1.0.0": "aaa", "v1.1.0": "ccc"}


@pytest.mark.asyncio
async def test_fetch_tags_rejects_non_http_url() -> None:
    with pytest.raises(GitTagsError):
        await fetch_tags("file:///tmp/repo", timeout=1)


@pytest.mark.asyncio
async def test_fetch_tags_kills_process_on_timeout(tmp_path) -> None:
    fake_git = tmp_path / "git"
    fake_git.write_text("#!/bin/sh\nsleep 10\n")
    fake_git.chmod(fake_git.stat().st_mode | stat.S_IEXEC)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        with pytest.raises(GitTagsError):
            await asyncio.wait_for(
                fetch_tags("https://github.com/example/repo", timeout=0.2),
                timeout=2,
            )
