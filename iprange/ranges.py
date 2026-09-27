"""IP 段解析、规范化与合并。只用标准库（ipaddress/bisect）。"""

import bisect
import ipaddress


class RangeError(ValueError):
    """输入不合法；message 里带第几个 --add。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _max_prefix(version):
    return 32 if version == 4 else 128


def parse_range(text, index=None):
    """解析 "地址/前缀"，主机位清零。index 是第几个 --add（从 1 起），用于报错。"""
    where = "第 %d 个 --add " % index if index is not None else ""
    if "/" not in text:
        raise RangeError("%s缺少 '/'：%r" % (where, text))
    address_text, _, prefix_text = text.partition("/")
    try:
        address = ipaddress.ip_address(address_text.strip())
    except ValueError:
        raise RangeError("%s地址非法：%r" % (where, address_text)) from None
    try:
        prefix = int(prefix_text)
    except ValueError:
        raise RangeError("%s前缀非法：%r" % (where, prefix_text)) from None
    max_prefix = _max_prefix(address.version)
    if not 0 <= prefix <= max_prefix:
        raise RangeError(
            "%s前缀越界：%d（IPv%d 允许 0..%d）" % (where, prefix, address.version, max_prefix)
        )
    host_bits = max_prefix - prefix
    start = int(address) & (((1 << max_prefix) - 1) ^ ((1 << host_bits) - 1))
    return (address.__class__(start), prefix)


def format_range(item):
    """item 是 (网络地址, 前缀)，地址已规范化。"""
    address, prefix = item
    return "%s/%d" % (address, prefix)


def _to_interval(item):
    address, prefix = item
    max_prefix = _max_prefix(address.version)
    host_bits = max_prefix - prefix
    start = int(address) & (((1 << max_prefix) - 1) ^ ((1 << host_bits) - 1))
    return (address.version, start, start + (1 << host_bits) - 1)


def merge(ranges):
    """合并重叠/相邻段为最小 CIDR 集合；IPv4 在前，按地址数值再按前缀升序。

    内存 O(段数)：只用区间端点，不展开地址。
    """
    intervals = {4: [], 6: []}
    for item in ranges:
        version, start, end = _to_interval(item)
        intervals[version].append((start, end))
    result = []
    for version in (4, 6):
        spans = sorted(intervals[version])
        if not spans:
            continue
        merged = []
        cur_start, cur_end = spans[0]
        for start, end in spans[1:]:
            if start <= cur_end + 1:
                if end > cur_end:
                    cur_end = end
            else:
                merged.append((cur_start, cur_end))
                cur_start, cur_end = start, end
        merged.append((cur_start, cur_end))
        cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
        for start, end in merged:
            for network in ipaddress.summarize_address_range(cls(start), cls(end)):
                result.append((network.network_address, network.prefixlen))
    result.sort(key=lambda item: (item[0].version, int(item[0]), item[1]))
    return result


def contains(ranges, address):
    """判断 address 是否被已排序的合并结果覆盖；二分查找，不构造网络对象。"""
    target = ipaddress.ip_address(address)
    keys = [(item[0].version, int(item[0])) for item in ranges]
    index = bisect.bisect_right(keys, (target.version, int(target))) - 1
    if index < 0:
        return False
    network_address, prefix = ranges[index]
    if network_address.version != target.version:
        return False
    host_bits = _max_prefix(target.version) - prefix
    return 0 <= int(target) - int(network_address) < (1 << host_bits)
