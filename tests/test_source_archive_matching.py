from purl_resolver.source_archive.matching import (
    TagInfo,
    find_exact,
    find_near,
    parse_version,
    pick_nearer,
)


def tags(*names: str) -> list[TagInfo]:
    return [TagInfo(name=n, commit_sha=f"sha-{n}") for n in names]


def test_parse_version_splits_numeric_chain_and_suffix() -> None:
    assert parse_version("23.8.16.40").numbers == (23, 8, 16, 40)
    assert parse_version("2.0.0-rc1").suffix == "rc1"
    assert parse_version("main") is None


def test_find_exact_accepts_tag_prefix_and_suffix() -> None:
    version = parse_version("23.8.16.40")
    matches = find_exact(tags("v23.8.16.40-lts"), version)
    assert matches[0].tag.name == "v23.8.16.40-lts"
    assert matches[0].match_type == "exact"
    assert matches[0].matched_version == "23.8.16.40"


def test_find_exact_handles_underscore_separated_tags() -> None:
    matches = find_exact(tags("rel_23_8_16_40"), parse_version("23.8.16.40"))
    assert matches[0].tag.name == "rel_23_8_16_40"


def test_find_exact_pads_missing_components() -> None:
    assert find_exact(tags("v1.2.0"), parse_version("1.2"))[0].match_type == "exact"


def test_find_exact_requires_matching_prerelease_suffix() -> None:
    assert find_exact(tags("v2.0.0"), parse_version("2.0.0-rc1")) == []


def test_find_exact_priority_prefers_non_prerelease_then_shorter() -> None:
    matches = find_exact(tags("v1.2.3-rc1", "v1.2.3-lts", "1.2.3"), parse_version("1.2.3"))
    assert [m.tag.name for m in matches] == ["1.2.3", "v1.2.3-lts", "v1.2.3-rc1"]


def test_find_near_prefers_lower_then_higher_in_same_major_minor() -> None:
    version = parse_version("23.8.16.40")
    assert find_near(tags("v23.8.16.39", "v23.8.16.41"), version).tag.name == "v23.8.16.39"
    assert find_near(tags("v23.8.16.41"), version).tag.name == "v23.8.16.41"


def test_find_near_rejects_other_major_minor() -> None:
    assert find_near(tags("v24.1.0", "v23.9.1"), parse_version("23.8.16.40")) is None


def test_find_near_includes_equal_numbers_with_suffix_mismatch() -> None:
    match = find_near(tags("v2.5.0", "v2.4.9"), parse_version("2.5.0-rc1"))
    assert match.tag.name == "v2.5.0"
    assert match.match_type == "near"


def test_pick_nearer_uses_distance_priority() -> None:
    version = parse_version("2.5.1")
    lower = find_near(tags("v2.5.0"), version)
    higher = find_near(tags("v2.5.2"), version)
    assert pick_nearer(version, lower, higher).tag.name == "v2.5.0"
