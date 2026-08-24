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
    duplicates_removed: int = 0


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
            containers = top_components
            was_transformed = False
        else:
            containers = cls._collect_containers(data)
            was_transformed = True

        deduped, dup_counts = cls._deduplicate_containers(containers)

        if dup_counts:
            was_transformed = True

        images = cls._build_image_infos(deduped, dup_counts)
        result_sbom = dict(data)
        result_sbom["components"] = deduped

        return ImagesListConversionResult(
            images_list=result_sbom, was_transformed=was_transformed, images=images
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
    def _deduplicate_containers(cls, containers: list[dict]) -> tuple[list[dict], dict[str, int]]:
        seen: set[str] = set()
        dup_counts: dict[str, int] = {}
        deduped: list[dict] = []
        for comp in containers:
            purl = comp.get("purl")
            if isinstance(purl, str):
                if purl in seen:
                    dup_counts[purl] = dup_counts.get(purl, 0) + 1
                    continue
                seen.add(purl)
            deduped.append(comp)
        return deduped, dup_counts

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
    def _build_image_infos(
        cls, components: list[dict], dup_counts: dict[str, int] | None = None
    ) -> list[ImageInfo]:
        if dup_counts is None:
            dup_counts = {}
        images: list[ImageInfo] = []
        for comp in components:
            name = comp.get("name")
            version = comp.get("version")
            purl = comp.get("purl")
            dr = dup_counts.get(purl, 0) if isinstance(purl, str) else 0
            info = ImageInfo(
                name=name if isinstance(name, str) and name else None,
                version=version if isinstance(version, str) and version else None,
                missing_name=not (isinstance(name, str) and name),
                missing_version=not (isinstance(version, str) and version),
                missing_components=not cls._has_subcomponents(comp),
                missing_properties=not cls._has_properties(comp),
                duplicates_removed=dr,
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
