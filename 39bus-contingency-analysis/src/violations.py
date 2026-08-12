"""
Phases 6 and 7: voltage and thermal violation detection.

A bus fails if it breaks either voltage criterion: the emergency band, or the
deviation limit against the base case. Every record keeps the base-case value
alongside the new one, so a condition the outage caused can be told apart from
one the system was already carrying.
"""

import base_case
import config
import load_system


def find_voltage_violations(network, base, outage_name):
    """One entry per bus that fails a voltage criterion. "base" comes from save_base_case()."""
    voltages = base_case.get_bus_voltages(network)
    violations = []

    for bus in voltages:
        voltage_now = voltages[bus]
        voltage_before = base["voltages"][bus]
        change = voltage_now - voltage_before

        # Band is checked first: a bus outside it counts as a band violation even
        # if it barely moved to get there.
        if voltage_now < config.V_MIN:
            kind = "undervoltage"
            limit = config.V_MIN
            excursion = voltage_now - config.V_MIN
        elif voltage_now > config.V_MAX:
            kind = "overvoltage"
            limit = config.V_MAX
            excursion = voltage_now - config.V_MAX
        elif abs(change) > config.V_DEVIATION_LIMIT:
            kind = "deviation"
            limit = config.V_DEVIATION_LIMIT
            excursion = abs(change) - config.V_DEVIATION_LIMIT
        else:
            continue

        violations.append({
            "outage": outage_name,
            "bus": bus,
            "kind": kind,
            "vm_pu": round(voltage_now, 4),
            "limit": limit,
            "excursion": round(excursion, 4),
            "base_vm_pu": round(voltage_before, 4),
            "delta_from_base": round(change, 4),
        })

    return violations


def find_thermal_violations(network, base, branches, outage_name):
    """One entry per branch loaded above its rating."""
    loadings = base_case.get_branch_loadings(network, branches)
    violations = []

    for branch in branches:
        name = branch["name"]
        if name not in loadings:
            continue

        loading_now = loadings[name]
        if loading_now <= config.LOADING_LIMIT:
            continue

        rating, rating_unit = load_system.get_branch_rating(network, branch)
        loading_before = base["loadings"][name]

        violations.append({
            "outage": outage_name,
            "branch": name,
            "type": branch["type"],
            "p_mw": round(base_case.get_branch_power(network, branch), 2),
            "rating": round(rating, 4),
            "rating_unit": rating_unit,
            "loading_percent": round(loading_now, 1),
            "base_loading_percent": round(loading_before, 1),
            "delta_from_base": round(loading_now - loading_before, 1),
        })

    return violations


def summarize_violations(voltage_violations, thermal_violations):
    """
    Totals for the severity index. Band and deviation violations are kept apart
    because the index weights them differently.
    """
    band_excursion = 0.0
    deviation_excursion = 0.0
    undervoltage_count = 0
    overvoltage_count = 0
    deviation_count = 0
    worst_undervoltage = None
    worst_overvoltage = None
    worst_deviation = None

    for violation in voltage_violations:
        if violation["kind"] == "undervoltage":
            undervoltage_count += 1
            band_excursion += abs(violation["excursion"])
            if worst_undervoltage is None or violation["vm_pu"] < worst_undervoltage:
                worst_undervoltage = violation["vm_pu"]
        elif violation["kind"] == "overvoltage":
            overvoltage_count += 1
            band_excursion += abs(violation["excursion"])
            if worst_overvoltage is None or violation["vm_pu"] > worst_overvoltage:
                worst_overvoltage = violation["vm_pu"]
        else:
            deviation_count += 1
            deviation_excursion += abs(violation["excursion"])
            change = abs(violation["delta_from_base"])
            if worst_deviation is None or change > worst_deviation:
                worst_deviation = change

    thermal_excursion = 0.0
    worst_loading = None
    for violation in thermal_violations:
        thermal_excursion += violation["loading_percent"] - config.LOADING_LIMIT
        if worst_loading is None or violation["loading_percent"] > worst_loading:
            worst_loading = violation["loading_percent"]

    return {
        "n_voltage": len(voltage_violations),
        "n_undervoltage": undervoltage_count,
        "n_overvoltage": overvoltage_count,
        "n_deviation": deviation_count,
        "n_thermal": len(thermal_violations),
        "worst_undervoltage": worst_undervoltage,
        "worst_overvoltage": worst_overvoltage,
        "worst_deviation": worst_deviation,
        "worst_loading": worst_loading,
        "band_excursion": band_excursion,
        "deviation_excursion": deviation_excursion,
        "thermal_excursion": thermal_excursion,
    }
