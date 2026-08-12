"""
Phases 4 and 5: the automatic N-1 contingency engine.

classify_branches() decides what each branch outage actually represents, then
run_all_contingencies() removes every eligible branch in turn, re-solves,
classifies the outcome, and puts the branch back.
"""

import networkx
import pandapower.topology

import base_case
import severity
import violations


def find_radial_buses(network, branches):
    """
    Buses with only one branch attached. In case39 these are the nine generator
    buses behind a step-up transformer.
    """
    connection_count = {}
    for bus in network.bus.index:
        connection_count[int(bus)] = 0

    for branch in branches:
        connection_count[branch["from_bus"]] += 1
        connection_count[branch["to_bus"]] += 1

    radial_buses = []
    for bus in connection_count:
        if connection_count[bus] <= 1:
            radial_buses.append(bus)
    return radial_buses


def build_network_graph(network, branches):
    """Buses as nodes, branches as edges. Connectivity only, no electrical data."""
    graph = networkx.Graph()
    for bus in network.bus.index:
        graph.add_node(int(bus))
    for branch in branches:
        graph.add_edge(branch["from_bus"], branch["to_bus"])
    return graph


def find_bridge_branches(network, branches):
    """
    Branches whose removal would split the network. Graph theory calls these
    bridges, and networkx finds them all in one pass on the intact system.

    Worth finding in advance: a bridge outage cannot be assessed by a power flow
    at all, since there is no longer one connected network to solve. Better to
    detect that up front than to let Newton-Raphson fail and call it a result.
    """
    graph = build_network_graph(network, branches)

    bridge_pairs = []
    for bus_a, bus_b in networkx.bridges(graph):
        bridge_pairs.append(sorted([int(bus_a), int(bus_b)]))

    bridge_names = []
    for branch in branches:
        pair = sorted([branch["from_bus"], branch["to_bus"]])
        if pair in bridge_pairs:
            bridge_names.append(branch["name"])
    return bridge_names


def classify_branches(network, branches):
    """
    Label each branch with the kind of contingency its outage really is.

    generator step-up  Only connection to a generator bus, so removing it is a
                       generator outage in disguise and disconnects the bus by
                       definition. Excluded from the ranking, otherwise nine
                       maximal scores sit on top of every real result.
    structural bridge  Splits the network somewhere other than a generator tail.
                       A real transmission contingency, kept in the ranking, but
                       not solvable with a power flow.
    meshed             Everything else, and the bulk of the study.
    """
    radial_buses = find_radial_buses(network, branches)
    bridge_names = find_bridge_branches(network, branches)

    for branch in branches:
        touches_radial_bus = (branch["from_bus"] in radial_buses
                              or branch["to_bus"] in radial_buses)

        if touches_radial_bus:
            if branch["from_bus"] in radial_buses:
                generator_bus = branch["from_bus"]
            else:
                generator_bus = branch["to_bus"]
            branch["topology"] = "generator step-up"
            branch["eligible"] = False
            branch["exclusion"] = "sole connection to generator bus " + str(generator_bus)
        elif branch["name"] in bridge_names:
            branch["topology"] = "structural bridge"
            branch["eligible"] = True
            branch["exclusion"] = ""
        else:
            branch["topology"] = "meshed"
            branch["eligible"] = True
            branch["exclusion"] = ""

    return branches


def set_branch_in_service(network, branch, in_service):
    if branch["type"] == "line":
        network.line.at[branch["index"], "in_service"] = in_service
    else:
        network.trafo.at[branch["index"], "in_service"] = in_service


def find_islanded_buses(network):
    """
    Buses that lost their path to the slack. "Islanded" means separated from the
    slack specifically, since without it the power flow has no reference.
    """
    graph = pandapower.topology.create_nxgraph(network, respect_switches=True)
    slack_bus = int(network.ext_grid.at[network.ext_grid.index[0], "bus"])

    in_service_buses = []
    for bus in network.bus.index:
        if bool(network.bus.at[bus, "in_service"]):
            in_service_buses.append(int(bus))

    if slack_bus not in graph:
        return in_service_buses

    connected_to_slack = pandapower.topology.connected_component(graph, slack_bus)
    still_connected = []
    for bus in connected_to_slack:
        still_connected.append(int(bus))

    islanded = []
    for bus in in_service_buses:
        if bus not in still_connected:
            islanded.append(bus)
    return islanded


def find_worst_voltage_change(network, base):
    """
    Largest voltage change from base case, and where. Recorded for every
    contingency, not just violating ones, so the study can report actual margin.
    """
    voltages = base_case.get_bus_voltages(network)

    worst_bus = None
    worst_change = 0.0
    for bus in voltages:
        change = abs(voltages[bus] - base["voltages"][bus])
        if worst_bus is None or change > worst_change:
            worst_bus = bus
            worst_change = change

    return worst_change, worst_bus


def evaluate_contingency(network, base, branches, outage_name):
    """
    Assess one contingency; the branch must already be out of service.
    Returns the result row plus the voltage and thermal violation lists.
    """
    islanded_buses = find_islanded_buses(network)
    if len(islanded_buses) > 0:
        disconnected_load = 0.0
        for load_row in network.load.index:
            load_bus = int(network.load.at[load_row, "bus"])
            if load_bus in islanded_buses:
                disconnected_load += float(network.load.at[load_row, "p_mw"])

        result = {
            "status": "ISLANDED",
            "n_islanded": len(islanded_buses),
            "islanded_load_mw": round(disconnected_load, 1),
        }
        return result, [], []

    if not base_case.run_power_flow(network):
        result = {
            "status": "NON-CONVERGENT",
            "n_islanded": 0,
            "islanded_load_mw": 0.0,
        }
        return result, [], []

    voltage_violations = violations.find_voltage_violations(network, base, outage_name)
    thermal_violations = violations.find_thermal_violations(network, base, branches,
                                                            outage_name)
    summary = violations.summarize_violations(voltage_violations, thermal_violations)

    if summary["n_voltage"] > 0 or summary["n_thermal"] > 0:
        status = "VIOLATION"
    else:
        status = "NORMAL"

    voltages = base_case.get_bus_voltages(network)
    loadings = base_case.get_branch_loadings(network, branches)

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

    worst_change, worst_change_bus = find_worst_voltage_change(network, base)

    result = {
        "status": status,
        "n_islanded": 0,
        "islanded_load_mw": 0.0,
        "v_min": round(voltages[lowest_bus], 4),
        "v_min_bus": lowest_bus,
        "v_max": round(voltages[highest_bus], 4),
        "v_max_bus": highest_bus,
        "max_loading": round(loadings[busiest_branch], 1),
        "max_loading_branch": busiest_branch,
        "max_abs_dv": round(worst_change, 4),
        "max_abs_dv_bus": worst_change_bus,
        "n_voltage": summary["n_voltage"],
        "n_undervoltage": summary["n_undervoltage"],
        "n_overvoltage": summary["n_overvoltage"],
        "n_deviation": summary["n_deviation"],
        "n_thermal": summary["n_thermal"],
        "worst_undervoltage": summary["worst_undervoltage"],
        "worst_overvoltage": summary["worst_overvoltage"],
        "worst_deviation": summary["worst_deviation"],
        "worst_loading": summary["worst_loading"],
    }
    return result, voltage_violations, thermal_violations


def run_all_contingencies(network, base, branches, verbose=False):
    """
    The main N-1 loop: remove a branch, check connectivity, solve, record and
    score, restore. Returns one result row per branch plus the violation records.
    """
    all_results = []
    all_voltage_violations = []
    all_thermal_violations = []

    for branch in branches:
        if not branch["eligible"]:
            all_results.append({
                "name": branch["name"],
                "type": branch["type"],
                "topology": branch["topology"],
                "from_bus": branch["from_bus"],
                "to_bus": branch["to_bus"],
                "exclusion": branch["exclusion"],
                "status": "EXCLUDED",
                "severity": None,
                "category": "Excluded",
            })
            continue

        set_branch_in_service(network, branch, False)
        try:
            result, voltage_violations, thermal_violations = evaluate_contingency(
                network, base, branches, branch["name"])
        finally:
            # finally guarantees the restore even if evaluation raises. One branch
            # left out of service would corrupt every contingency after it.
            set_branch_in_service(network, branch, True)

        summary = violations.summarize_violations(voltage_violations,
                                                  thermal_violations)
        score = severity.calculate_severity(result["status"], summary)

        row = {
            "name": branch["name"],
            "type": branch["type"],
            "topology": branch["topology"],
            "from_bus": branch["from_bus"],
            "to_bus": branch["to_bus"],
            "exclusion": branch["exclusion"],
            "severity": score,
            "category": severity.classify_severity(result["status"], score),
        }
        for key in result:
            row[key] = result[key]

        all_results.append(row)
        all_voltage_violations = all_voltage_violations + voltage_violations
        all_thermal_violations = all_thermal_violations + thermal_violations

        if verbose:
            print("  %-10s %-16s severity %8.2f"
                  % (branch["name"], result["status"], score))

    return all_results, all_voltage_violations, all_thermal_violations
