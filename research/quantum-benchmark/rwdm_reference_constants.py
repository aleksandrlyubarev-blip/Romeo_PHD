#!/usr/bin/env python3
"""Executable reference fixture for the RWDM / 8Li->6Li LiF problem.

Golden constants and closed-form G(beta0*t) models extracted from the three
experimental/theory papers on polarization transfer 8Li->6Li in LiF, for use
as validation anchors of the RWDM-baseline code (see
docs/article-comparison-2009-2014-2021.md and
docs/quantum-benchmark-rwdm-lif.md).

Sources (short keys used below):
  AMR2009  = Dzheparov, Gulko, Ermakov, Lyubarev, Stepanov, Trostin,
             Appl. Magn. Reson. 35, 411-420 (2009).
  PAN2014  = Abov, Gulko, Dzheparov, Ermakov, Lvov, Lyubarev,
             Phys. At. Nucl. 77, 682-694 (2014); DOI 10.1134/S1063778814050032.
  AMR2021  = Dzheparov, Gulko, Lvov, Appl. Magn. Reson. 52, 805-829 (2021).

CANONICAL NORMALIZATION (decided for this project):
  * beta0 (canonical) = 1.122 * beta0G = 12.15 s^-1 at c = 10 %.  Use THIS.
  * beta0G = 10.80 s^-1 is the LEGACY Gaussian estimate (AMR2009 Table 1,
    equal to PAN2014 beta0G). It is NOT beta0. Never mix the two on one axis.
  * The 1.122 factor (PAN2014 Eq. 13) accounts for the non-Gaussian
    cross-relaxation line shape and local-field correlations.

Every entry carries: value, unit, source, and a tolerance (`rtol` relative or
`atol` absolute) intended for regression tests. Pure standard library; run the
tests with:  python3 -m unittest test_rwdm_reference_constants
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Const:
    """A single golden constant with provenance and a test tolerance."""

    value: float
    unit: str
    source: str
    note: str = ""
    rtol: Optional[float] = None  # relative tolerance for regression checks
    atol: Optional[float] = None  # absolute tolerance (used if rtol is None)

    def close(self, x: float) -> bool:
        if self.rtol is not None:
            return abs(x - self.value) <= self.rtol * abs(self.value)
        if self.atol is not None:
            return abs(x - self.value) <= self.atol
        return x == self.value


# ---------------------------------------------------------------------------
# 1. Universal constants (identical in AMR2009 and PAN2014)
# ---------------------------------------------------------------------------

XI = Const(
    3.0, "dimensionless", "AMR2009/PAN2014",
    "xi = I(I+1)/(S(S+1)); I(8Li)=2, S(6Li)=1. Return-rate asymmetry factor.",
    atol=0.0,
)
G_FACTOR_6LI = Const(0.822047, "dimensionless", "PAN2014", "g-factor of 6Li", rtol=1e-6)
G_FACTOR_8LI = Const(0.82670, "dimensionless", "PAN2014", "g-factor of 8Li", atol=1e-5)
DELTA_G_OVER_G = Const(0.0057, "dimensionless", "PAN2014", "(g8-g6)/g6", atol=1e-4)
R0_ANGSTROM = Const(2.85, "angstrom", "AMR2021", "nearest Li-Li distance in LiF", atol=0.01)
MU_BETA0_TAU = Const(5.11, "dimensionless", "AMR2009/PAN2014", "matching cond. Eq.(8)/(9)", atol=0.01)
PHI = Const(2.09, "dimensionless", "AMR2009/PAN2014", "from w_ij(r->inf), Eq.(9)", atol=0.01)
ALPHA_200G = Const(0.0147, "dimensionless", "AMR2009/PAN2014", "alpha(200 G), tabulated vs w0/w1", atol=1e-4)
LAMBDA_8LI = Const(0.8268, "1/s", "PAN2014", "8Li decay rate, T1/2=0.84 s", atol=1e-4)
LAMBDA_20F = Const(0.063, "1/s", "PAN2014", "20F decay rate", atol=1e-3)

# Foerster coefficient beta0 = (256/243)*(r0^3/Omega)^2 * pi^3 * c^2 * w0
# (PAN2014 Eq. 7). For the FCC lithium sublattice (r0^3/Omega)^2 = 2, hence
# beta0 = (512/243)*pi^3 * c^2 * w0 = 65.33 * c^2 * w0 (matches AMR2009 p.413).
FCC_R0CUBE_OVER_OMEGA_SQ = Const(2.0, "dimensionless", "geometry(FCC)", "(r0^3/Omega)^2 for FCC Li sublattice", atol=1e-9)
FOERSTER_COEF_FCC = Const(
    (512.0 / 243.0) * math.pi ** 3, "dimensionless", "PAN2014 Eq.7 + FCC",
    "coefficient K in beta0 = K*c^2*w0; K=(512/243)pi^3=65.33", rtol=1e-6,
)


# ---------------------------------------------------------------------------
# 2. beta0 normalization (CANONICAL vs LEGACY)
# ---------------------------------------------------------------------------

BETA0_CORRECTION_FACTOR = Const(
    1.122, "dimensionless", "PAN2014 Eq.13",
    "beta0 = 1.122 * beta0G; non-Gaussian line shape + local-field correlations.",
    atol=1e-3,
)

# LEGACY Gaussian estimate. Do NOT use as beta0.
BETA0G_LEGACY_C10 = Const(
    10.80, "1/s", "AMR2009 Table 1 (c=10.06%, 200 G, [111])",
    "LEGACY Gaussian beta0G at c=10%. PAN2014 Eq.13 gives 10.83 for the same "
    "quantity; the ~0.3% gap is the 2009/2014 difference in beta0G itself.",
    atol=0.05,
)
BETA0G_2014_C10 = Const(10.83, "1/s", "PAN2014 Eq.13", "beta0G at c=10.06% (2014 value)", atol=0.05)

# CANONICAL field scale. Use THIS.
BETA0_CANONICAL_C10 = Const(
    12.15, "1/s", "PAN2014 Eq.13 (1.122 * 10.83)",
    "CANONICAL beta0 at c=10%. 1.122*10.80(legacy)=12.12; 1.122*10.83(2014)=12.15. "
    "Tolerance covers both provenances.",
    atol=0.05,
)

# beta0G(c) from PAN2014 Eq.(13) (Gaussian estimates at the three concentrations).
BETA0G_2014 = {
    0.1006: Const(10.83, "1/s", "PAN2014 Eq.13", "beta0G(c=0.1006)", atol=0.02),
    0.053: Const(3.057, "1/s", "PAN2014 Eq.13", "beta0G(c=0.053)", atol=0.005),
    0.033: Const(1.193, "1/s", "PAN2014 Eq.13", "beta0G(c=0.033)", atol=0.005),
}


def beta0G_to_beta0(beta0G: float) -> float:
    """Convert a LEGACY Gaussian beta0G into the CANONICAL beta0 (PAN2014)."""
    return BETA0_CORRECTION_FACTOR.value * beta0G


def beta0_from_c(c: float, K: float = 1067.0) -> float:
    """Foerster scaling beta0 ~ K*c^2 (c as a fraction). K from AMR2009 Table 1.

    Note: this returns the LEGACY-scale beta0G family (K~1067); multiply by
    BETA0_CORRECTION_FACTOR for the canonical beta0.
    """
    return K * c * c


# ---------------------------------------------------------------------------
# 3. AMR2009 Table 1 -- 4 samples at 200 G, [111] (the clean beta0 ~ c^2 set)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Sample2009:
    c: float          # 6Li fraction
    mu: float
    beta0: float      # s^-1 (LEGACY Gaussian scale == beta0G)
    beta1: float      # s^-1
    b1: float         # G(t) fit param (Eq. 7)
    b2: float         # G(t) fit param (Eq. 7)
    a0: float         # limiting asymmetry, %
    chi2_over_N: str

    @property
    def beta1_over_beta0(self) -> float:
        return self.beta1 / self.beta0


# NB: the "beta0" column here is the LEGACY Gaussian scale (beta0G), see docs.
TABLE_2009 = [
    Sample2009(0.0328, 0.726, 1.15, 1.08, 0.051, 0.567, 10.00, "112/98"),
    Sample2009(0.0530, 0.736, 3.00, 2.83, 0.075, 0.234, 9.81, "115/98"),
    Sample2009(0.0881, 0.754, 8.28, 7.81, 0.059, 0.126, 9.31, "58/70"),
    Sample2009(0.1006, 0.761, 10.80, 10.18, 0.054, 0.111, 9.43, "168/98"),
]
TABLE_2009_SOURCE = "AMR2009 Table 1 (200 G, [111])"

# Foerster invariant beta0G/c^2 across the 4 samples (see tests).
BETA0_OVER_C2_2009 = Const(
    1067.0, "1/s", TABLE_2009_SOURCE, "beta0G/c^2, ~const across samples", rtol=0.01,
)

# Legacy beta1/beta0 at 200 G, c=10.06% (used by quantum-benchmark-rwdm-lif.md).
BETA1_OVER_BETA0_LEGACY_200G = Const(
    0.9426, "dimensionless", TABLE_2009_SOURCE,
    "LEGACY beta1/beta0 = 10.18/10.80 at 200 G. Canonical (2014) value is 0.917.",
    atol=1e-3,
)


# ---------------------------------------------------------------------------
# 4. PAN2014 field dependence -- beta1/beta0 at three fields (CANONICAL)
# ---------------------------------------------------------------------------
# PAN2014 Eq.(13): beta1(H) = k(H)*beta0G, beta0 = 1.122*beta0G, so
# beta1/beta0 = k(H)/1.122.
BETA1_REL_BETA0G_2014 = {
    0.200: 1.029,    # H0 in kG
    0.691: 0.4341,
    1.210: 0.09389,
}

BETA1_OVER_BETA0_2014 = {
    0.200: Const(1.029 / 1.122, "dimensionless", "PAN2014 Eq.13", "beta1/beta0 @200 G", atol=2e-3),
    0.691: Const(0.4341 / 1.122, "dimensionless", "PAN2014 Eq.13", "beta1/beta0 @691 G", atol=2e-3),
    1.210: Const(0.09389 / 1.122, "dimensionless", "PAN2014 Eq.13", "beta1/beta0 @1210 G", atol=2e-3),
}


# ---------------------------------------------------------------------------
# 5. Two closed forms of the correction factor G(beta0*t)
# ---------------------------------------------------------------------------

def g_2009(t: float, beta0: float, beta1: float, b1: float, b2: float,
           alpha: float = ALPHA_200G.value) -> float:
    """AMR2009 Eq.(7): simple 2-parameter correction factor.

        G = 1 - [(0.125+alpha)*beta1*t - b1*(beta1*t)^2] / (1 + b2*beta0*t)^3
    """
    y = beta1 * t
    x = beta0 * t
    return 1.0 - ((0.125 + alpha) * y - b1 * y * y) / (1.0 + b2 * x) ** 3


@dataclass(frozen=True)
class G2014Params:
    """PAN2014 Eq.(12) parameters for one (c, H0) pair (Table + relations 13)."""

    a1: float
    b: float
    c1: float
    d0: float
    f0: float
    f1: float
    f2: float
    b0: float
    b1: float
    d1: float = 1.0
    h: float = 0.1


# PAN2014 "Table" keyed by (c, H0[kG]).
G2014_TABLE = {
    (0.1, 0.2): G2014Params(57.13, 3.0, 0.08185, 17.88, 10.65, -1.170, 0.2152, -8.953, 41.55),
    (0.1, 0.691): G2014Params(84.61, 3.824, 0.4875, -1.376, 3.473, -0.1920, 0.1244, -1.404, 1.989),
    (0.1, 1.21): G2014Params(113.2, 19.93, 0.3928, -1042.0, 748.9, -47.71, 1.018, 7461.0, -40120.0),
    (0.053, 0.2): G2014Params(64.29, 3.0, 0.04227, 4.343, 8.024, -1.054, 0.1905, -0.1340, 6.356),
    (0.053, 0.691): G2014Params(82.72, 3.034, 0.3585, 4.218, 6.893, -0.8265, 0.1454, -2.334, 6.572),
    (0.053, 1.21): G2014Params(98.37, 23.22, 0.6161, -48.99, 181.4, -9.401, 0.1683, -536.3, 396.5),
    (0.033, 0.2): G2014Params(47.39, 11.81, 0.2797, 957.0, 144.9, -25.06, 2.806, 20.95, 89.60),
    (0.033, 0.691): G2014Params(44.11, 4.348, 0.0, 13.19, 13.17, -1.270, 0.1913, -2.423, 12.38),
    (0.033, 1.21): G2014Params(72.79, 25.75, 0.6101, -61.76, 122.5, -6.729, 0.1295, 22.64, -416.7),
}
G2014_TABLE_SOURCE = "PAN2014 Eq.(12) + Table (d1=1, h=0.1 common)"


def g_2014(x: float, p: G2014Params) -> float:
    """PAN2014 Eq.(12): extended correction factor. Argument x = beta0*t.

    Not intended for (1+xi)*w0*t < 1 (short-time linear regime).
    """
    sx = math.sqrt(x)
    num = -p.b0 * sx + (0.138 + p.b1) * x - p.d0 * x * sx - p.d1 * x * x
    den = (1.0 + p.f0 * sx + p.f1 * x + p.f2 * x * sx) ** 2
    lognorm = p.c1 * math.exp(
        -0.5 * ((math.log(x * x + p.h * p.h) - math.log(p.a1 * p.a1 + p.h * p.h)) / math.log(p.b)) ** 2
    )
    return 1.0 - num / den + lognorm


# ---------------------------------------------------------------------------
# 6. The beta0*t = 30..108 window -- a documented benchmark/outlier, NOT a
#    requirement that the simulation reproduce the semi-phenomenological form.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OutlierWindow:
    beta0_t_lo: float
    beta0_t_hi: float
    kind: str
    source: str
    note: str
    outlier_amplitude_vs_eq9: float  # observed excess relative to Eq.(9) prediction


# PAN2014: max (P00 - Pdiff)/Pdiff is "nearly twice" the Eq.(9) prediction, and
# the pre-asymptotic stage is long. The direct-supercell vs F(t)*G(t)
# discrepancy in quantum-benchmark-rwdm-lif.md is this same outlier. It is an
# OPEN physics question (does full quantum dynamics explain it), NOT a target
# the RWDM baseline must match.
OUTLIER_WINDOW = OutlierWindow(
    beta0_t_lo=30.0,
    beta0_t_hi=108.0,
    kind="benchmark_outlier",           # explicitly not "equality_requirement"
    source="PAN2014 Results/Discussion; docs/quantum-benchmark-rwdm-lif.md",
    note=(
        "Excess of P00 over the diffusion/Foerster asymptotic in the transition "
        "region. Marked as an open-question benchmark; simulations are compared "
        "against it, not required to reproduce the phenomenological F(t)*G(t)."
    ),
    outlier_amplitude_vs_eq9=2.0,       # ~2x the Eq.(9) predicted amplitude
)


if __name__ == "__main__":
    print("RWDM reference constants (canonical beta0 = 1.122*beta0G):")
    print(f"  beta0 (c=10%, canonical) = {BETA0_CANONICAL_C10.value} {BETA0_CANONICAL_C10.unit}")
    print(f"  beta0G  (c=10%, LEGACY)  = {BETA0G_LEGACY_C10.value} {BETA0G_LEGACY_C10.unit}")
    print(f"  Foerster K (FCC)         = {FOERSTER_COEF_FCC.value:.3f}")
    print(f"  beta1/beta0 @200/691/1210 G = "
          + ", ".join(f"{BETA1_OVER_BETA0_2014[h].value:.4f}" for h in (0.2, 0.691, 1.21)))
    print(f"  outlier window beta0*t in [{OUTLIER_WINDOW.beta0_t_lo}, "
          f"{OUTLIER_WINDOW.beta0_t_hi}] ({OUTLIER_WINDOW.kind})")
    p = G2014_TABLE[(0.1, 0.2)]
    peak = max(g_2014(x, p) for x in (30, 40, 50, 60, 80, 108))
    print(f"  G_2014(c=10%,200G) peak in window ~ {peak:.3f}")
