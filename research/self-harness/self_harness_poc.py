#!/usr/bin/env python3
"""Self-Harness PoC: a harness that improves itself, applied to a RoboQC-style
visual inspection agent.

Implements the three-stage loop of "Self-Harness: Harnesses That Improve
Themselves" (Shanghai AI Lab, arXiv:2606.09498) on a synthetic but
mechanistically faithful QC environment:

  1. Weakness Mining    -- run the current harness on held-in tasks, collect
                           execution traces, cluster failures by signature
                           (verifier-level cause + agent-level mechanism +
                           context bucket), keep recurring patterns.
  2. Harness Proposal   -- generate K candidate edits, each MINIMAL (touches
                           exactly one editable surface) and tied to one mined
                           weakness.  The proposer also emits plausible-but-bad
                           candidates (a no-op instruction and a "paranoid
                           reject" policy) to exercise the validator.
  3. Proposal Validation-- evaluate every candidate independently against the
                           current harness on held-in AND held-out splits with
                           common random numbers (paired evaluation).  Accept
                           only if it improves at least one split without
                           regressing the other (non-regression rule).  Merge
                           compatible accepted edits, iterate until dry.

The "agent" here is a stochastic simulator whose failure modes are gated by
harness surfaces, so the run demonstrates the *mechanism* of the loop (mining
finds the right signatures, targeted minimal edits pass validation, distractor
edits get rejected) -- not the capability of any particular LLM.

Stdlib only.  Deterministic for a fixed --seed.

Usage:
    python3 self_harness_poc.py [--seed 42] [--tasks 1200] [--rounds 6]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

# ---------------------------------------------------------------------------
# Domain: synthetic PCB inspection tasks
# ---------------------------------------------------------------------------

DEFECT_TYPES = ["solder_bridge", "missing_component", "tombstone", "cold_joint"]
LIGHTING = ["normal", "glare"]
ZONES = ["connector", "generic"]


@dataclass(frozen=True)
class Task:
    task_id: int
    defect: str  # one of DEFECT_TYPES or "none"
    lighting: str
    zone: str
    loop_prone: bool  # tasks where the agent tends to re-inspect forever


def generate_tasks(n: int, rng: random.Random) -> list[Task]:
    tasks = []
    for i in range(n):
        defect = rng.choice(DEFECT_TYPES) if rng.random() < 0.65 else "none"
        tasks.append(
            Task(
                task_id=i,
                defect=defect,
                lighting="glare" if rng.random() < 0.30 else "normal",
                zone="connector" if rng.random() < 0.25 else "generic",
                loop_prone=rng.random() < 0.08,
            )
        )
    return tasks


# ---------------------------------------------------------------------------
# Harness: the editable surfaces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Harness:
    """Editable surfaces of the inspection harness.

    Each field maps to a real surface in a production QC harness:
    few-shot blocks in the vision prompt, output-schema enforcement,
    retry/recovery policies, cross-checks, verification steps, execution
    guards.  The simulator gates each failure mode on exactly one field.
    """

    fewshot_defects: frozenset[str] = frozenset({"solder_bridge"})
    strict_output_schema: bool = False
    glare_retry_policy: bool = False
    cross_view_on_connectors: bool = False
    self_verification: bool = False
    step_budget_guard: bool = False
    # Distractor surfaces the proposer may (wrongly) suggest touching:
    paranoid_reject: bool = False   # boosts recall, wrecks false-positive rate
    generic_caution: bool = False   # "be extra careful" -- does nothing

    def describe(self) -> dict:
        d = self.__dict__.copy()
        d["fewshot_defects"] = sorted(self.fewshot_defects)
        return d


# ---------------------------------------------------------------------------
# Execution: run one task under a harness, emit a rich trace
# ---------------------------------------------------------------------------


@dataclass
class Trace:
    task: Task
    verdict: str  # "pass" | "fail"
    failure_cause: str | None = None    # verifier-level
    mechanism: str | None = None        # agent-level
    context: str | None = None          # bucketed context
    steps: list[str] = field(default_factory=list)

    @property
    def signature(self) -> tuple[str, str, str] | None:
        if self.verdict == "pass":
            return None
        return (self.failure_cause, self.mechanism, self.context)


def simulate_inspection(task: Task, h: Harness, rng: random.Random) -> Trace:
    t = Trace(task=task, verdict="pass")
    t.steps.append("capture_frame")

    # Unbounded re-inspection loop on ambiguous frames.
    if task.loop_prone and not h.step_budget_guard and rng.random() < 0.55:
        t.steps.extend(["reinspect"] * 12)
        t.verdict, t.failure_cause, t.mechanism, t.context = (
            "fail", "timeout", "unbounded_reinspect_loop", "loop_prone=true")
        return t

    # Output-schema drift breaks the downstream PLC/decision parser.
    schema_fail_p = 0.01 if h.strict_output_schema else 0.14
    if rng.random() < schema_fail_p:
        t.verdict, t.failure_cause, t.mechanism, t.context = (
            "fail", "format_error", "output_schema_drift", "any")
        return t

    if task.defect != "none":
        # Detection probability: few-shot coverage dominates.
        p_detect = 0.93 if task.defect in h.fewshot_defects else 0.55
        if h.paranoid_reject:
            p_detect = min(0.98, p_detect + 0.10)
        if task.lighting == "glare":
            if h.glare_retry_policy:
                t.steps.append("retry_adjust_lighting")
                p_detect *= 0.90
            else:
                p_detect *= 0.45
        t.steps.append("classify_defect")
        if rng.random() < p_detect:
            return t
        t.verdict = "fail"
        t.failure_cause = "missed_defect"
        if task.lighting == "glare" and not h.glare_retry_policy:
            t.mechanism, t.context = "glare_degradation", "lighting=glare"
        elif task.defect not in h.fewshot_defects:
            t.mechanism = "no_fewshot_coverage"
            t.context = f"defect={task.defect}"
        else:
            # Covered defect still missed: irreducible classifier residual,
            # not attributable to any editable surface.
            t.mechanism = "residual_classifier_miss"
            t.context = f"defect={task.defect}"
        return t

    # Clean board: false positives.
    if task.zone == "connector":
        p_fp = 0.04 if h.cross_view_on_connectors else 0.28
        mechanism, context = "connector_ambiguity", "zone=connector"
        if h.cross_view_on_connectors:
            t.steps.append("cross_view_check")
    else:
        p_fp = 0.02 if h.self_verification else 0.11
        mechanism, context = "hallucinated_defect", "zone=generic"
        if h.self_verification:
            t.steps.append("self_verify")
    if h.paranoid_reject:
        p_fp = min(0.95, p_fp + 0.30)
    if rng.random() < p_fp:
        t.verdict, t.failure_cause, t.mechanism, t.context = (
            "fail", "false_positive", mechanism, context)
    return t


def evaluate(harness: Harness, tasks: list[Task], base_seed: int) -> list[Trace]:
    """Paired evaluation: each task gets its own RNG stream derived from
    (base_seed, task_id), so two harnesses are compared on identical
    randomness (common random numbers)."""
    return [
        simulate_inspection(task, harness, random.Random(f"{base_seed}:{task.task_id}"))
        for task in tasks
    ]


def pass_rate(traces: list[Trace]) -> float:
    return sum(tr.verdict == "pass" for tr in traces) / len(traces)


# ---------------------------------------------------------------------------
# Stage 1: Weakness Mining
# ---------------------------------------------------------------------------


def mine_weaknesses(traces: list[Trace], min_count: int) -> list[tuple[tuple, int]]:
    """Cluster failed traces by (verifier cause, agent mechanism, context)
    and keep recurring, actionable signatures ranked by frequency."""
    sigs = Counter(tr.signature for tr in traces if tr.signature)
    return [(sig, n) for sig, n in sigs.most_common() if n >= min_count]


# ---------------------------------------------------------------------------
# Stage 2: Harness Proposal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Edit:
    name: str
    target_signature: str  # which mined weakness this edit addresses
    surface: str           # exactly ONE editable surface

    def apply(self, h: Harness) -> Harness:
        if self.surface == "fewshot_defects":
            defect = self.name.split(":", 1)[1]
            return replace(h, fewshot_defects=h.fewshot_defects | {defect})
        return replace(h, **{self.surface: True})


def propose_edits(mined: list[tuple[tuple, int]], h: Harness) -> list[Edit]:
    """Map each mined signature to minimal candidate edits.  In production
    this stage is the same frozen LLM acting as proposer over the harness
    files; here it is a catalog keyed by mechanism.  Distractor proposals
    are always included so validation has something to reject."""
    edits: list[Edit] = []
    for (cause, mechanism, context), _count in mined:
        sig_str = f"{cause}/{mechanism}/{context}"
        if mechanism == "no_fewshot_coverage":
            defect = context.split("=", 1)[1]
            if defect not in h.fewshot_defects:
                edits.append(Edit(f"add_fewshot:{defect}", sig_str, "fewshot_defects"))
        elif mechanism == "glare_degradation" and not h.glare_retry_policy:
            edits.append(Edit("enable_glare_retry", sig_str, "glare_retry_policy"))
        elif mechanism == "connector_ambiguity" and not h.cross_view_on_connectors:
            edits.append(Edit("enable_cross_view", sig_str, "cross_view_on_connectors"))
        elif mechanism == "hallucinated_defect" and not h.self_verification:
            edits.append(Edit("enable_self_verification", sig_str, "self_verification"))
        elif mechanism == "output_schema_drift" and not h.strict_output_schema:
            edits.append(Edit("enforce_output_schema", sig_str, "strict_output_schema"))
        elif mechanism == "unbounded_reinspect_loop" and not h.step_budget_guard:
            edits.append(Edit("add_step_budget_guard", sig_str, "step_budget_guard"))
    # Plausible-but-bad candidates: the validator must reject both.
    if mined and not h.paranoid_reject:
        edits.append(Edit("paranoid_reject_everything",
                          "missed_defect/* (overreach)", "paranoid_reject"))
    if mined and not h.generic_caution:
        edits.append(Edit("add_generic_caution_instruction",
                          "any (vague)", "generic_caution"))
    return edits


# ---------------------------------------------------------------------------
# Stage 3: Proposal Validation (non-regression rule)
# ---------------------------------------------------------------------------


@dataclass
class Verdict:
    edit: Edit
    d_in: float
    d_out: float
    accepted: bool
    reason: str


def validate(edit: Edit, current: Harness, held_in: list[Task],
             held_out: list[Task], seed: int,
             min_gain: float = 0.01, max_regress: float = 0.005) -> Verdict:
    candidate = edit.apply(current)
    d_in = pass_rate(evaluate(candidate, held_in, seed)) - \
        pass_rate(evaluate(current, held_in, seed))
    d_out = pass_rate(evaluate(candidate, held_out, seed)) - \
        pass_rate(evaluate(current, held_out, seed))
    improves = d_in >= min_gain or d_out >= min_gain
    regresses = d_in < -max_regress or d_out < -max_regress
    if improves and not regresses:
        return Verdict(edit, d_in, d_out, True, "improves without regression")
    if regresses:
        return Verdict(edit, d_in, d_out, False, "regression on a split")
    return Verdict(edit, d_in, d_out, False, "no measurable improvement")


# ---------------------------------------------------------------------------
# The self-improvement loop
# ---------------------------------------------------------------------------


def run(seed: int, n_tasks: int, max_rounds: int, out_dir: Path) -> dict:
    rng = random.Random(seed)
    tasks = generate_tasks(n_tasks, rng)
    held_in = [t for t in tasks if t.task_id % 2 == 0]
    held_out = [t for t in tasks if t.task_id % 2 == 1]

    harness = Harness()
    baseline_in = pass_rate(evaluate(harness, held_in, seed))
    baseline_out = pass_rate(evaluate(harness, held_out, seed))
    print(f"baseline pass rate  held-in {baseline_in:6.1%}   "
          f"held-out {baseline_out:6.1%}")
    print(f"baseline harness    {harness.describe()}\n")

    rounds_log: list[dict] = []
    for rnd in range(1, max_rounds + 1):
        traces = evaluate(harness, held_in, seed + rnd)  # fresh episode noise
        mined = mine_weaknesses(traces, min_count=5)
        proposals = propose_edits(mined, harness)
        if not proposals:
            print(f"round {rnd}: no actionable proposals -- loop is dry")
            break

        print(f"round {rnd}: mined {len(mined)} recurring signatures, "
              f"{len(proposals)} proposals")
        for sig, n in mined[:6]:
            print(f"    weakness  {n:4d}x  {'/'.join(sig)}")

        verdicts = [validate(e, harness, held_in, held_out, seed) for e in proposals]
        accepted = [v for v in verdicts if v.accepted]
        for v in verdicts:
            mark = "ACCEPT" if v.accepted else "reject"
            print(f"    {mark}  {v.edit.name:<34s} "
                  f"d_in {v.d_in:+.3f}  d_out {v.d_out:+.3f}  ({v.reason})")

        # Merge compatible accepted edits (all surfaces here are independent).
        for v in accepted:
            harness = v.edit.apply(harness)

        rounds_log.append({
            "round": rnd,
            "mined_signatures": [{"signature": "/".join(s), "count": n}
                                 for s, n in mined],
            "verdicts": [{"edit": v.edit.name, "target": v.edit.target_signature,
                          "surface": v.edit.surface, "delta_held_in": round(v.d_in, 4),
                          "delta_held_out": round(v.d_out, 4),
                          "accepted": v.accepted, "reason": v.reason}
                         for v in verdicts],
            "pass_rate_held_in": round(pass_rate(evaluate(harness, held_in, seed)), 4),
            "pass_rate_held_out": round(pass_rate(evaluate(harness, held_out, seed)), 4),
        })
        print(f"    pass rate now   held-in {rounds_log[-1]['pass_rate_held_in']:6.1%}   "
              f"held-out {rounds_log[-1]['pass_rate_held_out']:6.1%}\n")

        if not accepted:
            print(f"round {rnd}: all proposals rejected -- loop is dry")
            break

    final_in = pass_rate(evaluate(harness, held_in, seed))
    final_out = pass_rate(evaluate(harness, held_out, seed))
    print("final harness       ", harness.describe())
    print(f"held-in   {baseline_in:6.1%} -> {final_in:6.1%}  "
          f"({(final_in - baseline_in) * 100:+.1f} pp)")
    print(f"held-out  {baseline_out:6.1%} -> {final_out:6.1%}  "
          f"({(final_out - baseline_out) * 100:+.1f} pp)")

    summary = {
        "paper": "Self-Harness (arXiv:2606.09498)",
        "seed": seed,
        "n_tasks": n_tasks,
        "baseline": {"held_in": round(baseline_in, 4), "held_out": round(baseline_out, 4)},
        "final": {"held_in": round(final_in, 4), "held_out": round(final_out, 4)},
        "final_harness": harness.describe(),
        "rounds": rounds_log,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    with (out_dir / "rounds.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["round", "edit", "surface", "delta_held_in",
                    "delta_held_out", "accepted", "reason"])
        for r in rounds_log:
            for v in r["verdicts"]:
                w.writerow([r["round"], v["edit"], v["surface"], v["delta_held_in"],
                            v["delta_held_out"], v["accepted"], v["reason"]])
    print(f"\nwrote {out_dir / 'summary.json'} and {out_dir / 'rounds.csv'}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tasks", type=int, default=1200)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "results")
    args = ap.parse_args()
    run(args.seed, args.tasks, args.rounds, args.out)
