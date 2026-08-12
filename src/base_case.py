"""Phase 3: solve the intact system and save it as the reference for every outage."""

import pandapower

import config


def run_power_flow(network):
    """
    AC Newton-Raphson power flow. Returns True if it converged.

    pandapower raises on failure, but for this study a failure is a result rather
    than an error, so it is caught and reported as a return value.

    init="dc" starts from a DC solution instead of a flat 1.0 pu guess, which
    helps convergence on the stressed post-outage cases.
    """
    try:
        pandapower.runpp(network, algorithm="nr", init="dc",
                         max_iteration=30, numba=False)
        return bool(network.converged)
    except Exception:
        return False


def get_bus_voltages(network):
    """Dictionary of bus number -> voltage magnitude in pu."""
    voltages = {}
    for bus in network.bus.index:
        voltage = network.res_bus.at[bus, "vm_pu"]
        # An out-of-service bus has no result, which pandas gives as NaN.
        # NaN != NaN is the standard test for it.
        if voltage == voltage:
            voltages[int(bus)] = float(voltage)
    return voltages


def get_branch_loadings(network, branches):
    """
    Dictionary of branch name -> loading in percent.

    Out-of-service branches are left out, which is what keeps a removed branch
    from showing up in its own overload list.
    """
    loadings = {}
    for branch in branches:
        if branch["type"] == "line":
            in_service = bool(network.line.at[branch["index"], "in_service"])
            loading = network.res_line.at[branch["index"], "loading_percent"]
        else:
            in_service = bool(network.trafo.at[branch["index"], "in_service"])
            loading = network.res_trafo.at[branch["index"], "loading_percent"]

        if in_service and loading == loading:
            loadings[branch["name"]] = float(loading)
    return loadings


def get_branch_power(network, branch):
    if branch["type"] == "line":
        return float(network.res_line.at[branch["index"], "p_from_mw"])
    return float(network.res_trafo.at[branch["index"], "p_hv_mw"])


def save_base_case(network, branches):
    return {
        "voltages": get_bus_voltages(network),
        "loadings": get_branch_loadings(network, branches),
    }


def check_base_case(network, branches):
    """
    Describe the intact system against both voltage bands.

    Checking the normal band too is what reveals that the published case already
    sits above 1.05 pu, which is the reason the study screens with two criteria.
    """
    voltages = get_bus_voltages(network)
    loadings = get_branch_loadings(network, branches)

    lowest_bus = None
    highest_bus = None
    for bus in voltages:
        if lowest_bus is None or voltages[bus] < voltages[lowest_bus]:
            lowest_bus = bus
        if highest_bus is None or voltages[bus] > voltages[highest_bus]:
            highest_bus = bus

    busiest_branch = None
    for name in loadings:
        if busiest_branch is None or loadings[name] > loadings[busiest_branch]:
            busiest_branch = name

    below_normal = 0
    above_normal = 0
    below_emergency = 0
    above_emergency = 0
    for bus in voltages:
        if voltages[bus] < config.V_MIN_NORMAL:
            below_normal += 1
        if voltages[bus] > config.V_MAX_NORMAL:
            above_normal += 1
        if voltages[bus] < config.V_MIN:
            below_emergency += 1
        if voltages[bus] > config.V_MAX:
            above_emergency += 1

    overloaded = 0
    for name in loadings:
        if loadings[name] > config.LOADING_LIMIT:
            overloaded += 1

    return {
        "converged": bool(network.converged),
        "v_min": voltages[lowest_bus],
        "v_min_bus": lowest_bus,
        "v_max": voltages[highest_bus],
        "v_max_bus": highest_bus,
        "max_loading": loadings[busiest_branch],
        "max_loading_branch": busiest_branch,
        "buses_below_normal": below_normal,
        "buses_above_normal": above_normal,
        "buses_below_emergency": below_emergency,
        "buses_above_emergency": above_emergency,
        "overloaded_branches": overloaded,
    }


def print_base_case(result):
    if result["converged"]:
        status = "CONVERGED"
    else:
        status = "FAILED"

    print("BASE CASE (all elements in service)")
    print("  power flow ...........", status)
    print("  minimum voltage ...... %.4f pu at bus %d"
          % (result["v_min"], result["v_min_bus"]))
    print("  maximum voltage ...... %.4f pu at bus %d"
          % (result["v_max"], result["v_max_bus"]))
    print("  maximum loading ...... %.1f%% on %s"
          % (result["max_loading"], result["max_loading_branch"]))
    print("  vs NORMAL band (%.2f-%.2f): %d under, %d over"
          % (config.V_MIN_NORMAL, config.V_MAX_NORMAL,
             result["buses_below_normal"], result["buses_above_normal"]))
    print("  vs EMERGENCY band (%.2f-%.2f): %d under, %d over"
          % (config.V_MIN, config.V_MAX,
             result["buses_below_emergency"], result["buses_above_emergency"]))
    print("  branches above %.0f%% .. %d"
          % (config.LOADING_LIMIT, result["overloaded_branches"]))
