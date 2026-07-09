from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.router import router
from purl_resolver.sbom.images_list_converter import ImagesListConverter
from purl_resolver.sbom.parser import SbomParseError


class TestImagesListConverter:
    def test_dedup_by_purl(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "nginx",
                    "version": "1.21",
                    "purl": "pkg:docker/nginx@1.21",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "nginx",
                    "version": "1.21",
                    "purl": "pkg:docker/nginx@1.21",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "postgres",
                    "version": "14",
                    "purl": "pkg:docker/postgres@14",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert len(result.images_list["components"]) == 2
        assert result.images[0].name == "nginx"
        assert result.images[0].duplicates_removed == 1
        assert result.images[1].name == "postgres"
        assert result.images[1].duplicates_removed == 0

    def test_dedup_no_purl_not_deduped(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert len(result.images_list["components"]) == 2
        assert result.images[0].duplicates_removed == 0
        assert result.images[1].duplicates_removed == 0

    def test_dedup_already_valid_list_with_dups(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "nginx",
                    "version": "1.21",
                    "purl": "pkg:docker/nginx@1.21",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "nginx",
                    "version": "1.21",
                    "purl": "pkg:docker/nginx@1.21",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is True
        assert len(result.images_list["components"]) == 1
        assert result.images[0].duplicates_removed == 1

    def test_dedup_no_duplicates(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "purl": "pkg:docker/web@1.0",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is False
        assert len(result.images_list["components"]) == 1
        assert result.images[0].duplicates_removed == 0

    def test_dedup_multiple_purls(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "a",
                    "version": "1",
                    "purl": "pkg:docker/a",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "a",
                    "version": "1",
                    "purl": "pkg:docker/a",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "b",
                    "version": "1",
                    "purl": "pkg:docker/b",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "b",
                    "version": "1",
                    "purl": "pkg:docker/b",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "b",
                    "version": "1",
                    "purl": "pkg:docker/b",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
                {
                    "type": "container",
                    "name": "c",
                    "version": "1",
                    "purl": "pkg:docker/c",
                    "properties": [{"name": "GOST:attack_surface", "value": "no"}],
                },
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert len(result.images_list["components"]) == 3
        assert result.images[0].duplicates_removed == 1
        assert result.images[1].duplicates_removed == 2
        assert result.images[2].duplicates_removed == 0

    def test_already_valid_images_list(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {
                    "type": "application",
                    "name": "product",
                    "version": "1.0",
                    "manufacturer": {"name": "Acme"},
                },
            },
            "components": [
                {
                    "type": "container",
                    "name": "manager",
                    "version": "3.0.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "yes"},
                    ],
                    "components": [
                        {"type": "library", "name": "lib", "version": "1.0"}
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is False
        assert len(result.images) == 1
        assert result.images[0].name == "manager"
        assert result.images[0].version == "3.0.0"

    def test_containers_inside_nested_are_promoted(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "application",
                    "name": "app",
                    "version": "1.0",
                    "components": [
                        {
                            "type": "container",
                            "name": "gateway",
                            "version": "2.0",
                            "properties": [
                                {"name": "GOST:attack_surface", "value": "yes"},
                                {"name": "GOST:security_function", "value": "no"},
                            ],
                        }
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is True
        assert len(result.images_list["components"]) == 1
        assert result.images_list["components"][0]["name"] == "gateway"

    def test_no_containers_returns_empty_components(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "library", "name": "lib-a", "version": "1.0"}
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is True
        assert result.images_list["components"] == []

    def test_non_container_top_level_removed(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "library", "name": "lib-a", "version": "1.0"},
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                },
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is True
        assert len(result.images_list["components"]) == 1
        assert result.images_list["components"][0]["name"] == "web"

    def test_missing_name_flag(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_name is True

    def test_missing_version_flag(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_version is True

    def test_missing_properties_flag(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "container", "name": "web", "version": "1.0"}
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_properties is True

    def test_missing_components_flag(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_components is True

    def test_metadata_preserved_as_is(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {
                    "type": "application",
                    "name": "My Product",
                    "version": "72.15",
                    "manufacturer": {"name": "ООО «Ромашка»"},
                },
            },
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images_list["metadata"]["component"]["name"] == "My Product"

    def test_version_not_incremented(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 5,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images_list["version"] == 5

    def test_invalid_json_not_dict_raises_error(self) -> None:
        with pytest.raises(SbomParseError, match="JSON object"):
            ImagesListConverter.convert([])

    def test_missing_bom_format_raises_error(self) -> None:
        with pytest.raises(SbomParseError, match="bomFormat"):
            ImagesListConverter.convert({"specVersion": "1.6", "components": []})

    def test_wrong_bom_format_raises_error(self) -> None:
        with pytest.raises(SbomParseError, match="bomFormat"):
            ImagesListConverter.convert({"bomFormat": "SPDX", "components": []})

    def test_empty_name(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_name is True

    def test_empty_version(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_version is True

    def test_empty_properties_array(self) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_properties is True


class TestImagesListConverterAPI:
    @pytest.fixture
    def client(self) -> TestClient:
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as c:
            yield c

    def test_convert_valid_sbom(self, client: TestClient) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "container", "name": "web", "version": "1.0",
                 "properties": [{"name": "GOST:attack_surface", "value": "no"},
                                {"name": "GOST:security_function", "value": "no"}]}
            ],
        }
        response = client.post(
            "/api/v1/convert/images-list",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "was_transformed" in data
        assert "images" in data
        assert "images_list" in data

    def test_convert_without_file_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/convert/images-list")
        assert response.status_code == 422

    def test_convert_invalid_json_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert/images-list",
            files={"file": ("bad.json", b"not json", "application/json")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_json"

    def test_convert_non_cyclonedx_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert/images-list",
            files={"file": ("test.json", json.dumps({"foo": "bar"}), "application/json")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_sbom"

    def test_convert_response_shape(self, client: TestClient) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "container", "name": "web", "version": "1.0",
                 "properties": [{"name": "GOST:attack_surface", "value": "no"},
                                {"name": "GOST:security_function", "value": "no"}]}
            ],
        }
        response = client.post(
            "/api/v1/convert/images-list",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        data = response.json()
        assert isinstance(data["was_transformed"], bool)
        assert isinstance(data["images"], list)
        assert isinstance(data["images_list"], dict)
        if data["images"]:
            img = data["images"][0]
            assert "name" in img
            assert "version" in img
            assert "missing_components" in img
            assert "missing_name" in img
            assert "missing_version" in img
            assert "missing_properties" in img
            assert "duplicates_removed" in img
            assert isinstance(img["duplicates_removed"], int)
