set -e
timeout 50 python3 - <<'PY'
import random, time
from difflib import SequenceMatcher
from merge3 import merge, merge_text

L = list
def eq(args, want, style="diff3"):
    b, o, t = (L(x) for x in args)
    copies = [L(b), L(o), L(t)]
    got = merge(b, o, t, style=style)
    assert [b, o, t] == copies, "inputs were modified"
    assert got == want, f"merge({args}, style={style!r})\n got {got}\nwant {want}"

C_O, C_B, C_S, C_T = "<<<<<<< ours", "||||||| base", "=======", ">>>>>>> theirs"
eq(("abcde", "aBcde", "abcDe"), (L("aBcDe"), 0))
eq(("abcd", "aXcd", "abYd"), (["a", C_O, "X", "c", C_B, "b", "c", C_S, "b", "Y", C_T, "d"], 1))
eq(("abc", "aXc", "aXc"), (L("aXc"), 0))
eq(("abc", "ac", "ac"), (L("ac"), 0))
eq(("abc", "ac", "abc"), (L("ac"), 0))
eq(("abc", "ac", "aYc"), (["a", C_O, C_B, "b", C_S, "Y", C_T, "c"], 1))
eq(("ab", "aXb", "aYb"), (["a", C_O, "X", C_B, C_S, "Y", C_T, "b"], 1))
eq(("ab", "aXb", "aXb"), (L("aXb"), 0))
eq(("ab", "aXYb", "aXb"), (["a", C_O, "X", "Y", C_B, C_S, "X", C_T, "b"], 1))
eq(("", "x", ""), (["x"], 0))
eq(("", "", ""), ([], 0))
eq(("abcdefg", "aXcdefZ", "abcYefg"), (L("aXcYefZ"), 0))
eq(("abcdefg", "aXcdefZ", "abcYefW"), (["a", "X", "c", "Y", "e", "f", C_O, "Z", C_B, "g", C_S, "W", C_T], 1))
# merge style: trimming, no base section
eq(("x", "pos", "pts"), (["p", C_O, "o", C_S, "t", C_T, "s"], 1), "merge")
eq(("m", "ab", "a"), (["a", C_O, "b", C_S, C_T], 1), "merge")
eq(("z", "aa", "a"), (["a", C_O, "a", C_S, C_T], 1), "merge")
eq(("z", "aba", "aa"), (["a", C_O, "b", C_S, C_T, "a"], 1), "merge")
eq(("ab", "aXb", "aYb"), (["a", C_O, "X", C_S, "Y", C_T, "b"], 1), "merge")
eq(("abcd", "aXcd", "abYd"), (["a", C_O, "X", "c", C_S, "b", "Y", C_T, "d"], 1), "merge")
eq(("abc", "aXc", "aXc"), (L("aXc"), 0), "merge")
eq(("q", "xyz", "xz"), (["x", C_O, "y", C_S, C_T, "z"], 1), "merge")
# two conflicts
eq(("abcde", "aXcYe", "aPcQe"), (["a", C_O, "X", C_B, "b", C_S, "P", C_T, "c",
                                  C_O, "Y", C_B, "d", C_S, "Q", C_T, "e"], 2))
for bad in ["", "DIFF3", None, "zealous"]:
    try:
        merge(["a"], ["a"], ["a"], style=bad)
    except ValueError:
        continue
    raise AssertionError(f"style {bad!r} accepted")
# text API
assert merge_text("a\nb\n", "a\nB\n", "a\nb\n") == ("a\nB\n", 0)
assert merge_text("a\nb\nc\nd\ne\n", "a\nB\nc\nd\ne\n", "a\nb\nc\nd\nE\n") == ("a\nB\nc\nd\nE\n", 0)
assert merge_text("a\nb\n", "a\nb", "a\nb\nc\n") == ("a\nb\n<<<<<<< ours\n||||||| base\n\n=======\nc\n\n>>>>>>> theirs", 1), merge_text("a\nb\n", "a\nb", "a\nb\nc\n")
assert merge_text("", "x", "y", style="merge") == ("<<<<<<< ours\nx\n=======\ny\n>>>>>>> theirs", 1)

# randomized differential test against the specified algorithm
def oracle(base, ours, theirs, style):
    def m(side):
        d = {}
        for a, b, n in SequenceMatcher(None, base, side, autojunk=False).get_matching_blocks():
            d.update((a + k, b + k) for k in range(n))
        return d
    mo, mt = m(ours), m(theirs)
    st = [(-1, -1, -1)] + [(i, mo[i], mt[i]) for i in range(len(base)) if i in mo and i in mt] + [(len(base), len(ours), len(theirs))]
    out, n = [], 0
    for p, q in zip(st, st[1:]):
        B, O, T = base[p[0]+1:q[0]], ours[p[1]+1:q[1]], theirs[p[2]+1:q[2]]
        if O == T: out += O
        elif O == B: out += T
        elif T == B: out += O
        else:
            n += 1
            if style == "diff3":
                out += [C_O] + O + [C_B] + B + [C_S] + T + [C_T]
            else:
                k = 0
                while k < min(len(O), len(T)) and O[k] == T[k]: k += 1
                O2, T2 = O[k:], T[k:]
                s = 0
                while s < min(len(O2), len(T2)) and O2[-1-s] == T2[-1-s]: s += 1
                out += O[:k] + [C_O] + O2[:len(O2)-s] + [C_S] + T2[:len(T2)-s] + [C_T] + O2[len(O2)-s:]
        if q[0] < len(base): out.append(ours[q[1]])
    return out, n

rng = random.Random(3)
def mutate(lines, alpha):
    lines = L(lines)
    for _ in range(rng.randint(0, 4)):
        k = rng.random(); i = rng.randint(0, len(lines))
        if k < 0.35 and lines: lines[min(i, len(lines)-1)] = rng.choice(alpha)
        elif k < 0.65: lines[i:i] = [rng.choice(alpha) for _ in range(rng.randint(1, 3))]
        elif lines: del lines[i:i + rng.randint(1, 3)]
    return lines
for _ in range(600):
    alpha = L("abcdefgh"[:rng.randint(2, 8)]) + ["X", "Y", "Z", ""]
    base = [rng.choice(alpha[:-4]) for _ in range(rng.randint(0, 12))]
    ours, theirs = mutate(base, alpha), mutate(base, alpha)
    if rng.random() < 0.2: theirs = L(ours) if rng.random() < 0.5 else mutate(ours, alpha)
    for style in ("diff3", "merge"):
        eq((base, ours, theirs), oracle(base, ours, theirs, style), style)

# performance
base = [f"line {i} {'x' * (i % 7)}" for i in range(3000)]
ours, theirs = L(base), L(base)
for i in range(0, 3000, 37): ours[i] = f"ours {i}"
for i in range(5, 3000, 41): theirs[i] = f"theirs {i}"
del ours[1000:1050]; theirs[2000:2000] = [f"new {k}" for k in range(80)]
t0 = time.perf_counter()
got = merge(base, ours, theirs)
el = time.perf_counter() - t0
assert got == oracle(base, ours, theirs, "diff3")
assert el < 1.0, f"3000-line merge took {el:.2f}s"
PY
python3 -m unittest -q 2>/dev/null
