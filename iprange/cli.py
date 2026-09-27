"""命令行入口：合并 IP 段、判断包含关系。"""

import argparse
import sys

from .ranges import RangeError, contains, format_range, merge, parse_range


def build_parser():
    parser = argparse.ArgumentParser(prog="ip-range", description="IP 段合并")
    parser.add_argument("--add", action="append", default=[], help="加入一个 CIDR，可重复")
    parser.add_argument("--contains", help="判断这个地址是否被覆盖")
    parser.add_argument("--list", action="store_true", help="打印合并后的 CIDR 列表")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        ranges = [parse_range(text) for text in args.add]
        merged = merge(ranges)
    except (RangeError, ValueError) as error:
        print("错误：%s" % error, file=sys.stderr)
        return 1
    if args.contains is not None:
        print("yes" if contains(merged, args.contains) else "no")
    if args.list or args.contains is None:
        for item in merged:
            print(format_range(item))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
