"""Exact nearest twins on the frozen v1.3 feature space (STANDARDS 10.14, part P-N). Pure numpy/scipy, no I/O.

The distance of STANDARDS section 4 with equal weights w_k = 1 over the K in-distance features is

    D(a, b) = sqrt( sum_k ((a_k - b_k) / sigma_k)^2 / K ) = ||z_a - z_b||_2 / sqrt(K),   z_k = x_k / sigma_k.

So D is a Euclidean distance in the standardised space, and a scipy cKDTree gives exact neighbours and ties.
Ties are broken by row index (ascending), the same order a stable sort by (D, index) gives.

Exactness: the tree returns the Euclidean distance, which can differ from the formula value by ~1e-16. ``knn``
therefore collects every point inside a radius that is a hair larger than the k-th tree distance, computes D exactly
by the formula, and sorts by (D, index). Every true top-k point lies inside that radius, so the result is the brute
force result (``brute_knn`` below implements the STANDARDS formula directly and is the reference for the tests).

NaN: rows with a NaN in any in-distance feature are not representable here. Callers drop them with ``valid_rows``
and report the count (STANDARDS 10.14). ``knn`` and ``ties`` raise on NaN queries.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.spatial import cKDTree

REL_MARGIN = 1e-9   # radius margin on the tree distance, relative
ABS_MARGIN = 1e-12  # radius margin on the tree distance, absolute


def standardise(X: Sequence | np.ndarray, sigma: Sequence | np.ndarray) -> np.ndarray:
    """z_k = x_k / sigma_k. X has shape (n, K) or (K,); sigma has shape (K,). NaN is kept as NaN.

    Raises ValueError when a sigma is not finite and > 0 (a missing sigma must never be guessed).
    """
    s = np.asarray(sigma, dtype=float)
    if s.ndim != 1 or not np.all(np.isfinite(s)) or np.any(s <= 0.0):
        raise ValueError("sigma must be a 1-D vector of finite values > 0")
    X = np.asarray(X, dtype=float)
    if X.shape[-1] != s.shape[0]:
        raise ValueError(f"X has {X.shape[-1]} features, sigma has {s.shape[0]}")
    return X / s


def valid_rows(Z: np.ndarray) -> np.ndarray:
    """Boolean mask of rows with no NaN (the rows that may enter the tree)."""
    Z = np.asarray(Z, dtype=float)
    if Z.ndim == 1:
        Z = Z[None, :]
    return ~np.isnan(Z).any(axis=1)


def build_tree(Z_earth: np.ndarray) -> cKDTree:
    """cKDTree over the standardised pool rows. Raises when a row has NaN (drop them first with valid_rows)."""
    Z = np.asarray(Z_earth, dtype=float)
    if Z.ndim != 2 or Z.shape[0] == 0:
        raise ValueError("build_tree needs a non-empty (n, K) array")
    if np.isnan(Z).any():
        raise ValueError("NaN rows must be excluded before build_tree (see valid_rows)")
    return cKDTree(Z)


def _k_of(tree: cKDTree) -> int:
    return int(tree.data.shape[1])


def _exact_d(tree: cKDTree, zq: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """D = ||z_q - z_i|| / sqrt(K) for the tree rows idx (formula value, used for every reported distance)."""
    diff = tree.data[idx] - zq
    return np.sqrt(np.einsum("ij,ij->i", diff, diff)) / math.sqrt(_k_of(tree))


def _check_query(zq: np.ndarray, K: int) -> np.ndarray:
    z = np.asarray(zq, dtype=float).reshape(-1)
    if z.shape[0] != K:
        raise ValueError(f"query has {z.shape[0]} features, tree has {K}")
    if np.isnan(z).any():
        raise ValueError("query contains NaN (no distance is defined; the caller must skip it)")
    return z


def knn(tree: cKDTree, Zq: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Exact k nearest rows for one or many queries, ties broken by row index.

    Zq: (K,) or (m, K) standardised queries. Returns (idx, D): idx int64 and D float64, both shaped (m, k_eff) (or
    (k_eff,) for a single query), with k_eff = min(k, number of tree rows). D is ascending along each row.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    K = _k_of(tree)
    single = np.asarray(Zq).ndim == 1
    Q = np.asarray(Zq, dtype=float).reshape(-1, K)
    k_eff = min(int(k), int(tree.n))
    out_i = np.empty((Q.shape[0], k_eff), dtype=np.int64)
    out_d = np.empty((Q.shape[0], k_eff), dtype=float)
    for row, zq in enumerate(Q):
        zq = _check_query(zq, K)
        d_tree, _ = tree.query(zq, k=k_eff)
        kth = float(np.atleast_1d(d_tree)[-1])
        radius = kth * (1.0 + REL_MARGIN) + ABS_MARGIN
        cand = np.asarray(tree.query_ball_point(zq, r=radius), dtype=np.int64)
        D = _exact_d(tree, zq, cand)
        order = np.lexsort((cand, D))[:k_eff]
        out_i[row] = cand[order]
        out_d[row] = D[order]
    if single:
        return out_i[0], out_d[0]
    return out_i, out_d


def ties(tree: cKDTree, zq: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """Pool rows whose D to the query is <= threshold (the tie set), sorted by (D, index).

    Candidates come from query_ball_point(r = threshold * sqrt(K)) (with a hair of margin); the exact formula then
    keeps D <= threshold. An empty tie set means the nearest twin is farther than the noise threshold (the Earth gap).
    """
    K = _k_of(tree)
    z = _check_query(zq, K)
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("threshold must be finite and >= 0")
    r = threshold * math.sqrt(K) * (1.0 + REL_MARGIN) + ABS_MARGIN
    cand = np.asarray(tree.query_ball_point(z, r=r), dtype=np.int64)
    if cand.size == 0:
        return cand, np.empty(0, dtype=float)
    D = _exact_d(tree, z, cand)
    keep = D <= threshold
    cand, D = cand[keep], D[keep]
    order = np.lexsort((cand, D))
    return cand[order], D[order]


def brute_knn(
    X_pool: np.ndarray, x_q: np.ndarray, sigma: Sequence[float] | np.ndarray, weights: Sequence[float] | np.ndarray,
    k: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Reference: STANDARDS section 4 written out, D = sqrt(sum w ((a-b)/sigma)^2 / sum w), ties by index.

    X_pool: (n, K) raw feature values with no NaN; x_q: (K,) raw query (no NaN). Returns (idx, D) of the k smallest.
    """
    X = np.asarray(X_pool, dtype=float)
    q = np.asarray(x_q, dtype=float).reshape(-1)
    s = np.asarray(sigma, dtype=float)
    w = np.asarray(weights, dtype=float)
    if np.isnan(X).any() or np.isnan(q).any():
        raise ValueError("brute_knn needs complete rows")
    D = np.sqrt(np.sum(w * ((X - q) / s) ** 2, axis=1) / np.sum(w))
    order = np.lexsort((np.arange(X.shape[0]), D))[: min(k, X.shape[0])]
    return order.astype(np.int64), D[order]
