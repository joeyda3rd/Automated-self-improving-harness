"""python3 -m inventory value FILE"""
import sys

from .loader import load_csv
from .report import low_stock, total_value


def main(argv):
    if len(argv) == 2 and argv[0] == "value":
        print(f"{total_value(load_csv(argv[1])):.2f}")
        return 0
    if len(argv) in (2, 4) and argv[0] == "low-stock":
        default = int(argv[3]) if len(argv) == 4 and argv[2] == "--default" else 5
        for i in low_stock(load_csv(argv[1]), {}, default):
            print(f"{i.sku},{i.category},{i.qty}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


sys.exit(main(sys.argv[1:]))
