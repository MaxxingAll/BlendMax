import unittest

from blendmax_max import __version__


class VersionMetadataTests(unittest.TestCase):
    def test_max_exporter_version_is_alpha_4_3_0(self):
        self.assertEqual(__version__, "0.1.0-alpha.4.3.0")


if __name__ == "__main__":
    unittest.main()
