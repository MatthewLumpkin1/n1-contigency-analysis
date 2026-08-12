"""
Runs the whole study end to end.

    python src/main.py
    python src/main.py --verbose
"""

import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base_case
import config
import contingency
import load_system
import visualization

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
FIGURES_DIR = os.path.join(PROJECT_ROOT, "figures")

RESULT_COLUMNS = [
    "rank", "name", "type", "topology", "from_bus", "to_bus", "status", "category",
    "severity", "v_min", "v_min_bus", "v_max", "max_loading", "max_loading_branch",
    "max_abs_dv", "max_abs_dv_bus", "n_voltage", "n_undervoltage", "n_overvoltage",
    "n_deviation", "n_thermal", "worst_deviation", "n_islanded", "islanded_load_mw",
    "exclusion",
]


def sort_key_severity_then_name(row):
    """
    Sort worst first, ties broken by name so two runs always produce the same order.

    Excluded branches have no score and are pushed to the bottom with -1.
    """
    if row["severity"] is None:
        return (-1.0, row["name"])
    return (row["severity"], row["name"])


def build_results_table(results):
    results = sorted(results, key=sort_key_severity_then_name, reverse=True)

    rank = 0
    for row in results:
        if row["severity"] is not None:
            rank += 1
            row["rank"] = rank
        else:
            row["rank"] = None

    table = pd.DataFrame(results)
    for column in RESULT_COLUMNS:
        if column not in table.columns:
            table[column] = None
    return table[RESULT_COLUMNS]


def count_by_status(results):
    counts = {}
    for row in results:
        status = row["status"]
        if status not in counts:
            counts[status] = 0
        counts[status] += 1
    return counts


def count_by_topology(branches):
    counts = {}
    for branch in branches:
        topology = branch["topology"]
        if topology not in counts:
            counts[topology] = 0
        counts[topology] += 1
    return counts


def find_worst_solvable(results):
    """Highest-severity contingency that the power flow could actually solve."""
    worst = None
    for row in results:
        if row["status"] != "VIOLATION" and row["status"] != "NORMAL":
            continue
        if worst is None or row["severity"] > worst["severity"]:
            worst = row
    return worst


def find_branch_by_name(branches, name):
    for branch in branches:
        if branch["name"] == name:
            return branch
    return None


def make_figures(network, branches, base, results, thermal_violations):
    """Re-runs the worst solvable outage so its voltages can be plotted."""
    worst_row = find_worst_solvable(results)
    worst_branch = find_branch_by_name(branches, worst_row["name"])

    contingency.set_branch_in_service(network, worst_branch, False)
    base_case.run_power_flow(network)
    outage_voltages = base_case.get_bus_voltages(network)
    contingency.set_branch_in_service(network, worst_branch, True)
    base_case.run_power_flow(network)

    overloaded_names = []
    for violation in thermal_violations:
        if violation["outage"] == worst_row["name"]:
            overloaded_names.append(violation["branch"])

    paths = []
    paths.append(visualization.plot_severity_ranking(
        results, os.path.join(FIGURES_DIR, "severity_ranking.png")))
    paths.append(visualization.plot_worst_voltage(
        results, os.path.join(FIGURES_DIR, "voltage_by_contingency.png")))
    paths.append(visualization.plot_branch_loading(
        results, os.path.join(FIGURES_DIR, "branch_loading.png")))
    paths.append(visualization.plot_voltage_profile(
        base, outage_voltages, worst_row["name"],
        os.path.join(FIGURES_DIR, "voltage_profile.png")))
    paths.append(visualization.plot_network_map(
        network, branches, worst_branch, overloaded_names,
        os.path.join(FIGURES_DIR, "network_worst_case.png")))
    return paths


def main(verbose=False):
    start_time = time.time()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(FIGURES_DIR, exist_ok=True)

    network = load_system.load_network()
    branches = load_system.get_all_branches(network)
    load_system.print_system_info(network)
    print()

    if not base_case.run_power_flow(network):
        print("base case did not converge - study aborted")
        return None

    base = base_case.save_base_case(network, branches)
    base_result = base_case.check_base_case(network, branches)
    base_case.print_base_case(base_result)
    print()

    load_system.make_bus_table(network).to_csv(
        os.path.join(RESULTS_DIR, "base_case_buses.csv"), index=False)
    load_system.make_branch_table(network, branches).to_csv(
        os.path.join(RESULTS_DIR, "base_case_branches.csv"), index=False)

    branches = contingency.classify_branches(network, branches)
    eligible_count = 0
    for branch in branches:
        if branch["eligible"]:
            eligible_count += 1

    print("N-1 SWEEP:", len(branches), "branches ->", eligible_count, "eligible,",
          len(branches) - eligible_count, "excluded")
    topology_counts = count_by_topology(branches)
    for topology in topology_counts:
        print("  %-20s %d" % (topology, topology_counts[topology]))
    print()

    results, voltage_violations, thermal_violations = contingency.run_all_contingencies(
        network, base, branches, verbose)

    check_restoration(network, branches, base_result)

    table = build_results_table(results)
    table.to_csv(os.path.join(RESULTS_DIR, "contingency_results.csv"), index=False)
    pd.DataFrame(voltage_violations).to_csv(
        os.path.join(RESULTS_DIR, "voltage_violations.csv"), index=False)
    pd.DataFrame(thermal_violations).to_csv(
        os.path.join(RESULTS_DIR, "thermal_violations.csv"), index=False)

    print("STATUS BREAKDOWN")
    status_counts = count_by_status(results)
    for status in status_counts:
        print("  %-16s %d" % (status, status_counts[status]))
    print()

    print("TOP 10 CONTINGENCIES")
    display_columns = ["rank", "name", "topology", "status", "severity", "v_min",
                       "max_abs_dv", "max_loading", "max_loading_branch",
                       "n_thermal", "category"]
    scored = table[table["severity"].notna()]
    print(scored.head(10)[display_columns].to_string(index=False))
    print()

    figure_paths = make_figures(network, branches, base, results, thermal_violations)
    print("figures written:")
    for path in figure_paths:
        print("  ", os.path.relpath(path, PROJECT_ROOT))

    print()
    print("study complete in %.1f s" % (time.time() - start_time))
    print("limits used: V %.2f-%.2f pu, deviation %.2f pu, loading %.0f%%"
          % (config.V_MIN, config.V_MAX, config.V_DEVIATION_LIMIT, config.LOADING_LIMIT))

    return table, voltage_violations, thermal_violations


def check_restoration(network, branches, base_result):
    """
    Confirm the sweep left the network exactly as it found it.

    A branch accidentally left out of service would quietly corrupt every result
    after it, so this is checked rather than assumed.
    """
    for branch in branches:
        if branch["type"] == "line":
            in_service = bool(network.line.at[branch["index"], "in_service"])
        else:
            in_service = bool(network.trafo.at[branch["index"], "in_service"])
        if not in_service:
            raise RuntimeError("branch " + branch["name"] + " was not restored")

    if not base_case.run_power_flow(network):
        raise RuntimeError("base case will not solve after the sweep")

    recheck = base_case.check_base_case(network, branches)
    if abs(recheck["v_min"] - base_result["v_min"]) > 1e-9:
        raise RuntimeError("base case drifted during the sweep")

    print("restoration check ....... PASS (base case reproduces exactly)")
    print()


if __name__ == "__main__":
    main("--verbose" in sys.argv)
