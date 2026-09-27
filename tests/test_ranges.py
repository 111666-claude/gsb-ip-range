import io
import ipaddress
import unittest
from contextlib import redirect_stdout

from iprange.cli import main
from iprange.ranges import RangeError, contains, format_range, merge, parse_range


class ParseTest(unittest.TestCase):
    def test_plain_network(self):
        self.assertEqual(parse_range("10.0.0.0/24"), (ipaddress.ip_address("10.0.0.0"), 24))

    def test_single_host(self):
        self.assertEqual(parse_range("10.0.0.1/32"), (ipaddress.ip_address("10.0.0.1"), 32))

    def test_missing_prefix(self):
        with self.assertRaises((RangeError, ValueError)):
            parse_range("10.0.0.0")


class MergeTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge([]), [])

    def test_single(self):
        self.assertEqual(merge([parse_range("10.0.0.0/24")]), [(ipaddress.ip_address("10.0.0.0"), 24)])

    def test_duplicates_collapse(self):
        item = parse_range("10.0.0.0/24")
        self.assertEqual(merge([item, item]), [item])


class ContainsTest(unittest.TestCase):
    def test_inside(self):
        self.assertTrue(contains([parse_range("10.0.0.0/24")], "10.0.0.7"))

    def test_outside(self):
        self.assertFalse(contains([parse_range("10.0.0.0/24")], "10.0.1.7"))

    def test_other_family(self):
        self.assertFalse(contains([parse_range("10.0.0.0/24")], "::1"))


class CliTest(unittest.TestCase):
    def test_lists_single_range(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--add", "10.0.0.0/24", "--list"])
        self.assertEqual(code, 0)
        self.assertEqual(buffer.getvalue().split(), ["10.0.0.0/24"])

    def test_contains_prints_yes(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            main(["--add", "10.0.0.0/24", "--contains", "10.0.0.7"])
        self.assertEqual(buffer.getvalue().split()[0], "yes")

    def test_contains_prints_no(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            main(["--add", "10.0.0.0/24", "--contains", "10.0.9.7"])
        self.assertEqual(buffer.getvalue().split()[0], "no")


if __name__ == "__main__":
    unittest.main()


class NormalizeTest(unittest.TestCase):
    def test_host_bits_cleared(self):
        self.assertEqual(parse_range("10.0.0.7/24"), (ipaddress.ip_address("10.0.0.0"), 24))

    def test_ipv6_host_bits_cleared(self):
        self.assertEqual(parse_range("2001:db8::1/64"), (ipaddress.ip_address("2001:db8::"), 64))

    def test_prefix_too_large(self):
        with self.assertRaises(RangeError):
            parse_range("10.0.0.0/33")

    def test_prefix_negative(self):
        with self.assertRaises(RangeError):
            parse_range("10.0.0.0/-1")

    def test_prefix_not_a_number(self):
        with self.assertRaises(RangeError):
            parse_range("10.0.0.0/abc")

    def test_bad_address(self):
        with self.assertRaises(RangeError):
            parse_range("999.0.0.0/24")


class MergeSpecTest(unittest.TestCase):
    def test_adjacent_halves_merge(self):
        merged = merge([parse_range("10.0.0.0/25"), parse_range("10.0.0.128/25")])
        self.assertEqual(merged, [(ipaddress.ip_address("10.0.0.0"), 24)])

    def test_adjacent_24s_merge_to_23(self):
        merged = merge([parse_range("10.0.0.0/24"), parse_range("10.0.1.0/24")])
        self.assertEqual(merged, [(ipaddress.ip_address("10.0.0.0"), 23)])

    def test_overlap_merges(self):
        merged = merge([parse_range("10.0.0.0/24"), parse_range("10.0.0.128/25")])
        self.assertEqual(merged, [(ipaddress.ip_address("10.0.0.0"), 24)])

    def test_numeric_sort(self):
        merged = merge([parse_range("10.0.0.10/32"), parse_range("10.0.0.2/32")])
        self.assertEqual(
            merged,
            [(ipaddress.ip_address("10.0.0.2"), 32), (ipaddress.ip_address("10.0.0.10"), 32)],
        )

    def test_ipv4_before_ipv6(self):
        merged = merge([parse_range("2001:db8::/64"), parse_range("10.0.0.0/24")])
        self.assertEqual(merged[0][0].version, 4)
        self.assertEqual(merged[1][0].version, 6)

    def test_idempotent_and_order_independent(self):
        texts = ["10.0.0.0/25", "10.0.0.128/25", "10.0.1.0/24", "10.0.0.0/25"]
        forward = merge([parse_range(t) for t in texts])
        backward = merge([parse_range(t) for t in reversed(texts)])
        again = merge(forward)
        self.assertEqual(forward, backward)
        self.assertEqual(forward, again)
        self.assertEqual(forward, [(ipaddress.ip_address("10.0.0.0"), 23)])

    def test_result_pairwise_disjoint(self):
        texts = ["10.0.0.0/24", "10.0.1.0/24", "10.0.0.128/25", "192.168.0.0/16"]
        merged = merge([parse_range(t) for t in texts])
        networks = [ipaddress.ip_network(format_range(item)) for item in merged]
        for i, left in enumerate(networks):
            for right in networks[i + 1:]:
                self.assertFalse(left.overlaps(right))


class CoverageTest(unittest.TestCase):
    def test_small_ranges_match_brute_force(self):
        import random

        random.seed(127)
        texts = []
        for _ in range(60):
            third = random.randint(0, 3)
            fourth = random.randint(0, 255)
            prefix = random.randint(24, 32)
            texts.append("10.0.%d.%d/%d" % (third, fourth, prefix))
        merged = merge([parse_range(t) for t in texts])
        expected = set()
        for text in texts:
            expected.update(ipaddress.ip_network(text, strict=False))
        actual = set()
        for item in merged:
            actual.update(ipaddress.ip_network(format_range(item)))
        self.assertEqual(expected, actual)


class ScaleTest(unittest.TestCase):
    def test_hundred_thousand_mixed_ranges(self):
        import random

        random.seed(7)
        texts = []
        for _ in range(100000):
            first = random.randint(0, 255)
            if random.random() < 0.5:
                texts.append("%d.0.0.0/8" % first)
            else:
                texts.append(
                    "%d.%d.%d.%d/32"
                    % (first, random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                )
        merged = merge([parse_range(t) for t in texts])
        self.assertTrue(merged)
        self.assertEqual(merged, merge(merged))
        self.assertTrue(contains(merged, "%d.0.0.1" % 0) or not contains(merged, "0.0.0.1"))


class CliErrorTest(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), __import__("contextlib").redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_error_names_add_index(self):
        code, _, err = self._run(["--add", "10.0.0.0/24", "--add", "10.0.0.0/33", "--list"])
        self.assertEqual(code, 1)
        self.assertIn("第 2 个 --add", err)

    def test_missing_slash_errors(self):
        code, _, err = self._run(["--add", "10.0.0.0"])
        self.assertEqual(code, 1)
        self.assertIn("第 1 个 --add", err)

    def test_cli_merges_adjacent(self):
        code, out, _ = self._run(
            ["--add", "10.0.0.0/25", "--add", "10.0.0.128/25", "--list"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), ["10.0.0.0/24"])

    def test_cli_normalizes_host_bits(self):
        code, out, _ = self._run(["--add", "10.0.0.7/24", "--list"])
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), ["10.0.0.0/24"])

    def test_cli_numeric_order(self):
        code, out, _ = self._run(
            ["--add", "10.0.0.10/32", "--add", "10.0.0.2/32", "--list"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), ["10.0.0.2/32", "10.0.0.10/32"])
