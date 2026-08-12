# Methodology

Every number this study produces depends on a handful of choices that are not
made for you by the solver. This document records what was chosen and why.

## 1. System model

The New England 39-bus test system (`pandapower.networks.case39`), a reduced
equivalent of the New England 345 kV transmission network:

| Quantity | Value |
|---|---|
| Buses | 39 (all 345 kV) |
| Generators | 10 (9 PV + slack at bus 30) |
| Loads | 21, totalling 6254.2 MW / 1387.1 Mvar |
| Lines | 35 |
| Transformers | 11 |
| System base | 100 MVA |

Bus and branch indices are pandapower's zero-based indices throughout. Bus 30 in
this study is the bus labelled 31 in the original MATPOWER data.

Branch ratings come with the case (MATPOWER `rateA`, converted by pandapower to
`max_i_ka` for lines and `sn_mva` for transformers) and resolve to a small set of
standard values. No thermal limits were invented.

## 2. Power flow

Full AC Newton-Raphson, flat-start avoided in favour of a DC-solution initial
guess (`init="dc"`), 30 iteration maximum. AC rather than DC power flow is
essential here: a DC formulation would report no voltage results at all, and the
reactive redistribution after an outage is a real part of the answer.

## 3. Voltage criteria — and why one limit is not enough

The intact system **already sits above 1.05 pu at seven buses**, peaking at
1.0636 pu (bus 35). That is not an error in the model; it is where the published
generator voltage setpoints put it.

The consequence matters. A single 0.95–1.05 pu screen reports those seven buses
as violations in essentially every contingency, producing 141 violation records
across the sweep — most of them with excursions of 0.0001 pu that the outage had
nothing to do with. The ranking is then driven by an inherited condition rather
than by the contingency, which is exactly the failure the study exists to avoid.

Two criteria are applied instead:

**Criterion 1 — post-contingency band, 0.90 ≤ V ≤ 1.10 pu.**
Standard planning practice separates the normal band (0.95–1.05) from the wider
emergency band tolerated in the window immediately following a single-element
outage. The base case sits comfortably inside the emergency band, so anything
tripping this criterion was genuinely caused by the outage.

**Criterion 2 — voltage deviation, |V − V_base| ≤ 0.05 pu.**
A bus can remain legal in absolute terms and still be a problem if the outage
moved it a long way, because the movement is what consumes reactive reserve and
exercises tap changers. This is the criterion that catches the one voltage
finding in this study (bus 14 on the L 14-15 outage), which criterion 1 misses
entirely.

Every violation record additionally carries `base_vm_pu` and `delta_from_base`,
so an inherited condition can never be mistaken for a caused one at any point.

## 4. Thermal criterion

`loading_percent > 100` against the continuous rating, applied to lines and
transformers alike. The removed element is excluded from its own overload check.

No emergency (short-term) rating is applied. Real studies commonly allow a
higher post-contingency rating for a limited duration; not doing so here makes
this screen conservative, which is stated in the limitations.

## 5. Contingency selection

All 46 branches are examined, but they are not all the same kind of event. The
list is partitioned before any power flow runs, using graph analysis on the
intact network:

| Category | Count | Treatment |
|---|---|---|
| Generator step-up | 9 | Screened, reported, **excluded** from the ranking |
| Structural bridge | 2 | Ranked as islanding contingencies |
| Meshed | 35 | Ranked normally |

**Generator step-up.** Nine buses (29 and 31–37) are radial: each is a generator
connected to the network by exactly one transformer. Removing that transformer is
a *generator* outage, not a transmission outage, and it disconnects the bus by
construction. Including these in a transmission ranking would put nine trivially
maximal scores at the top and bury every result the study is about.

**Structural bridge.** Branches whose removal disconnects the graph somewhere
other than a generator tail. These are found with `networkx.bridges` on the intact
network, before any solver runs — a bridge outage cannot be assessed by a power
flow because there is no connected network left to solve. Detecting them up front
is faster than letting Newton-Raphson fail, and more honest, since a solver
failure and a topological separation are different findings. The bridge detection
is cross-checked in the test suite against brute-force edge deletion.

## 6. Outcome classification

| Status | Meaning |
|---|---|
| `NORMAL` | Solved, no criterion breached |
| `VIOLATION` | Solved, one or more criteria breached |
| `NON-CONVERGENT` | Connected network, but Newton-Raphson did not converge |
| `ISLANDED` | Outage separates load from the slack; no power flow attempted |
| `EXCLUDED` | Generator step-up, screened separately |

`NON-CONVERGENT` deserves care. Non-convergence is not proof of physical
instability — it can also mean a poor initial guess or an iteration limit. It is
reported as its own category rather than folded into "violation" so that it is
visible as something requiring human judgement. In this study the category is
empty: every connected contingency converged.

## 7. Severity index

```
Severity = 100 × Σ|excursion beyond the emergency band, pu|
         +  50 × Σ|excursion beyond the deviation criterion, pu|
         +   1 × Σ(loading% − 100)
         + 500  if non-convergent
         + 1000 if islanded
```

Design decisions, each of which is defensible and each of which could reasonably
have gone another way:

**Magnitude, not count.** Six buses 0.001 pu low is a rounding error; one bus
0.06 pu low is a warning about voltage collapse. Counting violations treats these
as 6-to-1 in the wrong direction. The index integrates depth of excursion; counts
are still reported, as secondary statistics.

**Weight 100 on band violations.** This puts a 0.01 pu voltage excursion on par
with a 1% thermal overload. Both are "1% of nominal", so the two terms add on a
common scale rather than through an arbitrary tuning constant.

**Weight 50 on deviation violations.** Half a band violation: a large deviation
that stays inside the emergency band is a warning about system stress, not a
limit that has been broken.

**Failure penalties dominate.** A non-convergent case (500) outranks any solvable
violation, because an unconverged case is an unbounded unknown rather than a
quantified one. An islanded case (1000) outranks that, because load has been
disconnected outright — a firmer consequence than any in-service violation. The
constants are chosen to be unreachable by the violation terms rather than
calibrated to anything physical, and that is a deliberate limitation: the index
ranks islanding cases against each other only by tie.

**What the index does not do.** It has no notion of duration, of remedial action,
of how much load is at risk downstream of an overload, or of the probability of
the outage. A production ranking would weight by all four.

## 8. Reproducibility

The study is deterministic: no random initialisation, no sampling. `main.py`
re-solves the base case after the sweep and asserts it reproduces exactly, which
catches an element left out of service. The test suite runs the whole sweep twice
and compares every severity score.
