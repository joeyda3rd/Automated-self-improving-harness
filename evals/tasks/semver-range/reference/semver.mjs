// npm-style semver: compare, satisfies, maxSatisfying (strict, prereleases excluded by default).
const NUM = '0|[1-9]\\d*';
const PRE_ID = '(?:0|[1-9]\\d*|\\d*[A-Za-z-][0-9A-Za-z-]*)';
const PRE = `${PRE_ID}(?:\\.${PRE_ID})*`;
const BUILD = '[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*';
const FULL = new RegExp(`^v?(${NUM})\\.(${NUM})\\.(${NUM})(?:-(${PRE}))?(?:\\+(${BUILD}))?$`);
const XID = `${NUM}|x|X|\\*`;
const PARTIAL = new RegExp(`^v?(${XID})(?:\\.(${XID})(?:\\.(${XID})(?:-(${PRE}))?(?:\\+(${BUILD}))?)?)?$`);

function parse(v) {
  if (typeof v !== 'string') return null;
  const m = FULL.exec(v.trim());
  if (!m) return null;
  return {
    major: +m[1], minor: +m[2], patch: +m[3],
    pre: m[4] === undefined ? [] : m[4].split('.').map((id) => (/^\d+$/.test(id) ? +id : id)),
  };
}

function cmpPre(a, b) {
  if (!a.length && !b.length) return 0;
  if (!a.length) return 1;
  if (!b.length) return -1;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if (i >= a.length) return -1;
    if (i >= b.length) return 1;
    const x = a[i], y = b[i];
    if (x === y) continue;
    const xn = typeof x === 'number', yn = typeof y === 'number';
    if (xn && yn) return x < y ? -1 : 1;
    if (xn) return -1;
    if (yn) return 1;
    return x < y ? -1 : 1;
  }
  return 0;
}

function cmp(a, b) {
  for (const k of ['major', 'minor', 'patch']) if (a[k] !== b[k]) return a[k] < b[k] ? -1 : 1;
  return cmpPre(a.pre, b.pre);
}

export function compare(a, b) {
  const pa = parse(a), pb = parse(b);
  if (!pa || !pb) throw new TypeError(`Invalid version: ${pa ? b : a}`);
  return cmp(pa, pb);
}

const isX = (s) => s === undefined || s === 'x' || s === 'X' || s === '*';
const V = (M, m, p, pre = []) => ({ major: M, minor: m, patch: p, pre });
const C = (op, v) => ({ op, v });
const ANY = [];
const NONE = [C('<', V(0, 0, 0, [0]))];

function parsePartial(s) {
  const m = PARTIAL.exec(s);
  if (!m) throw new TypeError(`Invalid version in range: ${s}`);
  const parts = [m[1], m[2], m[3]];
  let n = 0;
  while (n < 3 && !isX(parts[n])) n++;
  const nums = parts.slice(0, n).map(Number);
  const pre = n === 3 && m[4] !== undefined ? m[4].split('.').map((id) => (/^\d+$/.test(id) ? +id : id)) : [];
  return { n, nums, pre };
}

const fill = ({ nums, pre }) => V(nums[0] ?? 0, nums[1] ?? 0, nums[2] ?? 0, pre);
function bump(nums, i) { // increment part i, zero the rest, prerelease 0
  const out = [0, 0, 0];
  for (let j = 0; j < i; j++) out[j] = nums[j];
  out[i] = nums[i] + 1;
  return V(out[0], out[1], out[2], [0]);
}

function primitive(op, p) {
  if (p.n === 3) return [C(op || '=', fill(p))];
  if (p.n === 0) return op === '<' || op === '>' ? NONE : ANY;
  const lo = fill(p), hi = bump(p.nums, p.n - 1);
  switch (op) {
    case '>': return [C('>=', hi)];
    case '>=': return [C('>=', lo)];
    case '<': return [C('<', V(lo.major, lo.minor, lo.patch, [0]))];
    case '<=': return [C('<', hi)];
    default: return [C('>=', lo), C('<', hi)];
  }
}

function tilde(p) {
  if (p.n === 0) return ANY;
  return [C('>=', fill(p)), C('<', bump(p.nums, p.n === 1 ? 0 : 1))];
}

function caret(p) {
  if (p.n === 0) return ANY;
  let i = p.nums.findIndex((x) => x !== 0);
  if (i === -1) i = p.n - 1;
  return [C('>=', fill(p)), C('<', bump(p.nums, i))];
}

function hyphen(a, b) {
  const out = [];
  if (a.n > 0) out.push(C('>=', fill(a)));
  if (b.n === 3) out.push(C('<=', fill(b)));
  else if (b.n > 0) out.push(C('<', bump(b.nums, b.n - 1)));
  return out;
}

function parseSet(s) {
  s = s.trim();
  if (s === '') return ANY;
  const h = /^(\S+)\s+-\s+(\S+)$/.exec(s);
  if (h) return hyphen(parsePartial(h[1]), parsePartial(h[2]));
  const items = s.replace(/(<=|>=|<|>|=|~|\^)\s+/g, '$1').split(/\s+/);
  const out = [];
  for (const item of items) {
    const m = /^(~|\^|<=|>=|<|>|=)?(.*)$/.exec(item);
    const p = parsePartial(m[2]);
    if (m[1] === '~') out.push(...tilde(p));
    else if (m[1] === '^') out.push(...caret(p));
    else out.push(...primitive(m[1], p));
  }
  return out;
}

function parseRange(range) {
  if (typeof range !== 'string') return null;
  try {
    return range.split('||').map(parseSet);
  } catch {
    return null;
  }
}

function testComp({ op, v }, ver) {
  const c = cmp(ver, v);
  switch (op) {
    case '<': return c < 0;
    case '<=': return c <= 0;
    case '>': return c > 0;
    case '>=': return c >= 0;
    default: return c === 0;
  }
}

function testSet(set, ver) {
  if (!set.every((c) => testComp(c, ver))) return false;
  if (!ver.pre.length) return true;
  return set.some(({ v }) => v.pre.length && v.major === ver.major && v.minor === ver.minor && v.patch === ver.patch);
}

const testRange = (sets, ver) => sets.some((set) => testSet(set, ver));

export function satisfies(version, range) {
  const ver = parse(version), sets = parseRange(range);
  return !!(ver && sets && testRange(sets, ver));
}

export function maxSatisfying(versions, range) {
  const sets = parseRange(range);
  if (!sets) return null;
  let best = null, bestV = null;
  for (const v of versions) {
    const pv = parse(v);
    if (pv && testRange(sets, pv) && (!bestV || cmp(pv, bestV) > 0)) { best = v; bestV = pv; }
  }
  return best;
}
