"""Tests for analog.core.stats (STANDARDS.md section 5 published values and section 6 procedures)."""

from __future__ import annotations

import numpy as np
import pytest

from analog.core import stats as st

SEED = 20261114


# ---------------------------------------------------------------- Wilson

def test_wilson_zero_of_ten():
    """Wilson 95% for (0, 10) = [0, 0.2775] [1e-4]."""
    lo, hi = st.wilson(0, 10)
    assert lo == pytest.approx(0.0, abs=1e-4)
    assert hi == pytest.approx(0.2775, abs=1e-4)


def test_wilson_five_of_ten():
    """Wilson 95% for (5, 10) = [0.2366, 0.7634] [1e-4]."""
    lo, hi = st.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4)
    assert hi == pytest.approx(0.7634, abs=1e-4)


def test_wilson_null_and_invalid_inputs():
    """n = 0 -> None; k outside [0, n] -> ValueError."""
    assert st.wilson(0, 0) is None
    with pytest.raises(ValueError):
        st.wilson(11, 10)


# ---------------------------------------------------------------- AUC

def test_auc_perfect_separation_is_one():
    """Every positive score above every negative score -> AUC = 1."""
    assert st.auc([3.0, 4.0, 5.0], [0.0, 1.0, 2.0]) == pytest.approx(1.0, abs=1e-12)


def test_auc_identical_samples_is_half():
    """Identical samples -> AUC = 0.5 (ties count 1/2)."""
    assert st.auc([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(0.5, abs=1e-12)


def test_auc_all_tied_is_half_and_reversed_is_zero():
    """All scores tied -> 0.5; fully reversed separation -> 0."""
    assert st.auc([2.0, 2.0], [2.0, 2.0, 2.0]) == pytest.approx(0.5, abs=1e-12)
    assert st.auc([0.0, 1.0], [2.0, 3.0]) == pytest.approx(0.0, abs=1e-12)


def test_auc_empty_is_null_and_nan_rejected():
    """Empty class -> None; NaN score -> ValueError."""
    assert st.auc([], [1.0]) is None
    with pytest.raises(ValueError):
        st.auc([np.nan, 1.0], [0.0])


def test_auc_matches_brute_force_pair_count():
    """Mann-Whitney AUC equals the brute-force fraction of (pos, neg) pairs with ties counted 1/2."""
    rng = np.random.default_rng(SEED)
    for _ in range(50):
        pos = rng.integers(0, 6, size=int(rng.integers(1, 15))).astype(float)
        neg = rng.integers(0, 6, size=int(rng.integers(1, 15))).astype(float)
        brute = 0.0
        for p in pos:
            for q in neg:
                brute += 1.0 if p > q else (0.5 if p == q else 0.0)
        brute /= pos.size * neg.size
        assert st.auc(pos, neg) == pytest.approx(brute, abs=1e-12)


# ---------------------------------------------------------------- Spearman / robust sigma

def test_spearman_monotone_transform_is_one():
    """Spearman of a monotone transform = 1 [1e-9]."""
    rng = np.random.default_rng(SEED)
    x = rng.normal(size=200)
    assert st.spearman(x, np.exp(x) + 3.0) == pytest.approx(1.0, abs=1e-9)
    assert st.spearman(x, -(x**3)) == pytest.approx(-1.0, abs=1e-9)


def test_spearman_drops_nonfinite_and_null_on_constant():
    """Non-finite pairs are dropped; a constant ranking gives None."""
    x = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
    y = np.array([2.0, 4.0, 9.0, 8.0, 10.0])
    assert st.spearman(x, y) == pytest.approx(1.0, abs=1e-12)
    assert st.spearman([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


def test_robust_sigma_of_standard_normal():
    """robust_sigma of N(0, 1) with n = 100000 = 1 [0.02]."""
    rng = np.random.default_rng(SEED)
    x = rng.standard_normal(100000)
    assert st.robust_sigma(x) == pytest.approx(1.0, abs=0.02)


def test_robust_sigma_resists_outlier_and_null_on_empty():
    """One huge outlier barely moves the MAD-based sigma; no finite value -> None."""
    x = np.concatenate([np.linspace(-1, 1, 101), [1e9]])
    base = st.robust_sigma(np.linspace(-1, 1, 101))
    assert st.robust_sigma(x) == pytest.approx(base, rel=0.05)
    assert st.robust_sigma([np.nan]) is None


# ---------------------------------------------------------------- pair-level validation

def _separable_pairs(seed: int = SEED, noise: float = 0.3):
    """15 regions in 5 classes (3 each). Region feature x = 3 * class + N(0, noise); score = -|x_a - x_b|.
    Same-class pairs have small distance, so the AUC is high (exactly 1 when noise is small)."""
    rng = np.random.default_rng(seed)
    classes = [f"c{k}" for k in range(5)]
    region_class = [classes[r // 3] for r in range(15)]
    x = np.array([3.0 * (r // 3) + rng.normal(0, noise) for r in range(15)])
    a, b, s = [], [], []
    for i in range(15):
        for j in range(i + 1, 15):
            a.append(i)
            b.append(j)
            s.append(-abs(x[i] - x[j]))
    return np.array(a), np.array(b), np.array(s), region_class


def test_permutation_p_separable_is_minimal_for_observed_auc_one():
    """Strongly separated classes: observed AUC is high and the permutation p is small."""
    a, b, s, rc = _separable_pairs()
    out = st.permutation_p_by_labels(a, b, s, rc, B=999, seed=SEED)
    assert out["auc_obs"] > 0.9
    assert out["p"] is not None
    assert out["p"] <= 0.01 + 1e-12
    assert out["p"] * 1000 == pytest.approx(round(out["p"] * 1000), abs=1e-9)  # p = (1 + count) / (1 + B)


def test_permutation_p_random_scores_is_not_significant():
    """Scores unrelated to the classes: the permutation p is not small (fixed seed)."""
    rng = np.random.default_rng(SEED)
    a, b, _, rc = _separable_pairs()
    s = rng.normal(size=a.size)
    out = st.permutation_p_by_labels(a, b, s, rc, B=999, seed=SEED)
    assert out["p"] is not None
    assert out["p"] > 0.05


def test_permutation_drops_null_scores_and_counts_them():
    """NaN (null) distances are excluded and reported, not silently zeroed."""
    a, b, s, rc = _separable_pairs()
    s = s.copy()
    s[:5] = np.nan
    out = st.permutation_p_by_labels(a, b, s, rc, B=99, seed=SEED)
    assert out["n_null_pairs"] == 5
    assert out["n_pairs"] == a.size - 5


def test_bootstrap_ci_brackets_observed_auc():
    """Region bootstrap CI (B = 2000, percentile) contains the observed AUC and is ordered."""
    a, b, s, rc = _separable_pairs(noise=1.5)
    out = st.bootstrap_ci_by_regions(a, b, s, rc, B=2000, seed=SEED)
    assert out["n_valid"] + out["n_invalid"] == 2000
    assert out["ci_lo"] <= out["auc_obs"] <= out["ci_hi"]
    assert 0.0 <= out["ci_lo"] < out["ci_hi"] <= 1.0


def test_bootstrap_ci_degenerate_when_perfect_separation():
    """Perfect separation (AUC = 1 for every resample) -> the percentile CI collapses to [1, 1]."""
    a, b, s, rc = _separable_pairs(noise=0.3)
    out = st.bootstrap_ci_by_regions(a, b, s, rc, B=200, seed=SEED)
    assert out["auc_obs"] == pytest.approx(1.0, abs=1e-12)
    assert out["ci_lo"] == pytest.approx(1.0, abs=1e-12)
    assert out["ci_hi"] == pytest.approx(1.0, abs=1e-12)


def test_bootstrap_ci_null_when_single_class():
    """One class only -> AUC undefined -> CI is null, not a number."""
    a, b, s, _ = _separable_pairs()
    out = st.bootstrap_ci_by_regions(a, b, s, ["x"] * 15, B=20, seed=SEED)
    assert out["auc_obs"] is None
    assert out["ci_lo"] is None


def test_bootstrap_excludes_self_copy_pairs_hand_value():
    """Self-copy pairs (a == b, two copies of one original region) are excluded.

    Regions 0 and 1 are class A, region 2 is class B. Pairs (score = -D):
      (0, 1) positive, -2.0      (0, 2) negative, -1.0      (1, 2) negative, -1.0      (0, 0) self-copy, 0.0
    Without the self pair the only positive (-2.0) is below both negatives, so AUC = 0 for every draw:
    auc_obs = 0 and every valid bootstrap draw gives 0, hence CI = [0, 0].
    Counting the self pair with multiplicity c_0^2 would instead give AUC([-2, 0], [-1, -1]) = (0 + 2) / 4 = 0.5
    and a CI above 0 (checked below as the trap value)."""
    a = np.array([0, 0, 1, 0])
    b = np.array([1, 2, 2, 0])
    s = np.array([-2.0, -1.0, -1.0, 0.0])
    rc = ["A", "A", "B"]
    assert st.auc([-2.0, 0.0], [-1.0, -1.0]) == pytest.approx(0.5, abs=1e-12)  # the trap value
    out = st.bootstrap_ci_by_regions(a, b, s, rc, B=200, seed=SEED)
    assert out["n_self_pairs_excluded"] == 1
    assert out["n_pairs"] == 3
    assert out["n_valid"] > 0
    assert out["auc_obs"] == pytest.approx(0.0, abs=1e-12)
    assert out["ci_lo"] == pytest.approx(0.0, abs=1e-12)
    assert out["ci_hi"] == pytest.approx(0.0, abs=1e-12)


def test_permutation_excludes_self_copy_pairs_hand_value():
    """Same construction as the bootstrap hand-value test: regions 0, 1 class A; region 2 class B; pairs
    (0,1)=-2.0 positive, (0,2)=-1.0 and (1,2)=-1.0 negative, (0,0)=0.0 self copy.

    Without the self pair: observed AUC = 0. The label permutations give only three distinct arrangements of
    {A, A, B} (B on region 0, 1 or 2), with AUC 0.75, 0.75 and 0. Every permuted AUC is >= 0, so
    p = (1 + B) / (1 + B) = 1.0 for any seed, and no permutation is undefined.
    Counting the self pair would give observed AUC([-2, 0], [-1, -1]) = 0.5 (the trap value, asserted)."""
    a = np.array([0, 0, 1, 0])
    b = np.array([1, 2, 2, 0])
    s = np.array([-2.0, -1.0, -1.0, 0.0])
    rc = ["A", "A", "B"]
    assert st.auc([-2.0, 0.0], [-1.0, -1.0]) == pytest.approx(0.5, abs=1e-12)  # the trap value
    out = st.permutation_p_by_labels(a, b, s, rc, B=199, seed=SEED)
    assert out["n_self_pairs_excluded"] == 1
    assert out["n_pairs"] == 3
    assert out["n_undefined_perm"] == 0
    assert out["auc_obs"] == pytest.approx(0.0, abs=1e-12)
    assert out["p"] == pytest.approx(1.0, abs=1e-12)
