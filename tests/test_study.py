"""
Verification tests. Run with:  python tests/test_study.py

Each test checks a way the study could be silently wrong, not just whether it
runs: a branch left out of service, a failed case poisoning the next one, a limit
that never actually fires, a ranking that changes between runs.
"""

import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import networkx

import base_case
import config
import contingency
import load_system
import severity
import violations

tests_run = 0
tests_failed = 0


def check(condition, description):
    global tests_run, tests_failed
    tests_run += 1
    if condition:
        print("  PASS  " + description)
    else:
        print("  FAIL  " + description)
        tests_failed += 1


def build_solved_system():
    network = load_system.load_network()
    branches = contingency.classify_branches(network, load_system.get_all_branches(network))
    base_case.run_power_flow(network)
    return network, branches


def test_base_case():
    print("Base case")
    network, branches = build_solved_system()
    result = base_case.check_base_case(network, branches)
    info = load_system.get_system_info(network)

    check(result["converged"], "base case converges")
    check(info["buses"] == 39, "39 buses")
    check(info["branches_total"] == 46, "46 branches")
    check(info["generators"] == 10, "10 generators")

    # If the base case broke the emergency band, every contingency would inherit
    # the violation and the ranking would be meaningless.
    check(result["buses_below_emergency"] == 0 and result["buses_above_emergency"] == 0,
          "base case is inside the emergency band")
    check(result["overloaded_branches"] == 0, "base case has no overloads")

    # Documents the finding that motivated the two-criterion screen.
    check(result["buses_above_normal"] > 0,
          "base case does exceed the normal band (why two criteria are used)")


def test_topology():
    print("Topology classification")
    network, branches = build_solved_system()

    # Cross-check networkx against the obvious method: delete every edge in turn
    # and see whether the graph falls apart.
    graph = contingency.build_network_graph(network, branches)
    brute_force = []
    for bus_a, bus_b in list(graph.edges()):
        graph.remove_edge(bus_a, bus_b)
        if not networkx.is_connected(graph):
            brute_force.append(sorted([bus_a, bus_b]))
        graph.add_edge(bus_a, bus_b)

    bridge_names = contingency.find_bridge_branches(network, branches)
    bridge_pairs = []
    for branch in branches:
        if branch["name"] in bridge_names:
            bridge_pairs.append(sorted([branch["from_bus"], branch["to_bus"]]))

    check(sorted(bridge_pairs) == sorted(brute_force),
          "bridge detection matches brute-force edge deletion")

    step_ups = 0
    step_ups_excluded = 0
    for branch in branches:
        if branch["topology"] == "generator step-up":
            step_ups += 1
            if not branch["eligible"]:
                step_ups_excluded += 1
    check(step_ups == 9, "nine radial generator buses identified")
    check(step_ups_excluded == 9, "all generator step-ups excluded from the ranking")

    names = []
    for branch in branches:
        names.append(branch["name"])
    check(len(names) == len(set(names)), "no branch appears twice")


def test_sweep_integrity():
    print("Sweep integrity")
    network, branches = build_solved_system()
    base = base_case.save_base_case(network, branches)
    results, voltage_violations, thermal_violations = \
        contingency.run_all_contingencies(network, base, branches)

    all_in_service = True
    for branch in branches:
        if branch["type"] == "line":
            in_service = bool(network.line.at[branch["index"], "in_service"])
        else:
            in_service = bool(network.trafo.at[branch["index"], "in_service"])
        if not in_service:
            all_in_service = False
    check(all_in_service, "every branch restored after the sweep")

    base_case.run_power_flow(network)
    after = base_case.save_base_case(network, branches)
    check(after["voltages"] == base["voltages"], "base-case voltages unchanged")
    check(after["loadings"] == base["loadings"], "base-case loadings unchanged")

    eligible = 0
    screened = 0
    for branch in branches:
        if branch["eligible"]:
            eligible += 1
    for row in results:
        if row["status"] != "EXCLUDED":
            screened += 1
    check(eligible == screened, "every eligible branch screened exactly once")

    islanded_ok = True
    found_islanded = False
    for row in results:
        if row["status"] == "ISLANDED":
            found_islanded = True
            if row["n_islanded"] <= 0 or row["islanded_load_mw"] < 0:
                islanded_ok = False
    check(found_islanded and islanded_ok, "islanded cases report disconnected load")


def test_failed_case_does_not_corrupt_the_next():
    print("Contamination")
    # Run a known solvable case on a clean network, then run it again right after
    # an islanding case, and confirm the answer is identical.
    network, branches = build_solved_system()
    base = base_case.save_base_case(network, branches)
    solvable = None
    islanding = None
    for branch in branches:
        if branch["name"] == "L 20-21":
            solvable = branch
        if branch["name"] == "L 15-18":
            islanding = branch

    contingency.set_branch_in_service(network, solvable, False)
    clean_result, _, _ = contingency.evaluate_contingency(network, base, branches, "L 20-21")
    contingency.set_branch_in_service(network, solvable, True)

    contingency.set_branch_in_service(network, islanding, False)
    contingency.evaluate_contingency(network, base, branches, "L 15-18")
    contingency.set_branch_in_service(network, islanding, True)

    contingency.set_branch_in_service(network, solvable, False)
    after_result, _, _ = contingency.evaluate_contingency(network, base, branches, "L 20-21")
    contingency.set_branch_in_service(network, solvable, True)

    check(clean_result["max_loading"] == after_result["max_loading"],
          "loading unchanged after an islanded case ran first")
    check(clean_result["v_min"] == after_result["v_min"],
          "voltage unchanged after an islanded case ran first")


def test_reproducible():
    print("Reproducibility")
    scores = []
    for attempt in range(2):
        network, branches = build_solved_system()
        base = base_case.save_base_case(network, branches)
        results, _, _ = contingency.run_all_contingencies(network, base, branches)
        run_scores = {}
        for row in results:
            run_scores[row["name"]] = row["severity"]
        scores.append(run_scores)
    check(scores[0] == scores[1], "two identical runs give identical severities")


def test_detectors():
    print("Violation detectors")
    # Driven with synthetic voltages written straight into the results table, so
    # each limit is tested on data that breaks it and data that does not.
    network, branches = build_solved_system()
    base = base_case.save_base_case(network, branches)

    network.res_bus.at[5, "vm_pu"] = config.V_MIN - 0.02
    found = violations.find_voltage_violations(network, base, "synthetic")
    hit = None
    for violation in found:
        if violation["bus"] == 5:
            hit = violation
    check(hit is not None and hit["kind"] == "undervoltage", "undervoltage detected")
    check(hit is not None and abs(hit["excursion"] + 0.02) < 1e-6,
          "undervoltage excursion is correct")

    network.res_bus.at[5, "vm_pu"] = config.V_MAX + 0.03
    found = violations.find_voltage_violations(network, base, "synthetic")
    hit = None
    for violation in found:
        if violation["bus"] == 5:
            hit = violation
    check(hit is not None and hit["kind"] == "overvoltage", "overvoltage detected")

    # A bus can be perfectly legal in absolute terms and still fail criterion 2.
    network.res_bus.at[5, "vm_pu"] = base["voltages"][5] - (config.V_DEVIATION_LIMIT + 0.01)
    found = violations.find_voltage_violations(network, base, "synthetic")
    hit = None
    for violation in found:
        if violation["bus"] == 5:
            hit = violation
    check(hit is not None and hit["kind"] == "deviation", "deviation detected inside the band")
    check(hit is not None and hit["vm_pu"] > config.V_MIN,
          "the deviation case really is inside the band")

    base_case.run_power_flow(network)
    found = violations.find_voltage_violations(network, base, "synthetic")
    check(len(found) == 0, "no violations reported on the intact system")

    network.res_line.at[3, "loading_percent"] = 142.0
    found = violations.find_thermal_violations(network, base, branches, "synthetic")
    hit = None
    for violation in found:
        if violation["loading_percent"] == 142.0:
            hit = violation
    check(hit is not None, "thermal overload detected")
    check(hit is not None and hit["delta_from_base"] > 0, "thermal delta from base is positive")

    # The removed element must never show up in its own overload list.
    network.line.at[3, "in_service"] = False
    network.res_line.at[3, "loading_percent"] = 999.0
    found = violations.find_thermal_violations(network, base, branches, "synthetic")
    reported = False
    for violation in found:
        if violation["loading_percent"] == 999.0:
            reported = True
    check(not reported, "an out-of-service branch is not flagged as overloaded")


def test_severity_index():
    print("Severity index")
    worst_violation = severity.calculate_severity("VIOLATION", {
        "band_excursion": 0.05, "deviation_excursion": 0.05, "thermal_excursion": 60.0})
    non_convergent = severity.calculate_severity("NON-CONVERGENT")
    islanded = severity.calculate_severity("ISLANDED")

    check(worst_violation < non_convergent, "non-convergent outranks any violation")
    check(non_convergent < islanded, "islanded outranks non-convergent")

    small = severity.calculate_severity("VIOLATION", {
        "band_excursion": 0.0, "deviation_excursion": 0.0, "thermal_excursion": 10.0})
    large = severity.calculate_severity("VIOLATION", {
        "band_excursion": 0.0, "deviation_excursion": 0.0, "thermal_excursion": 20.0})
    check(small < large, "severity increases with overload")

    # The whole point of the index: one deep violation beats several shallow ones.
    many_shallow = severity.calculate_severity("VIOLATION", {
        "band_excursion": 0.006, "deviation_excursion": 0.0, "thermal_excursion": 0.0})
    one_deep = severity.calculate_severity("VIOLATION", {
        "band_excursion": 0.06, "deviation_excursion": 0.0, "thermal_excursion": 0.0})
    check(one_deep > many_shallow, "one deep violation outranks six shallow ones")

    clean = severity.calculate_severity("NORMAL", {
        "band_excursion": 0.0, "deviation_excursion": 0.0, "thermal_excursion": 0.0})
    check(clean == 0.0, "a clean contingency scores zero")
    check(severity.classify_severity("NORMAL", 0.0) == "OK", "zero score classifies as OK")
    check(severity.classify_severity("VIOLATION", 70.0) == "Critical", "70 is Critical")
    check(severity.classify_severity("VIOLATION", 5.0) == "Warning", "5 is Warning")
    check(severity.classify_severity("ISLANDED", 1000.0) == "Critical", "islanded is Critical")


def run_all_tests():
    test_base_case()
    test_topology()
    test_sweep_integrity()
    test_failed_case_does_not_corrupt_the_next()
    test_reproducible()
    test_detectors()
    test_severity_index()

    print()
    print(str(tests_run - tests_failed) + "/" + str(tests_run) + " tests passed")
    if tests_failed > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
