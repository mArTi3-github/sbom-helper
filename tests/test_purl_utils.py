from __future__ import annotations

import pytest

from purl_resolver.purl_utils import PurlComponents, PurlValidationError, normalize, validate


class TestValidate:

    def test_valid_purl_with_namespace(self) -> None:
        components = validate("pkg:maven/org.apache.commons/io@1.3.4")
        assert components.scheme == "pkg"
        assert components.type == "maven"
        assert components.namespace == "org.apache.commons"
        assert components.name == "io"
        assert components.version == "1.3.4"

    def test_valid_purl_without_namespace(self) -> None:
        components = validate("pkg:pypi/requests@2.31.0")
        assert components.scheme == "pkg"
        assert components.type == "pypi"
        assert components.namespace is None
        assert components.name == "requests"

    def test_valid_purl_with_qualifiers(self) -> None:
        components = validate("pkg:deb/debian/curl@7.50.3-1?arch=i386")
        assert components.type == "deb"
        assert components.namespace == "debian"
        assert components.name == "curl"
        assert components.qualifiers == {"arch": "i386"}

    def test_valid_purl_with_subpath(self) -> None:
        components = validate("pkg:golang/google.golang.org/genproto#googleapis/api/annotations")
        assert components.type == "golang"
        assert components.namespace == "google.golang.org"
        assert components.name == "genproto"
        assert components.subpath == "googleapis/api/annotations"

    def test_invalid_purl_raises_error(self) -> None:
        with pytest.raises(PurlValidationError):
            validate("not-a-purl")

    def test_empty_string_raises_error(self) -> None:
        with pytest.raises(PurlValidationError):
            validate("")

    def test_missing_scheme_raises_error(self) -> None:
        with pytest.raises(PurlValidationError):
            validate("npm/lodash")


class TestNormalize:

    def test_with_namespace(self) -> None:
        components = PurlComponents(
            type="maven", namespace="org.apache.commons", name="io"
        )
        assert normalize(components) == "pkg:maven/org.apache.commons/io"

    def test_without_namespace(self) -> None:
        components = PurlComponents(type="pypi", name="requests")
        assert normalize(components) == "pkg:pypi/requests"

    def test_version_stripped(self) -> None:
        components = PurlComponents(
            type="pypi", name="requests", version="2.31.0"
        )
        result = normalize(components)
        assert result == "pkg:pypi/requests"
        assert "@" not in result

    def test_qualifiers_stripped(self) -> None:
        components = PurlComponents(
            type="deb", namespace="debian", name="curl",
            qualifiers={"arch": "i386"},
        )
        result = normalize(components)
        assert result == "pkg:deb/debian/curl"
        assert "?" not in result

    def test_subpath_stripped(self) -> None:
        components = PurlComponents(
            type="golang", namespace="google.golang.org", name="genproto",
            subpath="googleapis/api/annotations",
        )
        result = normalize(components)
        assert result == "pkg:golang/google.golang.org/genproto"
        assert "#" not in result


class TestValidateAndNormalizeRoundtrip:

    def test_full_purl_normalizes_correctly(self) -> None:
        components = validate(
            "pkg:maven/org.apache.commons/io@1.3.4?repository_url=repo.spring.io#sub"
        )
        assert normalize(components) == "pkg:maven/org.apache.commons/io"

    def test_purl_without_namespace_normalizes(self) -> None:
        components = validate("pkg:npm/lodash@4.17.21")
        assert normalize(components) == "pkg:npm/lodash"

    def test_percent_encoded_namespace(self) -> None:
        components = validate("pkg:npm/%40angular/animation@12.3.1")
        assert components.namespace == "@angular"
        assert components.name == "animation"
        assert normalize(components) == "pkg:npm/%40angular/animation"
