"""Display-width aware word wrapping and full justification."""
import unicodedata


def _char_width(ch):
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def display_width(s):
    col = 0
    for ch in s:
        if ch == "\t":
            col = (col // 4 + 1) * 4
        else:
            col += _char_width(ch)
    return col


def _graphemes(word):
    out = []
    for ch in word:
        if unicodedata.combining(ch) and out and not unicodedata.combining(out[-1][0]):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _check(width):
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise ValueError("width must be an int >= 1")


def _paragraphs(text):
    paras, cur = [], []
    for line in text.split("\n"):
        if line.strip(" \t") == "":
            if cur:
                paras.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        paras.append(cur)
    return paras


def _words(lines):
    words = []
    for line in lines:
        words.extend(w for w in line.replace("\t", " ").split(" ") if w)
    return words


def _break(words, width):
    """Return lines, each a list of words."""
    lines, cur, cur_w = [], [], 0
    for word in words:
        w = display_width(word)
        if w <= width:
            if not cur:
                cur, cur_w = [word], w
            elif cur_w + 1 + w <= width:
                cur.append(word)
                cur_w += 1 + w
            else:
                lines.append(cur)
                cur, cur_w = [word], w
            continue
        if cur:
            lines.append(cur)
        chunk, chunk_w = "", 0
        chunks = []
        for g in _graphemes(word):
            gw = display_width(g)
            if chunk and chunk_w + gw > width:
                chunks.append(chunk)
                chunk, chunk_w = "", 0
            chunk += g
            chunk_w += gw
        chunks.append(chunk)
        for c in chunks[:-1]:
            lines.append([c])
        cur, cur_w = [chunks[-1]], display_width(chunks[-1])
    if cur:
        lines.append(cur)
    return lines


def wrap(text, width):
    _check(width)
    return "\n\n".join("\n".join(" ".join(l) for l in _break(_words(p), width))
                       for p in _paragraphs(text))


def _justify_line(words, width):
    gaps = len(words) - 1
    w = sum(display_width(x) for x in words) + gaps
    if gaps == 0 or w >= width:
        return " ".join(words)
    extra = width - w
    out = words[0]
    for i, word in enumerate(words[1:]):
        out += " " * (1 + extra // gaps + (1 if i < extra % gaps else 0)) + word
    return out


def justify(text, width):
    _check(width)
    paras = []
    for p in _paragraphs(text):
        lines = _break(_words(p), width)
        out = [_justify_line(l, width) for l in lines[:-1]] + [" ".join(lines[-1])]
        paras.append("\n".join(out))
    return "\n\n".join(paras)
