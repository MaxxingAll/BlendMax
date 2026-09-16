"""BlendMax Blender importer extension entry point.

The module deliberately avoids importing :mod:`bpy` until Blender calls
``register``.  This keeps the package's manifest and archive code testable with
ordinary Python.
"""

from __future__ import annotations


__version__ = "0.1.9"

# bl_info is legacy add-on metadata: Blender 4.2+ extensions read
# blendmax_blender/blender_manifest.toml instead, and nothing in this
# repository reads bl_info. It is kept in step with __version__ by hand --
# the 0.1.9 bump missed it -- and tests/test_blender_extension_build.py now
# fails if any of the three version declarations disagree.
bl_info = {
    "name": "BlendMax Importer",
    "author": "MaxxingAll",
    "version": (0, 1, 9),
    "blender": (4, 2, 0),
    "location": "File > Import > BlendMax Asset (.blendmax)",
    "description": "Import BlendMax assets exported from Autodesk 3ds Max",
    "category": "Import-Export",
}


def register() -> None:
    from . import addon

    addon.register()


def unregister() -> None:
    from . import addon

    addon.unregister()
