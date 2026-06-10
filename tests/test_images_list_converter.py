from __future__ import annotations

import pytest

from purl_resolver.sbom.images_list_converter import ImagesListConverter
from purl_resolver.sbom.parser import SbomParseError


class TestImagesListConverter:
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