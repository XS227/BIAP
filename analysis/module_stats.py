"""Small, dependency-free statistics used by the Iran modules (no numpy in the FIN venv path)."""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence


def clean(values: Iterable) -> list[float]:
    out = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def quantile(sorted_vals: Sequence[float], q: float) -> Optional[float]:
    n = len(sorted_vals)
    if n == 0:
        return None
    pos = (n - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def describe(values: Iterable) -> dict:
    v = sorted(clean(values))
    n = len(v)
    if n == 0:
        return {"n": 0}
    mean = sum(v) / n
    var = sum((x - mean) ** 2 for x in v) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(var)
    skew = (sum((x - mean) ** 3 for x in v) / n) / (std ** 3) if std > 0 and n > 2 else 0.0
    return {"n": n, "mean": mean, "median": quantile(v, 0.5), "std": std, "min": v[0], "max": v[-1],
            "q1": quantile(v, 0.25), "q3": quantile(v, 0.75), "p05": quantile(v, 0.05), "p95": quantile(v, 0.95), "skew": skew}


def histogram(values: Iterable, bins: int = 12, *, lo: Optional[float] = None, hi: Optional[float] = None) -> dict:
    """Equal-width histogram; values outside [lo, hi] are counted in ``clipped`` (not silently dropped)."""
    v = sorted(clean(values))
    if not v:
        return {"bins": [], "clipped": 0, "n": 0}
    lo = v[0] if lo is None else lo
    hi = v[-1] if hi is None else hi
    if hi <= lo:
        return {"bins": [{"from": lo, "to": hi, "count": len(v)}], "clipped": 0, "n": len(v)}
    width = (hi - lo) / bins
    counts = [0] * bins
    clipped = 0
    for x in v:
        if x < lo or x > hi:
            clipped += 1
            continue
        idx = min(bins - 1, int((x - lo) / width))
        counts[idx] += 1
    return {"bins": [{"from": lo + i * width, "to": lo + (i + 1) * width, "count": c} for i, c in enumerate(counts)],
            "clipped": clipped, "n": len(v)}


def pearson(xs: Sequence, ys: Sequence) -> Optional[float]:
    pairs = [(float(a), float(b)) for a, b in zip(xs, ys) if a is not None and b is not None
             and math.isfinite(float(a)) and math.isfinite(float(b))]
    n = len(pairs)
    if n < 5:
        return None
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    sxx = sum((a - mx) ** 2 for a, _ in pairs)
    syy = sum((b - my) ** 2 for _, b in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in pairs) / math.sqrt(sxx * syy)


def _ranks(values: Sequence[float]) -> list[float]:
    """Average ranks (ties share the mean rank), 1-based."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: Sequence, ys: Sequence) -> Optional[float]:
    """Rank correlation: one extreme value cannot dominate it the way it dominates Pearson."""
    pairs = [(float(a), float(b)) for a, b in zip(xs, ys) if a is not None and b is not None
             and math.isfinite(float(a)) and math.isfinite(float(b))]
    if len(pairs) < 5:
        return None
    return pearson(_ranks([a for a, _ in pairs]), _ranks([b for _, b in pairs]))


def percentile_rank(sorted_vals: Sequence[float], x: float) -> Optional[float]:
    n = len(sorted_vals)
    if n == 0:
        return None
    below = sum(1 for v in sorted_vals if v < x)
    equal = sum(1 for v in sorted_vals if v == x)
    return (below + 0.5 * equal) / n


def iqr_outlier(sorted_vals: Sequence[float], x: float, k: float = 1.5) -> Optional[str]:
    q1, q3 = quantile(sorted_vals, 0.25), quantile(sorted_vals, 0.75)
    if q1 is None or q3 is None or len(sorted_vals) < 8:
        return None
    iqr = q3 - q1
    if x < q1 - k * iqr:
        return "low"
    if x > q3 + k * iqr:
        return "high"
    return None


def mad_zscores(values: Sequence[float]) -> list[Optional[float]]:
    """Robust z-score 0.6745*(x-median)/MAD; None when MAD is 0."""
    v = clean(values)
    if len(v) < 5:
        return [None] * len(values)
    med = quantile(sorted(v), 0.5)
    mad = quantile(sorted(abs(x - med) for x in v), 0.5)
    if not mad:
        return [None] * len(values)
    return [0.6745 * (float(x) - med) / mad for x in values]


def linear_fit(ys: Sequence[float]) -> tuple[float, float, float]:
    """OLS of y on index 0..n-1 -> (intercept, slope, residual_std)."""
    n = len(ys)
    xs = list(range(n))
    mx, my = (n - 1) / 2, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    rstd = math.sqrt(sum(r * r for r in resid) / max(1, n - 2))
    return intercept, slope, rstd
