from __future__ import annotations

import unittest

from blendmax_blender import __version__


class BlenderVersionMetadataTests(unittest.TestCase):
    def test_importer_version_is_0_1_7(self):
        self.assertEqual(__version__, "0.1.7")


if __name__ == "__main__":
    unittest.main()
