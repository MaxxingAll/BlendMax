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

    def test_reserved_names_with_a_space_before_the_extension(self):
        """Windows trims trailing spaces from a name before device matching.

        "AUX .txt" therefore resolves the same way "AUX" does. Note that this
        is a conservative extension rather than a demonstrated hazard: on the
        Windows host used to develop this, cmd.exe creates an ordinary file for
        "AUX .txt", and for "NUL.txt" too. Rejecting them costs nothing a real
        archive contains.
        """
        for part in ("AUX .txt", "NUL .txt", "CON .txt", "PRN .txt",
                     "COM1 .txt", "LPT1 .txt", "aux .log", "NUL ."):
            self.assertTrue(policy.windows_hazard(part), part)

    def test_a_space_before_the_extension_is_not_a_hazard_by_itself(self):
        for part in ("ordinary .txt", "my file .txt", "notes .md"):
            self.assertEqual(policy.windows_hazard(part), "", part)

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


class ByteBudgetTests(unittest.TestCase):
    """#50: cumulative decompressed-byte accounting, exception-neutral.

    ByteBudget is the shared half of the actual-byte limit: it decides whether
    a chunk fits, and each consumer keeps its own exception type and wording.
    """

    def test_budget_starts_empty_and_keeps_its_limit(self):
        budget = policy.ByteBudget(100)
        self.assertEqual(budget.limit, 100)
        self.assertEqual(budget.used, 0)

    def test_reserve_accepts_until_the_limit(self):
        budget = policy.ByteBudget(100)
        self.assertTrue(budget.reserve(60))
        self.assertTrue(budget.reserve(40))
        self.assertEqual(budget.used, 100)

    def test_reserve_accepts_a_chunk_landing_exactly_on_the_limit(self):
        # The comparison is "> limit", not ">= limit": an archive at exactly
        # the limit is valid.
        budget = policy.ByteBudget(100)
        self.assertTrue(budget.reserve(100))
        self.assertFalse(budget.reserve(1))

    def test_reserve_refuses_oversized_chunk_and_changes_nothing(self):
        budget = policy.ByteBudget(100)
        self.assertTrue(budget.reserve(90))
        self.assertFalse(budget.reserve(11))
        self.assertEqual(budget.used, 90)

    def test_used_never_exceeds_the_limit_under_any_sequence(self):
        budget = policy.ByteBudget(10)
        for size in (3, 3, 3, 3, 1, 1, 5, 10):
            budget.reserve(size)
        self.assertLessEqual(budget.used, budget.limit)

    def test_zero_limit_accepts_only_zero(self):
        budget = policy.ByteBudget(0)
        self.assertTrue(budget.reserve(0))
        self.assertFalse(budget.reserve(1))


class PathCollisionTests(unittest.TestCase):
    """#50: a file path may not also be a directory for another entry.

    Entries are (cleaned_path, is_directory) pairs in archive order, which is
    what both consumers collect while they validate members. The helper is
    deliberately stricter than nothing but weaker than every path rule: exact
    duplicate names are the duplicate checks' concern, not this one's.
    """

    def collision(self, entries):
        return policy.find_path_collision(entries)

    # -- the must-reject shapes -------------------------------------------

    def test_file_followed_by_a_path_beneath_it_collides(self):
        result = self.collision([("a", False), ("a/b", False)])
        self.assertEqual(result, policy.PathCollision("a", "a/b"))

    def test_deep_file_prefix_collides(self):
        result = self.collision([("a/b", False), ("a/b/c", False)])
        self.assertEqual(result, policy.PathCollision("a/b", "a/b/c"))

    def test_child_listed_before_the_file_still_collides(self):
        result = self.collision([("a/b", False), ("a", False)])
        self.assertEqual(result, policy.PathCollision("a", "a/b"))

    def test_file_against_an_explicit_directory_of_the_same_path(self):
        result = self.collision([("a", True), ("a", False)])
        self.assertEqual(result, policy.PathCollision("a", "a"))

    def test_file_prefix_of_an_explicit_directory_entry(self):
        result = self.collision([("a", False), ("a/b", True), ("a/b/c", False)])
        self.assertEqual(result, policy.PathCollision("a", "a/b"))

    # -- the must-stay-valid shapes ---------------------------------------

    def test_directory_entry_before_its_contents_is_valid(self):
        self.assertIsNone(self.collision([("a", True), ("a/b", False)]))

    def test_directory_hierarchy_is_valid(self):
        self.assertIsNone(
            self.collision([("a", True), ("a/b", True), ("a/b/c", False)])
        )

    def test_similar_but_not_prefix_paths_are_valid(self):
        # "a" must not swallow "ab/c": the comparison is per path component.
        self.assertIsNone(self.collision([("a", False), ("ab/c", False)]))
        self.assertIsNone(self.collision([("a.txt", False), ("a.txts", False)]))

    def test_single_file_is_valid(self):
        self.assertIsNone(self.collision([("a", False)]))

    def test_no_entries_is_valid(self):
        self.assertIsNone(self.collision([]))

    def test_exact_duplicate_names_are_left_to_the_duplicate_checks(self):
        # Both consumers already reject these; this helper must not claim
        # them, so the existing duplicate check's precedence is unchanged.
        self.assertIsNone(self.collision([("a", False), ("a", False)]))

    # -- comparison rules --------------------------------------------------

    def test_collisions_are_found_case_insensitively(self):
        # Same reason folded_path folds duplicates: Windows and macOS resolve
        # "A" and "a/b" to the same pair of paths.
        for entries in (
            [("A", False), ("a/b", False)],
            [("a", False), ("A/b", False)],
            [("A", True), ("a", False)],
        ):
            with self.subTest(entries=entries):
                self.assertIsNotNone(self.collision(entries))

    def test_the_first_collision_in_archive_order_is_reported(self):
        result = self.collision(
            [("z", False), ("a", False), ("a/b", False), ("c", False), ("c/d", False)]
        )
        self.assertEqual(result, policy.PathCollision("a", "a/b"))


if __name__ == "__main__":
    unittest.main()
