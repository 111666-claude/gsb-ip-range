"""IP 段规范化与合并：最小 CIDR 集合，只用标准库。"""

import bisect
import ipaddress


class RangeError(ValueError):
    """输入不合法。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _normalize(address, prefix):
    """主机位清零，返回 (网络地址, 前缀)。"""
    host_bits = address.max_prefixlen - prefix
    value = int(address)
    if host_bits:
        value = (value >> host_bits) << host_bits
    return (ipaddress.ip_address(value), prefix)


def parse_range(text):
    """解析 "10.0.0.0/24"，主机位清零；非法输入抛 RangeError。"""
    address_text, sep, prefix_text = text.partition("/")
    if not sep:
        raise RangeError("缺少 '/'：%r" % text)
    try:
        address = ipaddress.ip_address(address_text)
    except ValueError:
        raise RangeError("非法地址：%r" % text)
    try:
        prefix = int(prefix_text)
    except ValueError:
        raise RangeError("非法前缀：%r" % text)
    if not 0 <= prefix <= address.max_prefixlen:
        raise RangeError("前缀越界：%r（该地址族允许 0-%d）" % (text, address.max_prefixlen))
    return _normalize(address, prefix)


def format_range(item):
    address, prefix = item
    return "%s/%d" % (address, prefix)


def merge(ranges):
    """合并重叠与相邻的段为最小 CIDR 集合；IPv4 在前，按数值与前缀升序。"""
    normalized = [_normalize(address, prefix) for address, prefix in ranges]
    result = []
    for version in (4, 6):
        family = [item for item in normalized if item[0].version == version]
        if not family:
            continue
        max_prefixlen = family[0][0].max_prefixlen
        intervals = []
        for address, prefix in family:
            start = int(address)
            intervals.append((start, start + (1 << (max_prefixlen - prefix)) - 1))
        intervals.sort()
        merged_intervals = []
        for start, end in intervals:
            if merged_intervals and start <= merged_intervals[-1][1] + 1:
                if end > merged_intervals[-1][1]:
                    merged_intervals[-1][1] = end
            else:
                merged_intervals.append([start, end])
        for start, end in merged_intervals:
            first = ipaddress.ip_address(start)
            last = ipaddress.ip_address(end)
            for network in ipaddress.summarize_address_range(first, last):
                result.append((network.network_address, network.prefixlen))
    result.sort(key=lambda item: (item[0].version, int(item[0]), item[1]))
    return result


def contains(ranges, address):
    """判断地址是否被覆盖；对排序后的区间二分，不逐段构造网络对象。"""
    target = ipaddress.ip_address(address)
    value = int(target)
    intervals = []
    for item in ranges:
        network_address, prefix = item
        if network_address.version != target.version:
            continue
        start = int(network_address)
        end = start + (1 << (network_address.max_prefixlen - prefix)) - 1
        intervals.append((start, end))
    intervals.sort()
    starts = [start for start, _ in intervals]
    index = bisect.bisect_right(starts, value) - 1
    return index >= 0 and intervals[index][1] >= value
