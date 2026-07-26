#!/usr/bin/env python3
"""Unit tests for the RWDM golden-constants fixture.

Pure standard library (unittest). Run:
    python3 -m unittest test_rwdm_reference_constants
or:
    python3 -m unittest discover research/quantum-benchmark

These tests pin the reference constants and closed forms extracted from
AMR2009 / PAN2014 / AMR2021 so that the RWDM-baseline code can be validated
against a single, provenance-tagged source. See
docs/article-comparison-2009-2014-2021.md.
"""

import math
import unittest

import rwdm_reference_constants as R


class TestUniversalConstants(unittest.TestCase):
    def test_xi_return_factor(self):
        # xi = I(I+1)/(S(S+1)) with I=2 (8Li), S=1 (6Li).
        self.assertEqual(R.XI.value, 2 * (2 + 1) / (1 * (1 + 1)))
        self.assertTrue(R.XI.close(3.0))

    def test_g_factor_difference(self):
        dg = (R.G_FACTOR_8LI.value - R.G_FACTOR_6LI.value) / R.G_FACTOR_6LI.value
        self.assertTrue(R.DELTA_G_OVER_G.close(dg),
                        f"(g8-g6)/g6 = {dg:.5f}")

    def test_foerster_coefficient_fcc(self):
        # K = (512/243) pi^3 = 65.33, and equals (256/243)*(r0^3/Omega)^2*pi^3
        # with (r0^3/Omega)^2 = 2 for the FCC Li sublattice.
        k_direct = (512.0 / 243.0) * math.pi ** 3
        k_fcc = (256.0 / 243.0) * R.FCC_R0CUBE_OVER_OMEGA_SQ.value * math.pi ** 3
        self.assertAlmostEqual(k_direct, k_fcc, places=9)
        self.assertTrue(R.FOERSTER_COEF_FCC.close(k_direct))
        self.assertAlmostEqual(k_direct, 65.33, places=2)


class TestBeta0Normalization(unittest.TestCase):
    """Canonical beta0 = 1.122*beta0G; beta0G is legacy Gaussian, never beta0."""

    def test_correction_factor_recovers_canonical_beta0(self):
        b0 = R.beta0G_to_beta0(R.BETA0G_2014_C10.value)  # 1.122 * 10.83
        self.assertTrue(R.BETA0_CANONICAL_C10.close(b0),
                        f"1.122*10.83 = {b0:.3f}, expected ~12.15")

    def test_legacy_value_is_not_canonical(self):
        # The two must be kept apart: >10% relative gap.
        rel = abs(R.BETA0_CANONICAL_C10.value - R.BETA0G_LEGACY_C10.value) / R.BETA0_CANONICAL_C10.value
        self.assertGreater(rel, 0.10,
                           "canonical beta0 and legacy beta0G must not be conflated")

    def test_legacy_beta0G_matches_2009_table(self):
        # AMR2009 Table 1 "beta0" at c=10.06% IS the legacy Gaussian beta0G.
        s10 = [s for s in R.TABLE_2009 if abs(s.c - 0.1006) < 1e-6][0]
        self.assertTrue(R.BETA0G_LEGACY_C10.close(s10.beta0))

    def test_canonical_from_legacy_within_tolerance(self):
        # Using the legacy 10.80 gives 12.12; tolerance on the canonical must
        # still accept it (0.3% provenance gap 10.80/10.83).
        b0_from_legacy = R.beta0G_to_beta0(R.BETA0G_LEGACY_C10.value)
        self.assertTrue(R.BETA0_CANONICAL_C10.close(b0_from_legacy),
                        f"1.122*10.80 = {b0_from_legacy:.3f}")

    def test_units_and_source_present(self):
        for c in (R.BETA0_CANONICAL_C10, R.BETA0G_LEGACY_C10, R.BETA0_CORRECTION_FACTOR):
            self.assertTrue(c.unit and c.source, "every const must carry unit+source")
            self.assertTrue(c.rtol is not None or c.atol is not None,
                            "every const must carry a tolerance")


class TestBeta0ProportionalToC2(unittest.TestCase):
    """beta0G ~ K c^2 across the 4 AMR2009 samples (Foerster scaling)."""

    def test_ratio_constant_across_samples(self):
        ratios = [s.beta0 / (s.c * s.c) for s in R.TABLE_2009]
        mean = sum(ratios) / len(ratios)
        for s, ratio in zip(R.TABLE_2009, ratios):
            self.assertTrue(R.BETA0_OVER_C2_2009.close(ratio),
                            f"c={s.c}: beta0/c^2={ratio:.1f} (mean {mean:.1f})")
        # Spread across samples stays within ~1%.
        self.assertLess((max(ratios) - min(ratios)) / mean, 0.01)

    def test_beta0_from_c_helper(self):
        for s in R.TABLE_2009:
            pred = R.beta0_from_c(s.c, K=R.BETA0_OVER_C2_2009.value)
            self.assertAlmostEqual(pred, s.beta0, delta=0.02 * s.beta0)


class TestBeta1OverBeta0(unittest.TestCase):
    def test_three_canonical_field_values(self):
        expected = {0.200: 0.9171, 0.691: 0.3869, 1.210: 0.0837}
        for h, exp in expected.items():
            got = R.BETA1_OVER_BETA0_2014[h].value
            self.assertAlmostEqual(got, exp, places=3,
                                   msg=f"beta1/beta0 @{h} kG = {got:.4f}")

    def test_derivation_from_eq13(self):
        # beta1/beta0 = k(H)/1.122.
        for h, k in R.BETA1_REL_BETA0G_2014.items():
            self.assertTrue(R.BETA1_OVER_BETA0_2014[h].close(k / R.BETA0_CORRECTION_FACTOR.value))

    def test_monotonic_decrease_with_field(self):
        vals = [R.BETA1_OVER_BETA0_2014[h].value for h in (0.200, 0.691, 1.210)]
        self.assertTrue(vals[0] > vals[1] > vals[2])

    def test_legacy_200G_ratio(self):
        s10 = [s for s in R.TABLE_2009 if abs(s.c - 0.1006) < 1e-6][0]
        self.assertTrue(R.BETA1_OVER_BETA0_LEGACY_200G.close(s10.beta1_over_beta0))
        # Legacy (0.943) differs from canonical (0.917) by ~2.7%.
        self.assertGreater(
            abs(R.BETA1_OVER_BETA0_LEGACY_200G.value - R.BETA1_OVER_BETA0_2014[0.200].value),
            0.02)


class TestTables(unittest.TestCase):
    def test_2009_table_shape_and_values(self):
        self.assertEqual(len(R.TABLE_2009), 4)
        cs = [s.c for s in R.TABLE_2009]
        self.assertEqual(cs, sorted(cs))  # ascending concentration
        # a0 clusters around the ~10% limiting asymmetry.
        for s in R.TABLE_2009:
            self.assertTrue(9.0 <= s.a0 <= 10.5)
            self.assertGreater(s.beta0, s.beta1)  # beta1 = beta0*w1/w0 < beta0

    def test_2014_g_table_shape(self):
        self.assertEqual(len(R.G2014_TABLE), 9)  # 3 concentrations x 3 fields
        concs = sorted({c for (c, _h) in R.G2014_TABLE})
        fields = sorted({h for (_c, h) in R.G2014_TABLE})
        self.assertEqual(concs, [0.033, 0.053, 0.1])
        self.assertEqual(fields, [0.2, 0.691, 1.21])
        for p in R.G2014_TABLE.values():
            self.assertEqual(p.d1, 1.0)
            self.assertEqual(p.h, 0.1)

    def test_2014_beta0G_values(self):
        self.assertTrue(R.BETA0G_2014[0.1006].close(10.83))
        self.assertTrue(R.BETA0G_2014[0.053].close(3.057))
        self.assertTrue(R.BETA0G_2014[0.033].close(1.193))


class TestGForm2009(unittest.TestCase):
    def setUp(self):
        self.s = [s for s in R.TABLE_2009 if abs(s.c - 0.1006) < 1e-6][0]

    def test_boundary_values(self):
        g0 = R.g_2009(0.0, self.s.beta0, self.s.beta1, self.s.b1, self.s.b2)
        self.assertAlmostEqual(g0, 1.0, places=12)
        # t -> inf : denominator ~ t^3 dominates numerator ~ t^2, G -> 1.
        g_inf = R.g_2009(1e6, self.s.beta0, self.s.beta1, self.s.b1, self.s.b2)
        self.assertAlmostEqual(g_inf, 1.0, places=4)

    def test_intermediate_bounded(self):
        for t in (0.1, 0.5, 1, 2, 5):
            g = R.g_2009(t, self.s.beta0, self.s.beta1, self.s.b1, self.s.b2)
            self.assertTrue(0.5 < g < 2.0, f"G_2009(t={t})={g:.3f} out of range")


class TestGForm2014(unittest.TestCase):
    def setUp(self):
        self.p = R.G2014_TABLE[(0.1, 0.2)]  # well-behaved reference row

    def test_G0_is_one(self):
        self.assertAlmostEqual(R.g_2014(0.0, self.p), 1.0, places=6)

    def test_G_returns_to_one_at_large_x(self):
        self.assertAlmostEqual(R.g_2014(1e4, self.p), 1.0, delta=0.1)

    def test_intermediate_region_bounded(self):
        # Paper: 0.85 < G < 2 in the intermediate region (x >= a few).
        for x in (5, 10, 20, 30, 50, 80, 108, 200):
            g = R.g_2014(x, self.p)
            self.assertTrue(0.85 < g < 2.0, f"G_2014(x={x})={g:.3f} out of [0.85,2]")

    def test_all_rows_evaluate_finite(self):
        # Every (c,H0) row must produce finite G on a coarse grid without
        # domain errors (log/sqrt), even the stiff high-field rows.
        for key, p in R.G2014_TABLE.items():
            for x in (0.0, 1.0, 10.0, 100.0):
                g = R.g_2014(x, p)
                self.assertTrue(math.isfinite(g), f"G_2014{key}(x={x}) not finite")


class TestOutlierWindow(unittest.TestCase):
    def test_window_range(self):
        self.assertEqual(R.OUTLIER_WINDOW.beta0_t_lo, 30.0)
        self.assertEqual(R.OUTLIER_WINDOW.beta0_t_hi, 108.0)
        self.assertLess(R.OUTLIER_WINDOW.beta0_t_lo, R.OUTLIER_WINDOW.beta0_t_hi)

    def test_marked_as_benchmark_not_equality_requirement(self):
        # The window is an open-question benchmark, NOT a requirement that the
        # RWDM baseline reproduce the phenomenological F(t)*G(t).
        self.assertEqual(R.OUTLIER_WINDOW.kind, "benchmark_outlier")
        self.assertNotEqual(R.OUTLIER_WINDOW.kind, "equality_requirement")
        self.assertIn("open-question", R.OUTLIER_WINDOW.note.lower())

    def test_g_peaks_inside_window(self):
        # The correction factor's maximum (largest excess over Foerster) falls
        # inside the outlier window for the canonical c=10%,200G curve.
        p = R.G2014_TABLE[(0.1, 0.2)]
        grid = [x / 2 for x in range(2, 601)]  # x in [1, 300]
        x_peak = max(grid, key=lambda x: R.g_2014(x, p))
        self.assertTrue(R.OUTLIER_WINDOW.beta0_t_lo <= x_peak <= R.OUTLIER_WINDOW.beta0_t_hi,
                        f"G peak at beta0*t={x_peak}, outside outlier window")
        # Peak amplitude is substantial (~1.8), consistent with the ~2x outlier.
        self.assertGreater(R.g_2014(x_peak, p), 1.5)


if __name__ == "__main__":
    unittest.main()
