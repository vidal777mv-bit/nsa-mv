"""Validation statistics (STANDARDS.md sections 5 and 6).

Pair-level functions take integer region indices ``pair_a``, ``pair_b`` (0..R-1), a float ``score``
per pair (score = -D, NaN = null distance, dropped and counted), and ``region_class`` (length R).
A pair is positive when both of its regions carry the same class.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.stats import rankdata

MAD_TO_SIGMA = 1.4826


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion.

    Formula: p = k/n; centre = (p + z^2/(2n)) / (1 + z^2/n); half = z sqrt(p(1-p)/n + z^2/(4n^2)) / (1 + z^2/n);
    interval = [centre - half, centre + half], clipped to [0, 1].
    Returns None when n == 0. Raises ValueError when k is outside [0, n].
    """
    if n == 0:
        return None
    if k < 0 or k > n:
        raise ValueError(f"k={k} outside [0, n={n}]")
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _auc_grouped(
    group: np.ndarray, n_groups: int, positive: np.ndarray, weights: np.ndarray
) -> float | None:
    """Weighted Mann-Whitney AUC from tie groups (group ids ordered by ascending score).

    Formula: AUC = sum_p w_p ( sum_{n: s_n < s_p} w_n + 0.5 sum_{n: s_n = s_p} w_n ) / (W_pos W_neg),
    evaluated per tie group. Returns None when either class has zero total weight.
    """
    w_pos = np.bincount(group, weights=weights * positive, minlength=n_groups)
    w_neg = np.bincount(group, weights=weights * (~positive), minlength=n_groups)
    total_pos = float(w_pos.sum())
    total_neg = float(w_neg.sum())
    if total_pos <= 0.0 or total_neg <= 0.0:
        return None
    neg_before = np.cumsum(w_neg) - w_neg
    numerator = float(np.sum(w_pos * (neg_before + 0.5 * w_neg)))
    return numerator / (total_pos * total_neg)


def auc(pos_scores: Sequence[float] | np.ndarray, neg_scores: Sequence[float] | np.ndarray) -> float | None:
    """Area under the ROC curve by Mann-Whitney U (ties count 1/2).

    Formula: AUC = P(s_pos > s_neg) + 0.5 P(s_pos = s_neg) over all (pos, neg) pairs.
    Returns None when either sample is empty. Raises ValueError on NaN scores (callers drop null distances).
    """
    pos = np.asarray(pos_scores, dtype=float).ravel()
    neg = np.asarray(neg_scores, dtype=float).ravel()
    if np.isnan(pos).any() or np.isnan(neg).any():
        raise ValueError("NaN scores are not allowed in auc(); drop null distances first")
    if pos.size == 0 or neg.size == 0:
        return None
    scores = np.concatenate([pos, neg])
    uniq, group = np.unique(scores, return_inverse=True)
    positive = np.concatenate([np.ones(pos.size, dtype=bool), np.zeros(neg.size, dtype=bool)])
    return _auc_grouped(group.ravel(), uniq.size, positive, np.ones(scores.size))


def _pair_setup(
    pair_a: np.ndarray,
    pair_b: np.ndarray,
    score: np.ndarray,
    region_class: Sequence[object],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int, int]:
    """Drop null-score pairs and encode classes.

    Returns (a, b, score_kept, class_codes, group, n_groups, n_null) where class_codes are the
    integer codes of region_class and group are tie-group ids of score_kept.
    """
    a = np.asarray(pair_a, dtype=np.int64).ravel()
    b = np.asarray(pair_b, dtype=np.int64).ravel()
    s = np.asarray(score, dtype=float).ravel()
    if not (a.size == b.size == s.size):
        raise ValueError("pair_a, pair_b and score must have the same length")
    keep = np.isfinite(s)
    n_null = int(s.size - keep.sum())
    a, b, s = a[keep], b[keep], s[keep]
    _, codes = np.unique(np.array([str(c) for c in region_class]), return_inverse=True)
    codes = np.asarray(codes).ravel()
    if a.size and (a.min() < 0 or b.min() < 0 or a.max() >= codes.size or b.max() >= codes.size):
        raise ValueError("pair region index outside region_class")
    uniq, group = np.unique(s, return_inverse=True)
    return a, b, s, codes, group.ravel(), uniq.size, n_null


def permutation_p_by_labels(
    pair_a: np.ndarray,
    pair_b: np.ndarray,
    score: np.ndarray,
    region_class: Sequence[object],
    B: int = 9999,
    seed: int = 20261114,
) -> dict[str, object]:
    """Permutation p-value for AUC, permuting region class labels (not pairs).

    Formula: pairs with pair_a == pair_b (self copies) are dropped before everything else, from the observed AUC
    and from every permutation (their count is reported as n_self_pairs_excluded). AUC_obs from the true labels;
    for each of B permutations the class labels are shuffled among regions, pairs are re-labelled, AUC_perm is
    computed; p = (1 + #{AUC_perm >= AUC_obs}) / (1 + B).
    If any permuted AUC is undefined (a single class), p is None and the reason is returned.
    """
    a, b, s, codes, group, n_groups, n_null = _pair_setup(pair_a, pair_b, score, region_class)
    self_pair = a == b
    n_self = int(self_pair.sum())
    a, b, s, group = a[~self_pair], b[~self_pair], s[~self_pair], group[~self_pair]
    result: dict[str, object] = {
        "B": int(B),
        "seed": int(seed),
        "n_pairs": int(s.size),
        "n_null_pairs": n_null,
        "n_self_pairs_excluded": n_self,
    }
    positive = codes[a] == codes[b]
    observed = _auc_grouped(group, n_groups, positive, np.ones(s.size))
    result["auc_obs"] = observed
    if observed is None:
        result.update({"p": None, "n_undefined_perm": None, "reason": "AUC undefined for observed labels"})
        return result

    rng = np.random.default_rng(seed)
    ones = np.ones(s.size)
    exceed = 0
    undefined = 0
    for _ in range(int(B)):
        perm = rng.permutation(codes)
        value = _auc_grouped(group, n_groups, perm[a] == perm[b], ones)
        if value is None:
            undefined += 1
        elif value >= observed:
            exceed += 1
    result["n_undefined_perm"] = undefined
    if undefined:
        result.update({"p": None, "reason": "some permuted AUC undefined (single class)"})
        return result
    result["p"] = (1 + exceed) / (1 + int(B))
    return result


def bootstrap_ci_by_regions(
    pair_a: np.ndarray,
    pair_b: np.ndarray,
    score: np.ndarray,
    region_class: Sequence[object],
    B: int = 2000,
    seed: int = 20261114,
    alpha: float = 0.05,
) -> dict[str, object]:
    """Percentile bootstrap CI for AUC, resampling regions with replacement.

    Formula: pairs with pair_a == pair_b (two copies of the same original region, D = 0) are excluded from the
    observed AUC and from every draw, since they would inflate same-class AUC. Draw R region indices with
    replacement; each region r appears c_r times. The rebuilt pair list holds pair (a, b), a != b, with
    multiplicity c_a * c_b (equivalent to materialising the duplicated pairs). AUC_b is the weighted AUC of that
    list; the CI is the (alpha/2, 1 - alpha/2) percentile of the valid AUC_b values (a draw with one class only
    is skipped and counted in ``n_invalid``). The observed AUC uses the same pair set, so it lies in the CI.
    """
    a, b, s, codes, group, n_groups, n_null = _pair_setup(pair_a, pair_b, score, region_class)
    self_pair = a == b
    n_self = int(self_pair.sum())
    a, b, s, group = a[~self_pair], b[~self_pair], s[~self_pair], group[~self_pair]
    n_regions = codes.size
    positive = codes[a] == codes[b]
    result: dict[str, object] = {
        "B": int(B),
        "seed": int(seed),
        "alpha": float(alpha),
        "n_pairs": int(s.size),
        "n_null_pairs": n_null,
        "n_self_pairs_excluded": n_self,
        "n_regions": int(n_regions),
    }
    observed = _auc_grouped(group, n_groups, positive, np.ones(s.size))
    result["auc_obs"] = observed
    if observed is None:
        result.update({"ci_lo": None, "ci_hi": None, "n_valid": 0, "n_invalid": None})
        return result

    rng = np.random.default_rng(seed)
    values: list[float] = []
    invalid = 0
    for _ in range(int(B)):
        counts = np.bincount(rng.integers(0, n_regions, size=n_regions), minlength=n_regions)
        weights = (counts[a] * counts[b]).astype(float)
        keep = weights > 0
        value = _auc_grouped(group[keep], n_groups, positive[keep], weights[keep])
        if value is None:
            invalid += 1
        else:
            values.append(value)
    result["n_valid"] = len(values)
    result["n_invalid"] = invalid
    if not values:
        result.update({"ci_lo": None, "ci_hi": None})
        return result
    lo, hi = np.percentile(values, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    result.update({"ci_lo": float(lo), "ci_hi": float(hi)})
    return result


def spearman(x: Sequence[float] | np.ndarray, y: Sequence[float] | np.ndarray) -> float | None:
    """Spearman rank correlation with average ranks for ties.

    Formula: rho = Pearson correlation of rank(x) and rank(y). Pairs with a non-finite value are dropped.
    Returns None when fewer than 3 finite pairs remain or either ranking is constant.
    """
    xa = np.asarray(x, dtype=float).ravel()
    ya = np.asarray(y, dtype=float).ravel()
    if xa.size != ya.size:
        raise ValueError("x and y must have the same length")
    keep = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[keep], ya[keep]
    if xa.size < 3:
        return None
    rx = rankdata(xa)
    ry = rankdata(ya)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = math.sqrt(float(np.dot(rx, rx)) * float(np.dot(ry, ry)))
    if denom == 0.0:
        return None
    return float(np.dot(rx, ry) / denom)


def robust_sigma(x: Sequence[float] | np.ndarray) -> float | None:
    """Robust standard deviation from the median absolute deviation.

    Formula: sigma = 1.4826 * median( |x - median(x)| ), non-finite values dropped.
    Returns None when no finite value exists.
    """
    xa = np.asarray(x, dtype=float).ravel()
    xa = xa[np.isfinite(xa)]
    if xa.size == 0:
        return None
    med = float(np.median(xa))
    return float(MAD_TO_SIGMA * np.median(np.abs(xa - med)))
