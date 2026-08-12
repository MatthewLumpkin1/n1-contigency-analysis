"""
Phase 8: the contingency severity index.

    Severity = 100 * (excursion beyond the emergency voltage band, pu)
             +  50 * (excursion beyond the deviation criterion, pu)
             +   1 * (overload above 100%, percent)
             + 500  if the power flow did not converge
             + 1000 if the outage separated the network

The index adds up how far past each limit things went rather than counting
violations. Six buses 0.001 pu low is a rounding error and one bus 0.06 pu low is
a warning about voltage collapse, and a count ranks those two backwards.

The factor of 100 is what puts voltage and thermal terms on a common scale.
Deviation counts half because it is a stress warning, not a broken limit. The
failure penalties are unreachable by the violation terms on purpose: a case the
solver cannot evaluate has to outrank every case it can.
"""

import config


def calculate_severity(status, summary=None):
    """Severity score for one contingency. "summary" is only needed for solvable cases."""
    if status == "ISLANDED":
        return config.PENALTY_ISLANDED
    if status == "NON-CONVERGENT":
        return config.PENALTY_NON_CONVERGENT

    if summary is None:
        return 0.0

    score = 0.0
    score += config.WEIGHT_VOLTAGE_BAND * summary["band_excursion"]
    score += config.WEIGHT_VOLTAGE_DEVIATION * summary["deviation_excursion"]
    score += config.WEIGHT_THERMAL * summary["thermal_excursion"]
    return round(score, 2)


def classify_severity(status, score):
    """Score to a label a planner can sort by."""
    if status == "ISLANDED" or status == "NON-CONVERGENT":
        return "Critical"
    if score >= config.CRITICAL_THRESHOLD:
        return "Critical"
    if score > 0.0:
        return "Warning"
    return "OK"
