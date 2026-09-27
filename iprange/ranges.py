"""IP 段合并。只用标准库。缺陷：不规范化主机位、不合并相邻段、按字符串排序。"""

import ipaddress


class RangeError(ValueError):
    """输入不合法。缺陷：不带段下标。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def parse_range(text):
    """解析 "10.0.0.0/24"。缺陷：不校验前缀范围，也不清零主机位。"""
    address, _, prefix = text.partition("/")
    return (ipaddress.ip_address(address), int(prefix))


def format_range(item):
    """缺陷：直接照抄传入的地址，主机位没被清零。"""
    address, prefix = item
    return "%s/%d" % (address, prefix)


def merge(ranges):
    """缺陷：只去掉完全重复的段，相邻与重叠的段都不合并，还按字符串排序。"""
    seen = []
    for item in ranges:
        if item not in seen:
            seen.append(item)
    return sorted(seen, key=format_range)


def contains(ranges, address):
    """缺陷：逐段扫，每段都重新构造网络对象。"""
    target = ipaddress.ip_address(address)
    for item in ranges:
        network = ipaddress.ip_network(format_range(item), strict=False)
        if target.version == network.version and target in network:
            return True
    return False
