"""Focused tests for the shared archive policy.

The policy module is the single source of truth for the rules the Blender
``.blendmax`` importer and the 3ds Max update-ZIP installer both apply. These
tests pin the rules themselves; the two consumers' own behaviour (messages,
exception types, extraction) is pinned in their own test files.
"""

from __future__ import annotations

import unittest
import zipfile

import blendmax_archive_policy as policy


def symlink_info(name):
    info = zipfile.ZipInfo(name)
    info.external_attr = (0o120777) << 16
    return info


def file_info(name, size=0):
    info = zipfile.ZipInfo(name)
    info.external_attr = 0o100644 << 16
    info.file_size = size
    return info


class WindowsHazardTests(unittest.TestCase):
    def test_ordinary_components_are_not_hazards(self):
        for part in ("wood.png", "readme", "a", "file.tar.gz", "with-dash",
                     "with_underscore", "UPPER.TXT"):
            self.assertEqual(policy.windows_hazard(part), "", part)

    def test_reserved_device_names(self):
        for part in ("CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"):
            self.assertTrue(policy.windows_hazard(part), part)

    def test_reserved_names_are_case_insensitive(self):
        for part in ("con", "Con", "cOn", "nul", "Nul"):
            self.assertTrue(policy.windows_hazard(part), part)

    def test_reserved_names_with_extensions(self):
        # "CON.txt" is still the console: the check is on the stem.
        for part in ("CON.txt", "NUL.log", "aux.dat", "PRN.old.txt"):
            self.assertTrue(policy.windows_hazard(part), part)

    def test_serial_and_parallel_device_names(self):
        for index in range(1, 10):
            self.assertTrue(policy.windows_hazard("COM{0}".format(index)))
            self.assertTrue(policy.windows_hazard("LPT{0}".format(index)))

    def test_superscript_device_names_from_the_documented_set(self):
        # Microsoft names exactly the three ISO/IEC 8859-1 superscripts.
        for part in ("COM\u00b9", "COM\u00b2", "COM\u00b3",
                     "LPT\u00b9", "LPT\u00b2", "LPT\u00b3",
                     "com\u00b9.txt", "LPT\u00b2.log"):
            self.assertTrue(policy.windows_hazard(part), part)

    def test_accepted_boundaries_are_not_hazards(self):
        """The boundaries PR #38 deliberately left permitted must stay permitted."""
        for part in ("COM0", "LPT0", "COM10", "LPT10",
                     "COM\u2074", "COM\u2075",  # Unicode superscripts, not documented
                     "CLOCK$", "CONS", "NULL", "CONSOLE"):
            self.assertEqual(policy.windows_hazard(part), "", part)

    def test_trailing_dot(self):
        self.assertTrue(policy.windows_hazard("name."))
        self.assertTrue(policy.windows_hazard("name.."))

    def test_trailing_space(self):
        self.assertTrue(policy.windows_hazard("name "))

    def test_interior_dots_and_spaces_are_fine(self):
        for part in ("na.me", "a b", "a.b.c"):
            self.assertEqual(policy.windows_hazard(part), "", part)

    def test_colon(self):
        for part in ("a:b", "C:", "file.txt:ads"):
            self.assertTrue(policy.windows_hazard(part), part)

    def test_reserved_name_set_is_the_documented_thirty(self):
        base = {"con", "prn", "aux", "nul", "conin$", "conout$"}
        com = {"com{0}".format(i) for i in range(1, 10)}
        lpt = {"lpt{0}".format(i) for i in range(1, 10)}
        superscripts = {"com\u00b9", "com\u00b2", "com\u00b3",
                        "lpt\u00b9", "lpt\u00b2", "lpt\u00b3"}
        self.assertEqual(
            policy.WINDOWS_RESERVED_NAMES, base | com | lpt | superscripts
        )
        self.assertEqual(len(policy.WINDOWS_RESERVED_NAMES), 30)
        self.assertNotIn("clock$", policy.WINDOWS_RESERVED_NAMES)


class CheckMemberPathTests(unittest.TestCase):
    def test_ordinary_paths_pass_through_normalized(self):
        self.assertEqual(policy.check_member_path("textures/wood.png"),
                         policy.MemberPath("textures/wood.png", ""))
        self.assertEqual(policy.check_member_path("a/b/c.txt"),
                         policy.MemberPath("a/b/c.txt", ""))
        self.assertEqual(policy.check_member_path("readme.md"),
                         policy.MemberPath("readme.md", ""))

    def test_backslashes_are_treated_as_separators(self):
        # An archive written on Windows may use them; a consumer that only
        # understands forward slashes would miss a hazard.
        self.assertEqual(policy.check_member_path("dir\\file.txt"),
                         policy.MemberPath("dir/file.txt", ""))
        result = policy.check_member_path("dir\\NUL.txt")
        self.assertEqual(result.reason, policy.REASON_COMPONENT)
        self.assertEqual(result.part, "NUL.txt")

    def test_absolute_paths_are_rejected(self):
        for name in ("/etc/passwd", "/absolute.txt"):
            self.assertEqual(policy.check_member_path(name).reason,
                             policy.REASON_ABSOLUTE, name)

    def test_traversal_forms_are_rejected(self):
        for name in ("../escape.txt", "a/../../escape.txt", "..\\escape.txt",
                     "dir/../sibling.txt", ".."):
            self.assertEqual(policy.check_member_path(name).reason,
                             policy.REASON_TRAVERSAL, name)

    def test_empty_and_nul_names_are_rejected(self):
        for name in ("", "\x00", "a\x00b"):
            self.assertEqual(policy.check_member_path(name).reason,
                             policy.REASON_EMPTY, repr(name))

    def test_dot_only_paths_are_rejected(self):
        self.assertEqual(policy.check_member_path(".").reason, policy.REASON_EMPTY)

    def test_reserved_names_in_an_intermediate_directory_are_rejected(self):
        """A hazard in a middle component is extracted just the same."""
        for name in ("dir/CON/file.txt", "NUL/file.txt", "a/b/LPT1.txt/c.txt"):
            result = policy.check_member_path(name)
            self.assertEqual(result.reason, policy.REASON_COMPONENT, name)
            self.assertTrue(result.part, name)

    def test_component_hazards_are_reported_with_their_reason(self):
        result = policy.check_member_path("dir/CON/file.txt")
        self.assertEqual(result.part, "CON")
        self.assertEqual(result.hazard, "reserved Windows device name")

        result = policy.check_member_path("a/b:c")
        self.assertEqual(result.part, "b:c")
        self.assertIn("colon", result.hazard)

        result = policy.check_member_path("name.")
        self.assertEqual(result.hazard, "trailing dot or space")

    def test_a_trailing_dot_directory_component_is_rejected(self):
        self.assertEqual(policy.check_member_path("dir./file.txt").reason,
                         policy.REASON_COMPONENT)


class SymlinkAndLimitTests(unittest.TestCase):
    def test_symlink_entries_are_detected(self):
        self.assertTrue(policy.is_symlink(symlink_info("link")))

    def test_regular_entries_are_not_symlinks(self):
        self.assertFalse(policy.is_symlink(file_info("file.txt")))

    def test_directory_entries_are_not_symlinks(self):
        info = zipfile.ZipInfo("dir/")
        info.external_attr = (0o040755) << 16
        self.assertFalse(policy.is_symlink(info))

    def test_declared_bytes_sum_includes_every_entry(self):
        infos = [file_info("a", 10), file_info("b", 32), file_info("dir/", 0)]
        self.assertEqual(policy.declared_uncompressed_bytes(infos), 42)

    def test_declared_bytes_of_an_empty_archive(self):
        self.assertEqual(policy.declared_uncompressed_bytes([]), 0)

    def test_limits_keep_their_documented_values(self):
        self.assertEqual(policy.MAX_ARCHIVE_ENTRIES, 2048)
        self.assertEqual(policy.MAX_UNCOMPRESSED_BYTES, 16 * 1024 * 1024 * 1024)


class DuplicatePolicyTests(unittest.TestCase):
    def test_folding_is_case_insensitive(self):
        self.assertEqual(policy.folded_path("Readme.md"),
                         policy.folded_path("README.MD"))
        self.assertEqual(policy.folded_path("a/B.txt"), policy.folded_path("A/b.TXT"))

    def test_distinct_paths_do_not_fold_together(self):
        self.assertNotEqual(policy.folded_path("a.txt"), policy.folded_path("b.txt"))
        self.assertNotEqual(policy.folded_path("a/b.txt"),
                            policy.folded_path("a\\b.txt"))

    def test_path_separators_are_not_folded_away(self):
        # "a/b" and "a_b" are different files and must not collide.
        self.assertNotEqual(policy.folded_path("a/b"), policy.folded_path("a_b"))


if __name__ == "__main__":
    unittest.main()
