import io
import ipaddress
import random
import unittest
from contextlib import redirect_stdout

from iprange.cli import main
from iprange.ranges import RangeError, contains, format_range, merge, parse_range


def brute_force(texts):
    """把输入段逐地址展开成集合（仅限 ≤ /24 的小段）。"""
    addresses = set()
    for text in texts:
        network = ipaddress.ip_network(text, strict=False)
        assert network.num_addresses <= 256
        addresses.update(int(a) for a in network)
    return addresses


def expand_merged(merged):
    addresses = set()
    for address, prefix in merged:
        size = 1 << ((32 if address.version == 4 else 128) - prefix)
        addresses.update(range(int(address), int(address) + size))
    return addresses


class ParseTest(unittest.TestCase):
    def test_plain_network(self):
        self.assertEqual(parse_range("10.0.0.0/24"), (ipaddress.ip_address("10.0.0.0"), 24))

    def test_single_host(self):
        self.assertEqual(parse_range("10.0.0.1/32"), (ipaddress.ip_address("10.0.0.1"), 32))

    def test_host_bits_cleared(self):
        self.assertEqual(parse_range("10.0.0.7/24"), (ipaddress.ip_address("10.0.0.0"), 24))

    def test_ipv6_host_bits_cleared(self):
        self.assertEqual(parse_range("2001:db8::1/32"), (ipaddress.ip_address("2001:db8::"), 32))

    def test_missing_prefix(self):
        with self.assertRaises((RangeError, ValueError)):
            parse_range("10.0.0.0")

    def test_bad_address(self):
        with self.assertRaises(RangeError):
            parse_range("999.0.0.0/24")

    def test_prefix_out_of_range(self):
        with self.assertRaises(RangeError):
            parse_range("10.0.0.0/33")
        with self.assertRaises(RangeError):
            parse_range("10.0.0.0/-1")
        with self.assertRaises(RangeError):
            parse_range("::1/129")

    def test_prefix_not_a_number(self):
        with self.assertRaises(RangeError):
            parse_range("10.0.0.0/abc")

    def test_error_names_add_index(self):
        with self.assertRaises(RangeError) as ctx:
            parse_range("10.0.0.0/33", 3)
        self.assertIn("3", str(ctx.exception))


class MergeTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge([]), [])

    def test_single(self):
        self.assertEqual(merge([parse_range("10.0.0.0/24")]), [(ipaddress.ip_address("10.0.0.0"), 24)])

    def test_duplicates_collapse(self):
        item = parse_range("10.0.0.0/24")
        self.assertEqual(merge([item, item]), [item])

    def test_adjacent_halves_merge(self):
        merged = merge([parse_range("10.0.0.0/25"), parse_range("10.0.0.128/25")])
        self.assertEqual(merged, [(ipaddress.ip_address("10.0.0.0"), 24)])

    def test_adjacent_slash24_merge(self):
        merged = merge([parse_range("10.0.0.0/24"), parse_range("10.0.1.0/24")])
        self.assertEqual(merged, [(ipaddress.ip_address("10.0.0.0"), 23)])

    def test_overlap_merges(self):
        merged = merge([parse_range("10.0.0.0/24"), parse_range("10.0.0.128/25")])
        self.assertEqual(merged, [(ipaddress.ip_address("10.0.0.0"), 24)])

    def test_numeric_sort(self):
        merged = merge([parse_range("10.0.0.10/32"), parse_range("10.0.0.2/32")])
        self.assertEqual([format_range(i) for i in merged], ["10.0.0.2/32", "10.0.0.10/32"])

    def test_ipv4_before_ipv6(self):
        merged = merge([parse_range("::/0"), parse_range("0.0.0.0/0")])
        self.assertEqual([i[0].version for i in merged], [4, 6])

    def test_order_independent_and_idempotent(self):
        texts = ["10.0.0.0/25", "10.0.0.128/25", "192.168.0.0/24", "10.0.0.0/25"]
        base = merge([parse_range(t) for t in texts])
        rng = random.Random(42)
        for _ in range(20):
            shuffled = texts[:]
            rng.shuffle(shuffled)
            self.assertEqual(merge([parse_range(t) for t in shuffled]), base)
        self.assertEqual(merge(base), base)

    def test_result_pairwise_disjoint(self):
        texts = ["10.0.0.0/24", "10.0.0.128/25", "10.0.1.0/24", "10.0.1.0/32", "172.16.0.0/24"]
        merged = merge([parse_range(t) for t in texts])
        intervals = sorted(
            (int(a), int(a) + (1 << (32 - p)) - 1) for a, p in merged if a.version == 4
        )
        for (s1, e1), (s2, e2) in zip(intervals, intervals[1:]):
            self.assertLess(e1, s2)

    def test_coverage_matches_brute_force(self):
        rng = random.Random(7)
        texts = set()
        for _ in range(60):
            third = rng.randrange(0, 4)
            texts.add("10.0.%d.%d/%d" % (third, rng.randrange(0, 256), rng.choice([24, 25, 26, 28, 30, 32])))
        texts = sorted(texts)
        merged = merge([parse_range(t) for t in texts])
        expected = brute_force(texts)
        actual = expand_merged(merged)
        self.assertEqual(len(expected - actual), 0)
        self.assertEqual(len(actual - expected), 0)

    def test_host_bits_cleared_on_merge(self):
        merged = merge([parse_range("10.0.0.7/24")])
        self.assertEqual([format_range(i) for i in merged], ["10.0.0.0/24"])

    def test_scale_100k_mixed_prefixes(self):
        rng = random.Random(1)
        items = []
        for _ in range(100000):
            addr = ipaddress.IPv4Address(rng.getrandbits(32))
            prefix = rng.choice([8, 16, 24, 32])
            items.append((addr, prefix))
        merged = merge(items)
        self.assertTrue(all(a.version == 4 for a, _ in merged))
        intervals = [(int(a), int(a) + (1 << (32 - p)) - 1) for a, p in merged]
        for (s1, e1), (s2, e2) in zip(intervals, intervals[1:]):
            self.assertLess(e1, s2)


class ContainsTest(unittest.TestCase):
    def test_inside(self):
        self.assertTrue(contains([parse_range("10.0.0.0/24")], "10.0.0.7"))

    def test_outside(self):
        self.assertFalse(contains([parse_range("10.0.0.0/24")], "10.0.1.7"))

    def test_other_family(self):
        self.assertFalse(contains([parse_range("10.0.0.0/24")], "::1"))

    def test_ipv6_inside(self):
        self.assertTrue(contains(merge([parse_range("2001:db8::/32")]), "2001:db8::1"))

    def test_no_network_objects_rebuilt(self):
        merged = merge([parse_range("10.0.0.0/24")])
        original = ipaddress.ip_network
        def boom(*args, **kwargs):
            raise AssertionError("不应重新构造网络对象")
        ipaddress.ip_network = boom
        try:
            self.assertTrue(contains(merged, "10.0.0.7"))
            self.assertFalse(contains(merged, "10.0.1.7"))
        finally:
            ipaddress.ip_network = original

    def test_scale_100k(self):
        rng = random.Random(2)
        items = []
        for _ in range(100000):
            addr = ipaddress.IPv4Address(rng.getrandbits(32))
            items.append((addr, rng.choice([8, 16, 24, 32])))
        merged = merge(items)
        for address, prefix in merged[:: max(1, len(merged) // 100)]:
            self.assertTrue(contains(merged, str(address)))
        self.assertFalse(contains(merge([parse_range("10.0.0.0/8")]), "11.0.0.0"))


class CliTest(unittest.TestCase):
    def run_cli(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_lists_single_range(self):
        code, out = self.run_cli(["--add", "10.0.0.0/24", "--list"])
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), ["10.0.0.0/24"])

    def test_merges_two_halves(self):
        code, out = self.run_cli(["--add", "10.0.0.0/25", "--add", "10.0.0.128/25", "--list"])
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), ["10.0.0.0/24"])

    def test_normalizes_host_bits(self):
        code, out = self.run_cli(["--add", "10.0.0.7/24", "--list"])
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), ["10.0.0.0/24"])

    def test_numeric_order(self):
        code, out = self.run_cli(["--add", "10.0.0.10/32", "--add", "10.0.0.2/32", "--list"])
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), ["10.0.0.2/32", "10.0.0.10/32"])

    def test_contains_prints_yes(self):
        code, out = self.run_cli(["--add", "10.0.0.0/24", "--contains", "10.0.0.7"])
        self.assertEqual(out.split()[0], "yes")

    def test_contains_prints_no(self):
        code, out = self.run_cli(["--add", "10.0.0.0/24", "--contains", "10.0.9.7"])
        self.assertEqual(out.split()[0], "no")

    def test_bad_add_reports_index(self):
        import sys
        buffer = io.StringIO()
        with redirect_stdout(io.StringIO()):
            from contextlib import redirect_stderr
            with redirect_stderr(buffer):
                code = main(["--add", "10.0.0.0/24", "--add", "10.0.0.0/33", "--list"])
        self.assertEqual(code, 1)
        self.assertIn("2", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
