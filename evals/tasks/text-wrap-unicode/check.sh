set -e
python3 - <<'PY'
from uwrap import display_width, wrap, justify

W = {
    "a\tb": 5, "abcd\t": 8, "\u6f22\t": 4, "e\u0301\tx": 5, "\t\t": 8,
    "abc\t\u6f22\u0301": 6, "\uff21b": 3, "": 0, "\u0301": 0,
}
for s, want in W.items():
    got = display_width(s)
    assert got == want, ("display_width", s, got, want)

L = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor.\n"
     "Ut enim ad minim veniam.\n\n\n  \t\nShort.\n")
M = ("nai\u0308ve cafe\u0301 \u6771\u4eac \u30bf\u30ef\u30fc and re\u0301sume\u0301 "
     "supercalifragilistic \u7d42\u308f\u308a")
CASES = [
    (wrap, L, 20, "Lorem ipsum dolor\nsit amet,\nconsectetur\nadipiscing elit, sed\ndo eiusmod tempor.\n"
                  "Ut enim ad minim\nveniam.\n\nShort."),
    (justify, L, 20, "Lorem   ipsum  dolor\nsit            amet,\nconsectetur\nadipiscing elit, sed\n"
                     "do  eiusmod  tempor.\nUt   enim  ad  minim\nveniam.\n\nShort."),
    (wrap, M, 11, "nai\u0308ve cafe\u0301\n\u6771\u4eac \u30bf\u30ef\u30fc\nand re\u0301sume\u0301\n"
                  "supercalifr\nagilistic\n\u7d42\u308f\u308a"),
    (justify, M, 11, "nai\u0308ve  cafe\u0301\n\u6771\u4eac \u30bf\u30ef\u30fc\nand  re\u0301sume\u0301\n"
                     "supercalifr\nagilistic\n\u7d42\u308f\u308a"),
    (justify, "a\tb  c   d e f g h i j k", 7, "a b c d\ne f g h\ni j k"),
    (wrap, "xx\u0301\u0302\u0303yz", 2, "xx\u0301\u0302\u0303\nyz"),
    (wrap, "\u6f22\u5b57\u6f22\u5b57\u6f22", 3, "\u6f22\n\u5b57\n\u6f22\n\u5b57\n\u6f22"),
    (wrap, "\u6f22\u5b57 a", 1, "\u6f22\n\u5b57\na"),
    (wrap, "\u6f22\u0301\u5b57\u0302 b\u0303", 1, "\u6f22\u0301\n\u5b57\u0302\nb\u0303"),
    (justify, "ok \u6f22\u0301\u0302\u5b57 z", 2, "ok\n\u6f22\u0301\u0302\n\u5b57\nz"),
    (wrap, "\u0301\u0301ab", 1, "\u0301\u0301a\nb"),
    (wrap, "ab\u00a0cd ef\u3000gh i", 4, "ab\u00a0c\nd\nef\u3000\ngh i"),
    (wrap, "ab a\u6f22\u5b57b c", 4, "ab\na\u6f22\n\u5b57b\nc"),
    (justify, "one two three four five six seven eight nine ten", 16,
     "one   two  three\nfour   five  six\nseven eight nine\nten"),
    (justify, "aa bb cc\n\ndd ee ff gg hh", 7, "aa   bb\ncc\n\ndd   ee\nff   gg\nhh"),
    (wrap, " \n\t\n", 5, ""),
    (justify, "", 5, ""),
    (justify, "e\u0301e\u0301e\u0301e\u0301e\u0301 x y z w", 3,
     "e\u0301e\u0301e\u0301\ne\u0301e\u0301\nx y\nz w"),
    (justify, "x abcdefghij y z", 6, "x\nabcdef\nghij y\nz"),
    (justify, "\u65e5\u672c a b \u30c6\u30ad\u30b9\u30c8 c dd", 10,
     "\u65e5\u672c  a  b\n\u30c6\u30ad\u30b9\u30c8 c\ndd"),
]
for fn, text, width, want in CASES:
    got = fn(text, width)
    assert got == want, (fn.__name__, text, width, got, want)

for bad in (0, -3, True, 2.5, "4"):
    for fn in (wrap, justify):
        try:
            fn("abc", bad)
        except ValueError:
            continue
        raise AssertionError(f"{fn.__name__} accepted width {bad!r}")

# property: every justified non-final multi-word line is exactly `width`, and stripping
# runs of spaces gives back wrap()'s line
import random
rnd = random.Random(7)
alphabet = ["a", "bb", "ccc", "e\u0301", "\u6f22", "\u5b57\u0301", "x\u0308y", "\uff21"]
for _ in range(300):
    words = ["".join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 5))) for _ in range(rnd.randint(1, 25))]
    text = ""
    for w in words:
        text += w + rnd.choice([" ", " ", "  ", "\t", "\n", "\n\n"])
    width = rnd.randint(1, 14)
    wr, ju = wrap(text, width), justify(text, width)
    assert [" ".join(l.split(" ")).split() for l in ju.split("\n")] == [l.split() for l in wr.split("\n")]
    for para_w, para_j in zip(wr.split("\n\n"), ju.split("\n\n")):
        wl, jl = para_w.split("\n"), para_j.split("\n")
        assert len(wl) == len(jl)
        for i, (a, b) in enumerate(zip(wl, jl)):
            if i < len(wl) - 1 and " " in a:
                assert display_width(b) == width, (text, width, b)
            else:
                assert a == b, (text, width, a, b)
        for line in wl:
            if display_width(line) > width:
                assert " " not in line and len([c for c in line if display_width(c) > 0]) == 1, (text, width, line)
PY
python3 -m unittest -q 2>/dev/null
