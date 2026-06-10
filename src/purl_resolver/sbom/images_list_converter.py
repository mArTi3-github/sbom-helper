from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImageInfo:
    name: str | None
    version: str | None
    missing_components: bool = False
    missing_name: bool = False
    missing_version: bool = False
    missing_properties: bool = False


@dataclass
class ImagesListConversionResult:
    images_list: dict
    was_transformed: bool
    images: list[ImageInfo] = field(default_factory=list)


class ImagesListConverter:
    @classmethod
    def convert(cls, sbom_data: object) -> ImagesListConversionResult:
        data = cls._validate(sbom_data)
        top_components = data.get("components", [])
        if cls._all_are_containers(top_components):
            images = cls._build_image_infos(top_components)
            return ImagesListConversionResult(
                images_list=data, was_transformed=False, images=images
            )

        all_containers = cls._collect_containers(data)
        result_sbom = dict(data)
        result_sbom["components"] = all_containers
        images = cls._build_image_infos(all_containers)
        return ImagesListConversionResult(
            images_list=result_sbom, was_transformed=True, images=images
        )

    @classmethod
    def _validate(cls, data: object) -> dict:
        from .parser import CycloneDXParser

        return CycloneDXParser.parse(data)

    @classmethod
    def _all_are_containers(cls, components: list) -> bool:
        if not components:
            return False
        return all(
            isinstance(c, dict) and c.get("type") == "container" for c in components
        )

    @classmethod
    def _collect_containers(cls, data: dict) -> list[dict]:
        containers: list[dict] = []
        cls._walk_and_collect(data, containers)
        return containers

    @classmethod
    def _walk_and_collect(cls, obj: object, containers: list[dict]) -> None:
        if isinstance(obj, dict):
            if obj.get("type") == "container":
                containers.append(obj)
                return
            for value in obj.values():
                cls._walk_and_collect(value, containers)
        elif isinstance(obj, list):
            for item in obj:
                cls._walk_and_collect(item, containers)

    @classmethod
    def _build_image_infos(cls, components: list[dict]) -> list[ImageInfo]:
        images: list[ImageInfo] = []
        for comp in components:
            name = comp.get("name")
            version = comp.get("version")
            info = ImageInfo(
                name=name if isinstance(name, str) and name else None,
                version=version if isinstance(version, str) and version else None,
                missing_name=not (isinstance(name, str) and name),
                missing_version=not (isinstance(version, str) and version),
                missing_components=not cls._has_subcomponents(comp),
                missing_properties=not cls._has_properties(comp),
            )
            images.append(info)
        return images

    @classmethod
    def _has_subcomponents(cls, comp: dict) -> bool:
        children = comp.get("components")
        return isinstance(children, list) and len(children) > 0

    @classmethod
    def _has_properties(cls, comp: dict) -> bool:
        props = comp.get("properties")
        return isinstance(props, list) and len(props) > 0
