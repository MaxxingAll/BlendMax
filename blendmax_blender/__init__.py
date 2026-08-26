"""BlendMax Blender importer extension entry point.

The module deliberately avoids importing :mod:`bpy` until Blender calls
``register``.  This keeps the package's manifest and archive code testable with
ordinary Python.
"""

from __future__ import annotations


__version__ = "0.1.4"

bl_info = {
    "name": "BlendMax Importer",
    "author": "MaxxingAll",
    "version": (0, 1, 4),
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
