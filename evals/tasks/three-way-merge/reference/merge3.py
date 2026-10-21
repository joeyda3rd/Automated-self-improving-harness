"""Line-based three-way merge (diff3)."""
from difflib import SequenceMatcher

STYLES = ("diff3", "merge")


def _match(base, side):
    m = {}
    for a, b, n in SequenceMatcher(None, base, side, autojunk=False).get_matching_blocks():
        for k in range(n):
            m[a + k] = b + k
    return m


def merge(base, ours, theirs, style="diff3"):
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}")
    base, ours, theirs = list(base), list(ours), list(theirs)
    mo, mt = _match(base, ours), _match(base, theirs)
    stable = [(-1, -1, -1)] + [(i, mo[i], mt[i]) for i in range(len(base)) if i in mo and i in mt] \
        + [(len(base), len(ours), len(theirs))]
    out, conflicts = [], 0
    for (pi, po, pt), (qi, qo, qt) in zip(stable, stable[1:]):
        B, O, T = base[pi + 1:qi], ours[po + 1:qo], theirs[pt + 1:qt]
        if O == T:
            out += O
        elif O == B:
            out += T
        elif T == B:
            out += O
        else:
            conflicts += 1
            if style == "diff3":
                out += ["<<<<<<< ours", *O, "||||||| base", *B, "=======", *T, ">>>>>>> theirs"]
            else:
                p = 0
                while p < min(len(O), len(T)) and O[p] == T[p]:
                    p += 1
                O2, T2 = O[p:], T[p:]
                s = 0
                while s < min(len(O2), len(T2)) and O2[-1 - s] == T2[-1 - s]:
                    s += 1
                out += O[:p]
                out += ["<<<<<<< ours", *O2[:len(O2) - s], "=======", *T2[:len(T2) - s], ">>>>>>> theirs"]
                out += O2[len(O2) - s:]
        if qi < len(base):
            out.append(ours[qo])
    return out, conflicts


def merge_text(base, ours, theirs, style="diff3"):
    lines, n = merge(base.split("\n"), ours.split("\n"), theirs.split("\n"), style)
    return "\n".join(lines), n
