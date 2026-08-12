"""Phase 2: load the 39-bus system and describe it."""

import pandas as pd
import pandapower.networks


def load_network():
    return pandapower.networks.case39()


def get_all_branches(network):
    """
    One list describing every line and transformer the same way.

    pandapower keeps lines and transformers in separate tables with different
    column names. Flattening them into one list here is what lets the contingency
    sweep be a single loop instead of two nearly identical ones.
    """
    branches = []

    for row_index in network.line.index:
        branches.append({
            "type": "line",
            "index": int(row_index),
            "from_bus": int(network.line.at[row_index, "from_bus"]),
            "to_bus": int(network.line.at[row_index, "to_bus"]),
        })

    for row_index in network.trafo.index:
        branches.append({
            "type": "trafo",
            "index": int(row_index),
            # A transformer's ends are named high/low voltage, but they are still
            # just the two ends of a branch.
            "from_bus": int(network.trafo.at[row_index, "hv_bus"]),
            "to_bus": int(network.trafo.at[row_index, "lv_bus"]),
        })

    for branch in branches:
        if branch["type"] == "line":
            label = "L"
        else:
            label = "T"
        branch["name"] = label + " " + str(branch["from_bus"]) + "-" + str(branch["to_bus"])

    return branches


def get_branch_rating(network, branch):
    """Lines are rated in kA and transformers in MVA, so the unit travels with it."""
    if branch["type"] == "line":
        return float(network.line.at[branch["index"], "max_i_ka"]), "kA"
    return float(network.trafo.at[branch["index"], "sn_mva"]), "MVA"


def get_system_info(network):
    info = {}
    info["buses"] = len(network.bus)
    info["generators"] = len(network.gen) + len(network.ext_grid)
    info["pv_generators"] = len(network.gen)
    info["loads"] = len(network.load)
    info["lines"] = len(network.line)
    info["transformers"] = len(network.trafo)
    info["branches_total"] = len(network.line) + len(network.trafo)
    info["base_mva"] = float(network.sn_mva)
    info["slack_bus"] = int(network.ext_grid.at[network.ext_grid.index[0], "bus"])
    info["total_load_mw"] = float(network.load["p_mw"].sum())
    info["total_load_mvar"] = float(network.load["q_mvar"].sum())
    info["nominal_kv"] = sorted(network.bus["vn_kv"].unique().tolist())
    return info


def print_system_info(network):
    info = get_system_info(network)
    print("NEW ENGLAND 39-BUS TEST SYSTEM")
    print("  buses ................", info["buses"])
    print("  generators ...........", info["generators"],
          " (" + str(info["pv_generators"]) + " PV + 1 slack at bus "
          + str(info["slack_bus"]) + ")")
    print("  loads ................", info["loads"])
    print("  transmission lines ...", info["lines"])
    print("  transformers .........", info["transformers"])
    print("  total branches .......", info["branches_total"])
    print("  system base .......... %.0f MVA" % info["base_mva"])
    print("  nominal voltages .....", info["nominal_kv"], "kV")
    print("  total load ........... %.1f MW / %.1f Mvar"
          % (info["total_load_mw"], info["total_load_mvar"]))


def make_bus_table(network):
    """Bus summary table. Needs a solved power flow for the voltage columns."""
    generation_by_bus = network.gen.groupby("bus")["p_mw"].sum()
    load_mw_by_bus = network.load.groupby("bus")["p_mw"].sum()
    load_mvar_by_bus = network.load.groupby("bus")["q_mvar"].sum()

    generator_buses = list(network.gen["bus"])
    slack_bus = int(network.ext_grid.at[network.ext_grid.index[0], "bus"])

    rows = []
    for bus in network.bus.index:
        if bus == slack_bus:
            bus_type = "slack"
        elif bus in generator_buses:
            bus_type = "generator"
        else:
            bus_type = "load"

        generation = 0.0
        if bus in generation_by_bus.index:
            generation = float(generation_by_bus[bus])

        load_mw = 0.0
        if bus in load_mw_by_bus.index:
            load_mw = float(load_mw_by_bus[bus])

        load_mvar = 0.0
        if bus in load_mvar_by_bus.index:
            load_mvar = float(load_mvar_by_bus[bus])

        rows.append({
            "bus": int(bus),
            "type": bus_type,
            "vn_kv": float(network.bus.at[bus, "vn_kv"]),
            "vm_pu": float(network.res_bus.at[bus, "vm_pu"]),
            "va_degree": float(network.res_bus.at[bus, "va_degree"]),
            "gen_mw": generation,
            "load_mw": load_mw,
            "load_mvar": load_mvar,
        })

    return pd.DataFrame(rows).round(4)


def make_branch_table(network, branches):
    rows = []
    for branch in branches:
        rating, rating_unit = get_branch_rating(network, branch)

        if branch["type"] == "line":
            active_power = float(network.res_line.at[branch["index"], "p_from_mw"])
            reactive_power = float(network.res_line.at[branch["index"], "q_from_mvar"])
            loading = float(network.res_line.at[branch["index"], "loading_percent"])
        else:
            active_power = float(network.res_trafo.at[branch["index"], "p_hv_mw"])
            reactive_power = float(network.res_trafo.at[branch["index"], "q_hv_mvar"])
            loading = float(network.res_trafo.at[branch["index"], "loading_percent"])

        rows.append({
            "name": branch["name"],
            "type": branch["type"],
            "from_bus": branch["from_bus"],
            "to_bus": branch["to_bus"],
            "p_mw": active_power,
            "q_mvar": reactive_power,
            "rating": rating,
            "rating_unit": rating_unit,
            "loading_percent": loading,
        })

    return pd.DataFrame(rows).round(4)
