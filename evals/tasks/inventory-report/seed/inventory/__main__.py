"""python3 -m inventory value FILE"""
import sys

from .loader import load_csv
from .report import total_value


def main(argv):
    if len(argv) == 2 and argv[0] == "value":
        print(f"{total_value(load_csv(argv[1])):.2f}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


sys.exit(main(sys.argv[1:]))
