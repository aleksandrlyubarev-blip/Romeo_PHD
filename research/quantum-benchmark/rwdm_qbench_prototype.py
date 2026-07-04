#!/usr/bin/env python3
"""Prototype of the RWDM-LiF quantum-computer benchmark.

Physical system: polarization transfer from an impurity 8Li nucleus to a
random dilute 6Li sublattice in LiF (beta-NMR observable P00(t)).

This prototype implements the two computational tiers of the proposed
benchmark on small instances that fit exact classical simulation:

  Tier A  -- single-excitation sector on a disordered FCC supercell:
             classical random walk (RWDM master equation, rates ~ b_ij^2)
             versus continuous-time quantum walk (XY flip-flop, couplings
             ~ b_ij).  Classically cheap (O(N^3)); this is the hardware
             verification tier.

  Tier B  -- full many-body dynamics of the secular dipolar Hamiltonian
             for N spins-1/2 on the same disordered geometry, exact
             diagonalization in the full 2^N Hilbert space.  The observable
             is the infinite-temperature autocorrelator
                 C(t) = Tr[Sz_0(t) Sz_0] / Tr[Sz_0^2],
             i.e. exactly the beta-NMR return probability P00(t).
             Classically exponential; this is the quantum-advantage tier.

Simplifications relative to the production RWDM spec (documented in
docs/quantum-benchmark-rwdm-lif.md): homonuclear spins-1/2 (no xi=3
asymmetry, no spin-1/spin-2), no field factor beta1/beta0, unit line-shape
factor.  Geometry, disorder ensemble and observable are the real ones.

Units: cubic lattice constant a = 1, dipolar coupling b(r) = (1-3cos^2
theta)/r^3, dimensionless time tau = t / r0^3 with r0 = a/sqrt(2) the
nearest-neighbour Li-Li distance (i.e. |b(r0)| = 1 at the magic-angle-free
reference scale).

Only numpy is required.  Run:  python3 rwdm_qbench_prototype.py
"""

import json
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "results")

R0 = 1.0 / np.sqrt(2.0)  # nearest-neighbour distance of the FCC Li sublattice, a=1
B0 = 1.0 / R0**3         # dipolar coupling scale at r0

FCC_BASIS = np.array([
    [0.0, 0.0, 0.0],
    [0.0, 0.5, 0.5],
    [0.5, 0.0, 0.5],
    [0.5, 0.5, 0.0],
])


def fcc_sites(ng):
    """All 4*ng^3 Li-sublattice sites of a cubic supercell of size ng (a=1)."""
    cells = np.array([[i, j, k] for i in range(ng) for j in range(ng) for k in range(ng)],
                     dtype=float)
    return (cells[:, None, :] + FCC_BASIS[None, :, :]).reshape(-1, 3)


def make_instance(ng, n_spins, seed, orientation=(1.0, 1.0, 1.0)):
    """One disorder realization: 8Li fixed at the origin site, n_spins-1
    6Li nuclei placed uniformly at random on the remaining sublattice sites.
    Returns positions (n_spins, 3); index 0 is the 8Li site."""
    rng = np.random.default_rng(seed)
    sites = fcc_sites(ng)
    origin = 0  # site (0,0,0)
    others = np.delete(np.arange(len(sites)), origin)
    chosen = rng.choice(others, size=n_spins - 1, replace=False)
    idx = np.concatenate([[origin], chosen])
    return sites[idx], np.asarray(orientation, dtype=float)


def dipolar_couplings(pos, ng, orientation):
    """Matrix b_ij = (1 - 3 cos^2 theta_ij) / r_ij^3 with minimal-image PBC,
    theta measured from the field direction (orientation vector)."""
    n = len(pos)
    e = orientation / np.linalg.norm(orientation)
    d = pos[:, None, :] - pos[None, :, :]
    d -= ng * np.round(d / ng)  # minimal image in the cubic box of edge ng
    r = np.linalg.norm(d, axis=-1)
    np.fill_diagonal(r, np.inf)
    cos_t = (d @ e) / r
    return (1.0 - 3.0 * cos_t**2) / r**3


# ----------------------------------------------------------------------
# Tier A: single-excitation sector, classical vs quantum walk
# ----------------------------------------------------------------------

def tier_a_curves(b, taus):
    """P00(tau) for the classical master equation (rates w_ij = (b_ij/B0)^2,
    dimensionless time tau_c = nu0*t with nu0 = B0^2*t-scale) and for the
    continuous-time quantum walk (H_ij = b_ij, tau_q = B0*t).
    Both are exact via Hermitian eigendecomposition."""
    n = b.shape[0]
    bn = b / B0

    # classical generator (symmetric rates => already Hermitian)
    w = bn**2
    a_gen = w - np.diag(w.sum(axis=0))
    ev, u = np.linalg.eigh(a_gen)
    amp0 = u[0, :] ** 2
    p_cl = np.array([np.sum(amp0 * np.exp(ev * t)) for t in taus])

    # quantum walk in the single-excitation sector
    ev_q, u_q = np.linalg.eigh(bn)
    phase = np.exp(-1j * np.outer(taus, ev_q))
    amp = phase @ (u_q[0, :].conj() * u_q[0, :])
    p_q = np.abs(amp) ** 2
    return p_cl, p_q


# ----------------------------------------------------------------------
# Tier B: full many-body secular dipolar dynamics, exact diagonalization
# ----------------------------------------------------------------------

def pauli_ops(n):
    """Return lists of Sz_i, S+_i as dense 2^n operators (spin-1/2)."""
    sz1 = np.array([[0.5, 0.0], [0.0, -0.5]])
    sp1 = np.array([[0.0, 1.0], [0.0, 0.0]])
    eye = np.eye(2)

    def kron_at(op, i):
        m = np.array([[1.0]])
        for k in range(n):
            m = np.kron(m, op if k == i else eye)
        return m

    return [kron_at(sz1, i) for i in range(n)], [kron_at(sp1, i) for i in range(n)]


def tier_b_curve(b, taus):
    """Infinite-temperature autocorrelator C(tau)=Tr[Sz0(t)Sz0]/Tr[Sz0^2]
    for the secular dipolar Hamiltonian
        H = sum_{i<j} (b_ij/B0) [ Sz_i Sz_j - (1/4)(S+_i S-_j + S-_i S+_j) ].
    Exact dense diagonalization, dimension 2^n."""
    n = b.shape[0]
    bn = b / B0
    sz, sp = pauli_ops(n)
    dim = 2**n
    h = np.zeros((dim, dim), dtype=complex)
    for i in range(n):
        for j in range(i + 1, n):
            ff = sp[i] @ sp[j].conj().T
            h += bn[i, j] * (sz[i] @ sz[j] - 0.25 * (ff + ff.conj().T))
    ev, u = np.linalg.eigh(h)
    sz0 = u.conj().T @ sz[0] @ u
    w2 = np.abs(sz0) ** 2
    de = ev[:, None] - ev[None, :]
    norm = w2.sum()
    return np.array([np.sum(w2 * np.cos(t * de)) for t in taus]) / norm


def tier_b_master_equation(b, taus, rate_scale):
    """Single-particle RWDM master equation on the same instance, rates
    w_ij = rate_scale * (b_ij/B0)^2, as the classical baseline for Tier B."""
    bn = b / B0
    w = rate_scale * bn**2
    a_gen = w - np.diag(w.sum(axis=0))
    ev, u = np.linalg.eigh(a_gen)
    amp0 = u[0, :] ** 2
    return np.array([np.sum(amp0 * np.exp(ev * t)) for t in taus])


# ----------------------------------------------------------------------

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    summary = {}

    # ---- Tier A: ng=6 supercell, c ~ 10%, single-excitation sector ----
    ng_a, c_a, n_real_a = 6, 0.1006, 24
    n_sites = 4 * ng_a**3
    n_spins_a = 1 + int(round(c_a * n_sites))
    taus_a = np.linspace(0.0, 40.0, 161)
    acc_cl = np.zeros_like(taus_a)
    acc_q = np.zeros_like(taus_a)
    for s in range(n_real_a):
        pos, e = make_instance(ng_a, n_spins_a, seed=1000 + s)
        b = dipolar_couplings(pos, ng_a, e)
        p_cl, p_q = tier_a_curves(b, taus_a)
        acc_cl += p_cl
        acc_q += p_q
    acc_cl /= n_real_a
    acc_q /= n_real_a
    summary["tier_a"] = {
        "ng": ng_a, "concentration": c_a, "n_spins": n_spins_a,
        "n_realizations": n_real_a,
        "P00_classical_final": float(acc_cl[-1]),
        "P00_quantum_final": float(acc_q[-1]),
    }

    # ---- Tier B: 10 spins in an ng=3 supercell, full Hilbert space ----
    ng_b, n_spins_b, n_real_b = 3, 10, 16
    taus_b = np.linspace(0.0, 20.0, 121)
    acc_mb = np.zeros_like(taus_b)
    acc_me = {sc: np.zeros_like(taus_b) for sc in (0.5, 1.0, 2.0)}
    for s in range(n_real_b):
        pos, e = make_instance(ng_b, n_spins_b, seed=2000 + s)
        b = dipolar_couplings(pos, ng_b, e)
        acc_mb += tier_b_curve(b, taus_b)
        for sc in acc_me:
            acc_me[sc] += tier_b_master_equation(b, taus_b, sc)
    acc_mb /= n_real_b
    for sc in acc_me:
        acc_me[sc] /= n_real_b
    c_b = (n_spins_b - 1) / (4 * ng_b**3 - 1)
    summary["tier_b"] = {
        "ng": ng_b, "n_spins": n_spins_b, "concentration": round(c_b, 4),
        "hilbert_dim": 2**n_spins_b, "n_realizations": n_real_b,
        "C_final_exact_quantum": float(acc_mb[-1]),
        "P00_final_master_eq_scale_1": float(acc_me[1.0][-1]),
    }

    # ---- save data ----
    np.savetxt(os.path.join(OUTDIR, "tier_a_p00.csv"),
               np.column_stack([taus_a, acc_cl, acc_q]),
               header="tau,P00_classical_walk,P00_quantum_walk",
               delimiter=",", comments="")
    np.savetxt(os.path.join(OUTDIR, "tier_b_p00.csv"),
               np.column_stack([taus_b, acc_mb] + [acc_me[sc] for sc in sorted(acc_me)]),
               header="tau,C_exact_manybody,"
                      + ",".join(f"P00_master_eq_scale_{sc}" for sc in sorted(acc_me)),
               delimiter=",", comments="")
    with open(os.path.join(OUTDIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # ---- figure ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
        ax1.plot(taus_a, acc_cl, label="classical walk (RWDM rates $b_{ij}^2$)")
        ax1.plot(taus_a, acc_q, label="quantum walk (XY, couplings $b_{ij}$)")
        ax1.set_title(f"Tier A: single excitation, ng={ng_a}, c={c_a:.2%}, "
                      f"N={n_spins_a}, {n_real_a} realizations")
        ax1.set_xlabel(r"dimensionless time $\tau$")
        ax1.set_ylabel(r"$P_{00}$")
        ax1.set_yscale("log")
        ax1.legend()
        ax2.plot(taus_b, acc_mb, "k", lw=2,
                 label=r"exact many-body $\langle S^z_0(t)S^z_0\rangle$, $2^{10}$")
        for sc in sorted(acc_me):
            ax2.plot(taus_b, acc_me[sc], "--", label=f"master eq., rate scale {sc}")
        ax2.set_title(f"Tier B: secular dipolar, N={n_spins_b} spins, "
                      f"c={c_b:.2%}, {n_real_b} realizations")
        ax2.set_xlabel(r"dimensionless time $\tau$")
        ax2.set_ylabel(r"$P_{00}$")
        ax2.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(OUTDIR, "fig_qbench_prototype.png"), dpi=150)
    except ImportError:
        pass

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
