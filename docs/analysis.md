# Engineering Analysis

Seven contingencies out of 37 eligible produce a consequence worth discussing:
two separate the network, and five overload branches. The remaining 25 are
uneventful. This document works through all seven, because "why" is the part the
solver does not answer.

The headline finding first, since it frames everything below.

> **Under N-1, this system is thermally limited, not voltage limited.**
> Sixteen thermal violations across five contingencies; zero voltage-band
> violations across all 37. The lowest post-contingency voltage anywhere in the
> study is 0.9369 pu (bus 14, outage L 14-15) against a 0.90 pu emergency floor,
> and the highest is 1.0798 pu against a 1.10 pu ceiling. There is roughly 3–4%
> of voltage margin left in the worst case, and none at all thermally.

That is a real property of the model rather than an artefact of the limits: it
holds because case39 is a 345 kV network with generation distributed close to its
load centres, so outages redistribute real power over long paths without moving
voltages much. It would not hold for a distribution feeder, and it would not hold
here if the emergency band were tightened to 0.95–1.05.

---

## 1. L 15-18 — network separation, 680 MW disconnected

**Severity 1000 · ISLANDED · 4 buses separated**

Bus 18's only connections are bus 15, bus 19, and generator bus 32. Bus 19's only
connections are bus 18 and generator bus 33. The four buses {18, 19, 32, 33}
therefore hang off the rest of the network by the single line 15-18 — a
*structural bridge*, not a meshed element.

Removing it separates a pocket containing 680 MW of load (at bus 19) and two
generators (508 MW at bus 33, 632 MW at bus 32). No power flow is attempted,
because there is no longer one connected network to solve.

**Why this is the most severe result and also the least alarming.** In a real
345 kV network you would not accept a single line whose loss strands 680 MW of
load — that is precisely the condition N-1 planning exists to eliminate. But
case39 is a *reduced equivalent* of the New England system: the real network's
parallel paths in this corridor were collapsed into single equivalent branches
during the reduction. The radial tail is an artefact of the equivalencing, not a
vulnerability of the system being modelled. Reporting it as the top-ranked
contingency is correct behaviour by the tool and a modelling caveat by the
engineer, and both statements have to be made together.

## 2. T 18-19 — the same tail, one branch further in

**Severity 1000 · ISLANDED · 2 buses separated**

The transformer between bus 18 and bus 19 is the second bridge in the same tail.
Its loss strands {19, 33}: the same 680 MW of load, now with only the 508 MW
generator at bus 33 for company. Same caveat as above.

The two cases together are the study's clearest structural finding: **every
islanding contingency in this system lies on one radial tail.** The other 35
meshed branches all have an alternative path.

---

## 3. L 20-21 — worst solvable case, 157.5% overload

**Severity 70.4 · Critical · 3 thermal violations · max loading 157.5%**

The line carried 604 MW before the outage. Buses 15, 20, 21, 22 and 23 form a
ring, and 20-21 is one side of it — so when it opens, its power has to travel the
other way round.

| Branch | Before | After | Change | Loading |
|---|---:|---:|---:|---:|
| L 22-23 | +354 MW | **+958 MW** | +605 | **157.5%** |
| L 21-22 | +43 MW | **+650 MW** | +607 | **107.9%** |
| L 15-23 | −43 MW | **−629 MW** | −586 | **105.0%** |
| L 15-20 | −330 MW | +275 MW | +604 | 50.3% |

Two details are worth pulling out.

**The 650 MW on L 21-22 is not a coincidence.** Generator 34 injects exactly
650 MW into bus 21 through its step-up transformer. With 20-21 open, bus 21 has
exactly one remaining outlet, so the entire machine output has to leave through
21-22. That branch is rated around 600 MVA, so it is overloaded by construction
the moment the line opens — no redistribution arithmetic required.

**The flow reversal on L 15-23** (−43 to −629 MW) is the signature of a ring
reconfiguring. Before the outage the ring was nearly balanced and 15-23 carried
almost nothing; afterwards it becomes a main artery. A protection engineer would
care: directional relaying set for the pre-outage flow direction needs to cope
with 629 MW the other way.

This outage also produces the largest voltage movement of any thermal case
(−0.047 pu at bus 20) — still inside the band, but it shows the ring is being
worked hard in both real and reactive terms.

## 4. L 12-13 — 132.5% on the parallel corridor

**Severity 35.1 · Warning · 2 thermal violations**

Buses 4, 5, 9, 10, 12 and 13 form a group of parallel paths carrying generation
from the west (the slack at bus 30, and generator 31) toward the load centre.
Unlike case 3 this is not a ring but a set of parallel corridors, and the
redistribution splits accordingly:

| Branch | Before | After | Change | Loading |
|---|---:|---:|---:|---:|
| L 5-10 | −323 MW | **−637 MW** | −314 | **132.5%** |
| L 9-10 | +328 MW | +617 MW | +290 | **102.6%** |
| L 9-12 | +322 MW | +33 MW | −290 | 5% |
| L 3-4 | −197 MW | −480 MW | −283 | 66% |

The 317 MW the line was carrying does not land on one neighbour: roughly 314 MW
appears on 5-10 and the 9-12/9-10 pair swaps duty between them. That is parallel
impedance division doing exactly what it should, and it is why 5-10 — already the
most heavily loaded line in the corridor at 67% in the base case — is the one
that fails. **The pre-existing loading is what decides which branch breaks, not
the size of the transfer.**

## 5. L 9-12 — 111.8%, the mirror image

**Severity 20.0 · Warning · 2 thermal violations**

The same corridor, the reciprocal outage. Generator 31's full 650 MW enters bus 9
and, with 9-12 open, has only 9-10 to leave through — again pinning a branch to a
generator's exact output (108.2%). Meanwhile 5-10 picks up 215 MW and reaches
111.8%.

Cases 4 and 5 are a matched pair: **each is the worst overload of the other.**
That mutual relationship is the useful engineering result, because it says the
corridor has no genuine redundancy — the "parallel paths" are parallel only in
topology, not in capacity. Adding a circuit to either would fix both.

## 6. L 22-23 — 111.3%, the ring seen from the other side

**Severity 15.4 · Warning · 2 thermal violations**

The reciprocal of case 3. The 354 MW on 22-23 redistributes around the ring:
15-20 goes to 676 MW (111.3%), 20-21 to 954 MW (104.1%), and 21-22 reverses.

That this outage scores 15.4 while its partner scores 70.4 is the point of using
magnitude rather than counts. Both open the same ring; the difference is that
20-21 was carrying 604 MW and 22-23 only 354 MW, so the reconfigured ring is
loaded far harder in case 3. The index reflects that; a violation count (2 vs 3)
barely would.

## 7. L 5-10 — 106.0%, three branches marginal at once

**Severity 13.1 · Warning · 3 thermal violations**

The third member of the western corridor. Its 323 MW lands almost entirely on
12-13 (+323 MW → 105.3%), while 9-10 and 9-12 again trade places. Three branches
end up between 101% and 106%.

This case is the argument for a *magnitude*-weighted index over a count-weighted
one, taken in the other direction: it has more violations than case 4 (three
versus two) and scores about a third as high, because none of them is deep. Three
branches at 1–6% over a continuous rating is an operator's afternoon; one branch
at 132% is not.

---

## What the results say about the network

**One corridor, one ring, one tail.** Every violation in the study falls into
exactly three structures: the western parallel corridor (cases 4, 5, 7, plus
L 9-10 and L 3-13 lower down the ranking), the eastern ring (cases 3 and 6, plus
L 15-20), and the radial tail (cases 1 and 2). Twenty-five of 37 contingencies do
nothing at all. Reliability is not spread evenly across a network; it concentrates
in a few structures, and the value of an automated N-1 sweep is that it finds
which ones without being told where to look.

**Generator outlets set the worst overloads.** Two of the five thermal cases have
a branch pinned to a generator's exact output because the outage left the machine
one way out. Those overloads are set by the dispatch and the topology together,
and no amount of redispatch elsewhere relieves them.

**Pre-outage loading predicts the failure.** In the western corridor, 5-10 is the
branch that overloads in three different contingencies. It is not the branch that
receives the most power in any of them — it is the one that started at 67% while
its neighbours started near 53%.

**The thermal/voltage split is a property worth stating.** Zero voltage-band
violations in 37 contingencies is a result, not an absence of one. It means
remedial action for this system is about real-power redispatch and rating
management, not reactive support.
