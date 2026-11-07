import pytest

from purl_resolver.purl_utils.case_rules import lowercase_purl


@pytest.mark.parametrize(
    ("purl", "expected"),
    [
        ("pkg:deb/Ubuntu/OpenSSL@3.0", "pkg:deb/ubuntu/openssl@3.0"),
        (
            "pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0",
            "pkg:golang/github.com/masterminds/semver@v3.0.0",
        ),
        ("pkg:gem/Rails@7.0.0", "pkg:gem/rails@7.0.0"),
        ("pkg:npm/MyScope/Left-Pad@1.0.0", "pkg:npm/myscope/left-pad@1.0.0"),
        ("pkg:npm/@Angular/Animation", "pkg:npm/%40angular/animation"),
        ("pkg:pypi/Django_X@1.0RC1", "pkg:pypi/django_x@1.0RC1"),
        (
            "pkg:oci/Ubuntu@SHA256:ABC?tag=V1",
            "pkg:oci/ubuntu@SHA256:ABC?tag=V1",
        ),
        (
            "pkg:hackage/User/Some_Package@1.0",
            "pkg:hackage/user/Some_Package@1.0",
        ),
        (
            "pkg:vscode-extension/Microsoft/VSCode-Python@1.0.0",
            "pkg:vscode-extension/microsoft/vscode-python@1.0.0",
        ),
        (
            "pkg:deb/Ubuntu/OpenSSL@3.0?Arch=AMD64#src/Lib",
            "pkg:deb/ubuntu/openssl@3.0?Arch=AMD64#src/Lib",
        ),
        (
            "pkg:cargo/NameSpace/NamePart@1.0",
            "pkg:cargo/namespace/NamePart@1.0",
        ),
        (
            "pkg:rpm/NameSpace/NamePart@1.0",
            "pkg:rpm/namespace/NamePart@1.0",
        ),
    ],
)
def test_checker_mode_lowercases_only_allowed_fields(purl, expected):
    assert lowercase_purl(purl, "sbom_checker") == expected


@pytest.mark.parametrize(
    ("purl", "expected"),
    [
        ("pkg:deb/Ubuntu/OpenSSL@3.0", "pkg:deb/ubuntu/openssl@3.0"),
        ("pkg:pypi/Django_X@1.0RC1", "pkg:pypi/django_x@1.0rc1"),
        (
            "pkg:oci/Ubuntu@SHA256:ABC?tag=V1",
            "pkg:oci/ubuntu@sha256:abc?tag=V1",
        ),
        (
            "pkg:huggingface/User/Model@V1.0",
            "pkg:huggingface/User/Model@v1.0",
        ),
        (
            "pkg:vscode-extension/Microsoft/VSCode-Python@1.0.0",
            "pkg:vscode-extension/microsoft/vscode-python@1.0.0",
        ),
        (
            "pkg:bitnami/NamePart@1.0",
            "pkg:bitnami/namepart@1.0",
        ),
        (
            "pkg:chrome-extension/NamePart@1.0",
            "pkg:chrome-extension/namepart@1.0",
        ),
        (
            "pkg:yocto/NameSpace/NamePart@1.0",
            "pkg:yocto/namespace/NamePart@1.0",
        ),
    ],
)
def test_purl_spec_mode_lowercases_only_allowed_fields(purl, expected):
    assert lowercase_purl(purl, "purl_spec") == expected


@pytest.mark.parametrize(
    ("purl", "mode"),
    [
        ("pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0", "purl_spec"),
        ("pkg:npm/MyScope/Left-Pad@1.0.0", "purl_spec"),
        ("pkg:gem/Rails@7.0.0", "purl_spec"),
        ("pkg:cpan/AUTHOR/DBI@1.0", "sbom_checker"),
        ("pkg:cpan/AUTHOR/DBI@1.0", "purl_spec"),
        ("pkg:cpan/author/DBI@1.0", "sbom_checker"),
        ("pkg:cpan/author/DBI@1.0", "purl_spec"),
        ("pkg:maven/Org.Apache/Commons-Lang@1.0", "sbom_checker"),
        ("pkg:maven/Org.Apache/Commons-Lang@1.0", "purl_spec"),
        ("pkg:swift/github.com/Alamofire/Alamofire@5.4.3", "sbom_checker"),
        ("pkg:swift/github.com/Alamofire/Alamofire@5.4.3", "purl_spec"),
        ("pkg:git/Owner/Repo@V1", "sbom_checker"),
        ("pkg:git/Owner/Repo@V1", "purl_spec"),
        ("pkg:huggingface/User/Model@V1.0", "sbom_checker"),
        ("pkg:nuget/Newtonsoft.Json@13.0", "sbom_checker"),
        ("pkg:cocoapods/Alamofire@5.0", "sbom_checker"),
        ("pkg:cran/SomePackage@1.0", "sbom_checker"),
        ("pkg:custom/NameSpace/NamePart@V1", "sbom_checker"),
        ("pkg:custom/NameSpace/NamePart@V1", "purl_spec"),
        ("pkg:NPM/left-pad@1.0", "sbom_checker"),
        ("pkg:NPM/left-pad@1.0", "purl_spec"),
        ("not-a-purl", "sbom_checker"),
        ("", "sbom_checker"),
    ],
)
def test_no_change_returns_none(purl, mode):
    assert lowercase_purl(purl, mode) is None


def test_type_is_lowercased_when_another_field_is_rewritten():
    assert (
        lowercase_purl("pkg:NPM/Left-Pad@1.0", "sbom_checker")
        == "pkg:npm/left-pad@1.0"
    )


def test_percent_encoded_uppercase_is_lowercased_and_suffix_is_verbatim():
    assert lowercase_purl(
        "pkg:deb/Ubuntu/OpenSSL%2DThing@3.0?Arch=AMD64#src%2FLib",
        "sbom_checker",
    ) == "pkg:deb/ubuntu/openssl-thing@3.0?Arch=AMD64#src%2FLib"


def test_encoded_slash_stays_encoded_in_name_namespace_and_version():
    assert lowercase_purl(
        "pkg:generic/GitHub.com/Foo%2FBar@1",
        "sbom_checker",
    ) == "pkg:generic/github.com/foo%2Fbar@1"

    assert lowercase_purl(
        "pkg:deb/My%2FOrg/OpenSSL@3.0",
        "sbom_checker",
    ) == "pkg:deb/my%2Forg/openssl@3.0"

    assert lowercase_purl(
        "pkg:oci/Ubuntu@SHA256%2FABC",
        "purl_spec",
    ) == "pkg:oci/ubuntu@sha256%2Fabc"
