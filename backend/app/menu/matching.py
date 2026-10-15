"""Match what a customer said or typed to real menu records. Never guess: anything that isn't a clear
single match comes back as ambiguous (with candidates to ask about) or not_found."""
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .models import MenuItem

STRONG, CANDIDATE, MARGIN = 0.86, 0.55, 0.08


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def score(query: str, name: str) -> float:
    q, n = norm(query), norm(name)
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    ratio = SequenceMatcher(None, q, n).ratio()
    qt, nt = set(q.split()), set(n.split())
    overlap = len(qt & nt) / len(qt) if qt else 0
    contained = 0.75 if (q in n or n in q) else 0
    return max(ratio, overlap * 0.8, contained)


@dataclass
class MatchResult:
    status: str
    item: MenuItem | None = None
    candidates: list[MenuItem] = field(default_factory=list)


def match_item(query: str, items: list[MenuItem]) -> MatchResult:
    scored = []
    for it in items:
        names = [it.name, it.name_hi, *it.aliases]
        scored.append((max(score(query, n) for n in names if n), it))
    scored.sort(key=lambda x: -x[0])
    exact = [it for s, it in scored if s == 1.0]
    if len(exact) == 1:
        return MatchResult("matched", exact[0])
    if len(exact) > 1:
        return MatchResult("ambiguous", candidates=exact)
    if not scored or scored[0][0] < CANDIDATE:
        return MatchResult("not_found", candidates=[it for s, it in scored[:3] if s >= 0.4])
    top = scored[0][0]
    close = [it for s, it in scored if s >= CANDIDATE and top - s < MARGIN]
    if top >= STRONG and len(close) == 1:
        return MatchResult("matched", close[0])
    return MatchResult("ambiguous", candidates=[it for s, it in scored if s >= CANDIDATE][:5])


def match_option(query: str, options: list, attr: str = "name"):
    """Pick one variant/add-on by name. Returns (option, ambiguous_candidates)."""
    scored = sorted(((score(query, getattr(o, attr)), o) for o in options), key=lambda x: -x[0])
    exact = [o for s, o in scored if s == 1.0]
    if len(exact) == 1:
        return exact[0], []
    good = [o for s, o in scored if s >= STRONG]
    if len(good) == 1:
        return good[0], []
    return None, [o for s, o in scored if s >= CANDIDATE] or [o for _, o in scored]
