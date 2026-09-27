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
