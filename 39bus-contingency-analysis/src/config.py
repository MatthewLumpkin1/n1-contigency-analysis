"""Limits and weights used by the study. Reasoning is in docs/methodology.md."""

# Post-contingency (emergency) voltage band, per unit. The published case39 already
# sits above 1.05 pu at seven buses with everything in service, so screening N-1
# against the normal 0.95-1.05 band would flag pre-existing conditions as
# contingency violations. Planning practice relaxes the band after an outage anyway.
V_MIN = 0.90
V_MAX = 1.10

# Second voltage criterion: a bus can stay inside the band and still be a problem
# if the outage moved it a long way, since that is what drains reactive reserve.
V_DEVIATION_LIMIT = 0.05

# Normal-condition band. Only used to describe the base case, never to screen.
V_MIN_NORMAL = 0.95
V_MAX_NORMAL = 1.05

LOADING_LIMIT = 100.0

# Voltage excursions are in pu and thermal excursions in percent. The factor of 100
# puts a 0.01 pu excursion on the same scale as a 1% overload so they can be added.
WEIGHT_VOLTAGE_BAND = 100.0
WEIGHT_VOLTAGE_DEVIATION = 50.0   # half weight: stress warning, not a broken limit
WEIGHT_THERMAL = 1.0

# Set high enough that no combination of violations can reach them.
PENALTY_NON_CONVERGENT = 500.0
PENALTY_ISLANDED = 1000.0

CRITICAL_THRESHOLD = 50.0
