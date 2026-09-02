"""Translate BlendMax material graphs into native Blender shader nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import bpy

from .manifest import ManifestIndex
from .material_graph import (
    ParameterView,
    canonical_name,
    clamp01,
    find_texture_link,
    luminance,
    map_amount,
    map_is_enabled,
    physical_map_is_enabled,
    physical_roughness,
    rgba,
    scalar,
    sorted_sub_materials,
    vray_roughness,
    vray_anisotropy,
    vray_sheen_roughness,
    vray_thin_film,
)
from .models import GraphLink, GraphNode


# V-Ray properties that are intentionally preserved in the manifest but do not
# have a direct equivalent in the Blender Principled BSDF path yet. These are
# deliberately separated from truly unexpected keys so a new exporter field
# still produces an actionable importer warning.
_KNOWN_VRAY_UNMAPPED_PARAMETERS = {
    "anisotropy_axis",
    "anisotropy_channel",
    "anisotropy_derivation",
    "brdf_type",
    "coat_darkening",
    "option_cutoff",
    "option_doublesided",
    "option_glossyfresnel",
    "option_opacitymode",
    "option_openpbrmode",
    "option_tracediffuse",
    "option_tracereflection",
    "option_tracerefraction",
    "reflection_affectalpha",
    "reflection_dimdistance",
    "reflection_dimdistance_falloff",
    "reflection_dimdistance_on",
    "reflection_fresnel",
    "reflection_maxdepth",
    "refraction_affectalpha",
    "refraction_affectshadows",
    "refraction_dispersion",
    "refraction_dispersion_on",
    "refraction_fogbias",
    "refraction_fogcolor",
    "refraction_fogdepth",
    "refraction_fogmult",
    "refraction_fogunitsscale_on",
    "refraction_maxdepth",
    "selfillumination_gi",
    "translucency_amount",
    "translucency_color",
    "translucency_fbcoeff",
    "translucency_multiplier",
    "translucency_on",
    "translucency_scattercoeff",
    "translucency_surfacelighting",
    "translucency_thickness",
}


def _socket(sockets, *names):
    for name in names:
        found = sockets.get(name)
        if found is not None:
            return found
    wanted = {canonical_name(name) for name in names}
    for item in sockets:
        if canonical_name(getattr(item, "name", "")) in wanted:
            return item
        if canonical_name(getattr(item, "identifier", "")) in wanted:
            return item
    return None


def _set_default(node, names: Sequence[str], value) -> None:
    target = _socket(node.inputs, *names)
    if target is not None:
        target.default_value = value


def _configure_alpha(material) -> None:
    if hasattr(material, "surface_render_method"):
        try:
            material.surface_render_method = "DITHERED"
            return
        except (AttributeError, TypeError, ValueError):
            pass
    if hasattr(material, "blend_method"):
        try:
            material.blend_method = "HASHED"
        except (AttributeError, TypeError, ValueError):
            pass


class MaterialBuilder:
    """Build and cache Blender materials for one imported package."""

    def __init__(self, index: ManifestIndex, package_root: Path, warnings: List[str]):
        self.index = index
        self.package_root = Path(package_root)
        self.warnings = warnings
        self._warned: Set[str] = set()
        self._material_cache: Dict[str, object] = {}
        self._image_cache: Dict[Tuple[str, str], object] = {}
        self.created_materials: List[object] = []
        self.created_images: List[object] = []

    def _warn(self, message: str) -> None:
        if message not in self._warned:
            self._warned.add(message)
            self.warnings.append(message)

    def materials_for_assignment(self, ref: Optional[str]) -> Tuple[object, ...]:
        if not ref:
            return ()
        node = self.index.node(ref)
        if node is None:
            self._warn("Material graph reference {0} is missing.".format(ref))
            return (self._placeholder(ref, "Missing material"),)
        if canonical_name(node.class_name) != "multimaterial":
            return (self.build_material(ref),)

        links = sorted_sub_materials(node)
        if not links:
            return (self._placeholder(ref, node.name),)
        by_index = {link.index: link for link in links if link.index > 0}
        maximum = max(by_index, default=1)
        materials = []
        for slot_index in range(1, maximum + 1):
            link = by_index.get(slot_index)
            if link is None:
                materials.append(
                    self._placeholder(
                        "{0}:slot:{1}".format(ref, slot_index),
                        "{0} slot {1}".format(node.name, slot_index),
                    )
                )
            else:
                materials.append(self.build_material(link.ref))
        return tuple(materials)

    def build_material(self, ref: str):
        cached = self._material_cache.get(ref)
        if cached is not None:
            return cached

        graph_node = self.index.node(ref)
        name = graph_node.name if graph_node is not None else ref
        material = bpy.data.materials.new(name=name or ref)
        self._material_cache[ref] = material
        self.created_materials.append(material)
        output = self._build_shader(
            material.node_tree,
            ref,
            material,
            (),
            0.0,
            0.0,
        )
        if output is None:
            output = self._placeholder_shader(material.node_tree, name or ref)
        output_node = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
        output_node.location = (280.0, 0.0)
        material.node_tree.links.new(output, output_node.inputs["Surface"])
        return material

    def _build_shader(
        self,
        tree,
        ref: str,
        material,
        stack: Tuple[str, ...],
        x: float,
        y: float,
    ):
        if ref in stack:
            self._warn("Material graph cycle stopped at {0}.".format(ref))
            return None
        graph_node = self.index.node(ref)
        if graph_node is None:
            self._warn("Material graph reference {0} is missing.".format(ref))
            return None
        class_name = canonical_name(graph_node.class_name)
        next_stack = stack + (ref,)
        if class_name == "vraymtl":
            return self._build_vray_mtl(tree, graph_node, material, next_stack, x, y)
        if class_name == "multimaterial":
            return self._build_multimaterial(tree, graph_node, material, next_stack, x, y)
        self._warn(
            "Material {0} uses unsupported class {1}.".format(
                graph_node.name, graph_node.class_name
            )
        )
        return None

    def _placeholder_shader(self, tree, name):
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.label = name
        return bsdf.outputs[0]

    def _build_multimaterial(self, tree, graph_node, material, stack, x, y):
        links = sorted_sub_materials(graph_node)
        if not links:
            return None
        first = links[0]
        return self._build_shader(tree, first.ref, material, stack, x, y)

    def _mix_color(self, tree, texture, base, factor, x, y, label):
        mix = tree.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.label = label
        mix.location = (x, y)
        factor_input = _socket(mix.inputs, "Factor")
        if factor_input is not None:
            factor_input.default_value = clamp01(factor)
        a_input = _socket(mix.inputs, "A", "Color1")
        b_input = _socket(mix.inputs, "B", "Color2")
        if a_input is not None:
            a_input.default_value = base
        if b_input is not None:
            b_input.default_value = base
        if a_input is not None:
            tree.links.new(texture, a_input)
        return _socket(mix.outputs, "Result", "Result Color")

    def _mix_value(self, tree, texture, base, factor, x, y, label):
        mix = tree.nodes.new("ShaderNodeMix")
        mix.data_type = "FLOAT"
        mix.label = label
        mix.location = (x, y)
        factor_input = _socket(mix.inputs, "Factor")
        if factor_input is not None:
            factor_input.default_value = clamp01(factor)
        a_input = _socket(mix.inputs, "A", "Value1")
        b_input = _socket(mix.inputs, "B", "Value2")
        if a_input is not None:
            tree.links.new(texture, a_input)
        if b_input is not None:
            b_input.default_value = base
        return _socket(mix.outputs, "Result", "Result")

    def _invert_value(self, tree, texture, x, y):
        node = tree.nodes.new("ShaderNodeMath")
        node.operation = "SUBTRACT"
        node.inputs[0].default_value = 1.0
        node.location = (x, y)
        tree.links.new(texture, node.inputs[1])
        return node.outputs[0]

    def _to_value(self, tree, socket, x, y):
        if getattr(socket, "type", None) in {"VALUE", "INT", "BOOLEAN"}:
            return socket
        node = tree.nodes.new("ShaderNodeRGBToBW")
        node.location = (x, y)
        tree.links.new(socket, node.inputs[0])
        return node.outputs[0]

    def _normal_output(self, tree, ref, strength, stack, x, y):
        texture = self._texture_output(tree, ref, "normal", stack, x, y)
        if texture is None:
            return None
        normal = tree.nodes.new("ShaderNodeNormalMap")
        normal.location = (x + 180, y)
        _set_default(normal, ("Strength",), strength)
        tree.links.new(texture, normal.inputs[1])
        return normal.outputs[0]

    def _texture_path(self, ref):
        graph_node = self.index.node(ref)
        if graph_node is None:
            return None
        path = graph_node.parameters.get("filename")
        if path:
            candidate = self.package_root / path
            if candidate.exists():
                return candidate
            return Path(path)
        return None

    def _load_image(self, path, colorspace):
        key = (str(path), colorspace)
        cached = self._image_cache.get(key)
        if cached is not None:
            return cached
        try:
            image = bpy.data.images.load(str(path), check_existing=True)
        except Exception:
            self._warn("Packaged image for texture graph node {0} is unavailable.".format(path))
            return None
        self._image_cache[key] = image
        self.created_images.append(image)
        try:
            image.colorspace_settings.name = colorspace
        except Exception:
            pass
        return image

    def _build_vray_mtl(
        self,
        tree,
        graph_node: GraphNode,
        material,
        stack: Tuple[str, ...],
        x: float,
        y: float,
    ):
        parameters = ParameterView(graph_node.parameters)
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.label = graph_node.name
        bsdf.location = (x, y)

        diffuse = rgba(parameters.get("Diffuse"), (0.8, 0.8, 0.8, 1.0))
        reflection = rgba(parameters.get("Reflection"), (0.5, 0.5, 0.5, 1.0))
        refraction = rgba(parameters.get("Refraction"), (0.0, 0.0, 0.0, 1.0))
        emission = rgba(parameters.get("selfIllumination"), (0.0, 0.0, 0.0, 1.0))

        _set_default(bsdf, ("Base Color",), diffuse)
        _set_default(bsdf, ("Metallic",), clamp01(scalar(parameters, "reflection_metalness", 0.0)))
        _set_default(bsdf, ("Roughness",), vray_roughness(parameters))
        _set_default(
            bsdf,
            ("IOR",),
            max(1.0, scalar(parameters, "reflection_IOR", scalar(parameters, "refraction_ior", 1.5))),
        )
        _set_default(
            bsdf,
            ("Specular IOR Level", "Specular"),
            clamp01(luminance(reflection) * scalar(parameters, "reflection_weight", 1.0)),
        )
        _set_default(bsdf, ("Transmission Weight", "Transmission"), luminance(refraction))
        _set_default(bsdf, ("Alpha",), 1.0)
        _set_default(bsdf, ("Emission Color", "Emission"), emission)
        _set_default(
            bsdf,
            ("Emission Strength",),
            max(0.0, scalar(parameters, "selfIllumination_multiplier", 1.0)),
        )
        _set_default(bsdf, ("Coat Weight", "Coat"), clamp01(scalar(parameters, "coat_amount", 0.0)))
        _set_default(bsdf, ("Coat Roughness",), 1.0 - clamp01(scalar(parameters, "coat_glossiness", 1.0)))
        _set_default(bsdf, ("Coat IOR",), max(1.0, scalar(parameters, "coat_ior", 1.5)))
        _set_default(
            bsdf,
            ("Coat Tint",),
            rgba(parameters.get("coat_color"), (1.0, 1.0, 1.0, 1.0)),
        )
        _set_default(
            bsdf,
            ("Diffuse Roughness",),
            clamp01(scalar(parameters, "diffuse_roughness", 0.0)),
        )
        _set_default(
            bsdf,
            ("Thin Wall",),
            bool(parameters.get("refraction_thinwalled", False)),
        )

        anisotropic, anisotropic_rotation = vray_anisotropy(parameters)
        _set_default(bsdf, ("Anisotropic IOR Level", "Anisotropic"), anisotropic)
        _set_default(bsdf, ("Anisotropic Rotation",), anisotropic_rotation)

        sheen_color = rgba(parameters.get("sheen_color"), (0.0, 0.0, 0.0, 1.0))
        _set_default(bsdf, ("Sheen Weight", "Sheen"), luminance(sheen_color))
        _set_default(bsdf, ("Sheen Roughness",), vray_sheen_roughness(parameters))
        _set_default(bsdf, ("Sheen Tint",), sheen_color)

        thin_film_ior, thin_film_thickness = vray_thin_film(parameters)
        _set_default(bsdf, ("Thin Film IOR",), thin_film_ior)
        _set_default(bsdf, ("Thin Film Thickness",), thin_film_thickness)

        reflection_ior = scalar(parameters, "reflection_IOR", 1.5)
        refraction_ior = scalar(parameters, "refraction_ior", reflection_ior)
        if (
            not bool(parameters.get("reflection_lockIOR", True))
            and abs(reflection_ior - refraction_ior) > 0.0001
        ):
            self._warn(
                "{0} has separate reflection/refraction IOR values; Blender's "
                "Principled shader uses the reflection IOR while the original "
                "values remain in the packed manifest.".format(graph_node.name)
            )

        refraction_glossiness = parameters.get("refraction_glossiness")
        if refraction_glossiness is not None:
            try:
                refraction_roughness = 1.0 - clamp01(float(refraction_glossiness))
            except (TypeError, ValueError):
                refraction_roughness = None
            if (
                refraction_roughness is not None
                and luminance(refraction) > 0.0
                and abs(refraction_roughness - vray_roughness(parameters)) > 0.0001
            ):
                self._warn(
                    "{0} has separate reflection and refraction glossiness values; "
                    "Blender's Principled shader uses a single roughness for both, "
                    "so the refraction roughness is approximated.".format(
                        graph_node.name
                    )
                )

        diffuse_link = find_texture_link(graph_node, "Diffuse")
        if diffuse_link and map_is_enabled(parameters, diffuse_link.slot):
            texture = self._texture_output(tree, diffuse_link.ref, "color", stack, x - 900, y + 420)
            if texture is not None:
                mixed = self._mix_color(
                    tree,
                    texture,
                    diffuse,
                    map_amount(parameters, diffuse_link.slot),
                    x - 520,
                    y + 360,
                    "Diffuse map",
                )
                tree.links.new(mixed, _socket(bsdf.inputs, "Base Color"))

        reflection_link = find_texture_link(graph_node, "Reflection")
        if reflection_link and map_is_enabled(parameters, reflection_link.slot):
            texture = self._texture_output(tree, reflection_link.ref, "data", stack, x - 900, y + 220)
            target = _socket(bsdf.inputs, "Specular IOR Level", "Specular")
            if texture is not None and target is not None:
                value = self._to_value(tree, texture, x - 680, y + 220)
                mixed = self._mix_value(
                    tree,
                    value,
                    luminance(reflection),
                    map_amount(parameters, reflection_link.slot),
                    x - 500,
                    y + 220,
                    "Reflection map",
                )
                tree.links.new(mixed, target)

        roughness_link = find_texture_link(
            graph_node, "Reflection roughness", "Reflection glossiness"
        )
        if roughness_link and map_is_enabled(parameters, roughness_link.slot):
            texture = self._texture_output(tree, roughness_link.ref, "data", stack, x - 900, y + 40)
            if texture is not None:
                value = self._to_value(tree, texture, x - 700, y + 40)
                if canonical_name(roughness_link.slot) == "reflectionglossiness":
                    value = self._invert_value(tree, value, x - 540, y + 40)
                mixed = self._mix_value(
                    tree,
                    value,
                    vray_roughness(parameters),
                    map_amount(parameters, roughness_link.slot),
                    x - 360,
                    y + 40,
                    "Reflection roughness map",
                )
                tree.links.new(mixed, _socket(bsdf.inputs, "Roughness"))

        metalness_link = find_texture_link(graph_node, "Metalness")
        if metalness_link and map_is_enabled(parameters, metalness_link.slot):
            texture = self._texture_output(tree, metalness_link.ref, "data", stack, x - 900, y - 120)
            if texture is not None:
                value = self._to_value(tree, texture, x - 700, y - 120)
                mixed = self._mix_value(
                    tree,
                    value,
                    clamp01(scalar(parameters, "reflection_metalness", 0.0)),
                    map_amount(parameters, metalness_link.slot),
                    x - 500,
                    y - 120,
                    "Metalness map",
                )
                tree.links.new(mixed, _socket(bsdf.inputs, "Metallic"))

        refraction_link = find_texture_link(graph_node, "Refraction")
        transmission_input = _socket(bsdf.inputs, "Transmission Weight", "Transmission")
        if (
            refraction_link
            and transmission_input is not None
            and map_is_enabled(parameters, refraction_link.slot)
        ):
            texture = self._texture_output(tree, refraction_link.ref, "color", stack, x - 900, y - 280)
            if texture is not None:
                value = self._to_value(tree, texture, x - 700, y - 280)
                mixed = self._mix_value(
                    tree,
                    value,
                    luminance(refraction),
                    map_amount(parameters, refraction_link.slot),
                    x - 500,
                    y - 280,
                    "Refraction map",
                )
                tree.links.new(mixed, transmission_input)

        opacity_link = find_texture_link(graph_node, "Opacity")
        alpha_input = _socket(bsdf.inputs, "Alpha")
        if opacity_link and alpha_input is not None and map_is_enabled(parameters, opacity_link.slot):
            texture = self._texture_output(tree, opacity_link.ref, "data", stack, x - 900, y - 440)
            if texture is not None:
                value = self._to_value(tree, texture, x - 700, y - 440)
                mixed = self._mix_value(
                    tree,
                    value,
                    1.0,
                    map_amount(parameters, opacity_link.slot),
                    x - 500,
                    y - 440,
                    "Opacity map",
                )
                tree.links.new(mixed, alpha_input)
                _configure_alpha(material)

        emission_link = find_texture_link(graph_node, "Self-illumination", "Self illumination")
        emission_input = _socket(bsdf.inputs, "Emission Color", "Emission")
        if (
            emission_link
            and emission_input is not None
            and map_is_enabled(parameters, emission_link.slot)
        ):
            texture = self._texture_output(tree, emission_link.ref, "color", stack, x - 900, y - 600)
            if texture is not None:
                mixed = self._mix_color(
                    tree,
                    texture,
                    emission,
                    map_amount(parameters, emission_link.slot),
                    x - 520,
                    y - 600,
                    "Self-illumination map",
                )
                tree.links.new(mixed, emission_input)

        bump_link = find_texture_link(graph_node, "Bump")
        normal_input = _socket(bsdf.inputs, "Normal")
        if bump_link and normal_input is not None and map_is_enabled(parameters, bump_link.slot):
            normal = self._normal_output(
                tree,
                bump_link.ref,
                max(0.0, scalar(parameters, "texmap_bump_multiplier", 100.0) / 100.0),
                stack,
                x - 660,
                y - 780,
            )
            if normal is not None:
                tree.links.new(normal, normal_input)

        for key in parameters.unmapped_keys():
            if key.startswith("texmap"):
                continue
            if key.casefold() in _KNOWN_VRAY_UNMAPPED_PARAMETERS:
                continue
            self._warn(
                "VRayMtl parameter '{0}' has no Blender mapping yet; its value "
                "remains in the stored manifest.".format(key)
            )

        return bsdf.outputs[0]

    def _texture_output(
        self,
        tree,
        ref: str,
        role: str,
        stack: Tuple[str, ...],
        x: float,
        y: float,
    ):
        if ref in stack:
            self._warn("Texture graph cycle stopped at {0}.".format(ref))
            return None
        graph_node = self.index.node(ref)
        if graph_node is None:
            self._warn("Texture graph reference {0} is missing.".format(ref))
            return None
        class_name = canonical_name(graph_node.class_name)
        next_stack = stack + (ref,)

        if class_name in {"bitmaptexture", "vraybitmap"}:
            path = self._texture_path(ref)
            if path is None:
                return None
            image = self._load_image(path, "Non-Color" if role in {"data", "normal"} else "sRGB")
            texture = tree.nodes.new("ShaderNodeTexImage")
            texture.label = graph_node.name
            texture.image = image
            texture.location = (x, y)
            return _socket(texture.outputs, "Color")

        if class_name == "normalbump":
            child = find_texture_link(graph_node, "Normal", "Bump")
            if child is None and graph_node.sub_textures:
                child = graph_node.sub_textures[0]
            return (
                self._texture_output(tree, child.ref, role, next_stack, x, y)
                if child is not None
                else None
            )

        if class_name == "vraycolor":
            parameters = ParameterView(graph_node.parameters)
            color = list(rgba(parameters.get("color"), (0.5, 0.5, 0.5, 1.0)))
            multiplier = max(0.0, scalar(parameters, "rgb_multiplier", 1.0))
            color[:3] = [min(1.0, value * multiplier) for value in color[:3]]
            rgb_node = tree.nodes.new("ShaderNodeRGB")
            rgb_node.label = graph_node.name
            rgb_node.location = (x, y)
            rgb_node.outputs[0].default_value = color
            return rgb_node.outputs[0]

        if class_name == "noise":
            parameters = ParameterView(graph_node.parameters)
            noise = tree.nodes.new("ShaderNodeTexNoise")
            noise.label = graph_node.name
            noise.location = (x, y)
            units_per_meter = scalar(
                self.index.manifest.raw.get("source", {}),
                "system_units_per_meter",
                1.0,
            )
            size = max(0.000001, scalar(parameters, "size", 1.0))
            _set_default(noise, ("Scale",), max(0.000001, units_per_meter / size))
            _set_default(noise, ("Detail",), max(0.0, scalar(parameters, "levels", 2.0)))
            ramp = tree.nodes.new("ShaderNodeValToRGB")
            ramp.location = (x + 190, y)
            ramp.color_ramp.elements[0].color = rgba(
                parameters.get("color1"), (0.0, 0.0, 0.0, 1.0)
            )
            ramp.color_ramp.elements[1].color = rgba(
                parameters.get("color2"), (1.0, 1.0, 1.0, 1.0)
            )
            tree.links.new(_socket(noise.outputs, "Fac"), ramp.inputs[0])
            return ramp.outputs[0]

        self._warn(
            "Texture {0} uses unsupported class {1}.".format(
                graph_node.name, graph_node.class_name
            )
        )
        return None
