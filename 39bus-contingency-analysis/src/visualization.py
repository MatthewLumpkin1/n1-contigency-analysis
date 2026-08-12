"""Phase 10: the five figures. Each one answers something the tables cannot."""

import json

import matplotlib
matplotlib.use("Agg")           # no display available, so render straight to file
import matplotlib.pyplot as plt
import networkx
import pandapower.topology

import config

CATEGORY_COLORS = {
    "Critical": "#b2182b",
    "Warning": "#ef8a62",
    "OK": "#4d9221",
}


def save_figure(figure, path):
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def get_scored_results(results):
    """Only the contingencies that were actually screened, worst first."""
    scored = []
    for row in results:
        if row["severity"] is not None:
            scored.append(row)
    scored.sort(key=sort_by_severity, reverse=True)
    return scored


def sort_by_severity(row):
    return row["severity"]


def plot_severity_ranking(results, path, top_n=25):
    scored = get_scored_results(results)[:top_n]

    names = []
    scores = []
    colors = []
    for row in scored:
        names.append(row["name"])
        scores.append(row["severity"])
        colors.append(CATEGORY_COLORS[row["category"]])

    figure, axes = plt.subplots(figsize=(11, 5))
    axes.bar(names, scores, color=colors)
    axes.set_xlabel("Contingency (element removed)")
    axes.set_ylabel("Severity index")
    axes.set_title("N-1 contingency severity ranking - top " + str(len(scored)))
    axes.tick_params(axis="x", rotation=90)
    axes.grid(axis="y", alpha=0.3)

    legend_patches = []
    legend_labels = []
    for category in CATEGORY_COLORS:
        legend_patches.append(plt.Rectangle((0, 0), 1, 1, color=CATEGORY_COLORS[category]))
        legend_labels.append(category)
    axes.legend(legend_patches, legend_labels, title="Classification")

    return save_figure(figure, path)


def plot_worst_voltage(results, path):
    solvable = []
    for row in get_scored_results(results):
        if "v_min" in row:
            solvable.append(row)
    solvable.sort(key=sort_by_v_min)

    names = []
    voltages = []
    colors = []
    lowest = 1.0
    for row in solvable:
        names.append(row["name"])
        voltages.append(row["v_min"])
        colors.append(CATEGORY_COLORS[row["category"]])
        if row["v_min"] < lowest:
            lowest = row["v_min"]

    figure, axes = plt.subplots(figsize=(11, 5))
    axes.bar(names, voltages, color=colors)
    axes.axhline(config.V_MIN, linestyle="--", color="k", linewidth=1,
                 label="%.2f pu emergency limit" % config.V_MIN)
    # Zoomed so the differences between contingencies are visible; a 0-to-1 axis
    # would make every bar look identical.
    axes.set_ylim(min(0.93, lowest - 0.005), 1.0)
    axes.set_xlabel("Contingency (element removed)")
    axes.set_ylabel("Lowest bus voltage after outage (pu)")
    axes.set_title("Worst bus voltage by contingency")
    axes.tick_params(axis="x", rotation=90)
    axes.grid(axis="y", alpha=0.3)
    axes.legend()

    return save_figure(figure, path)


def sort_by_v_min(row):
    return row["v_min"]


def sort_by_max_loading(row):
    return row["max_loading"]


def plot_branch_loading(results, path):
    solvable = []
    for row in get_scored_results(results):
        if "max_loading" in row:
            solvable.append(row)
    solvable.sort(key=sort_by_max_loading, reverse=True)

    names = []
    loadings = []
    colors = []
    for row in solvable:
        names.append(row["name"])
        loadings.append(row["max_loading"])
        colors.append(CATEGORY_COLORS[row["category"]])

    figure, axes = plt.subplots(figsize=(11, 5))
    axes.bar(names, loadings, color=colors)
    axes.axhline(config.LOADING_LIMIT, linestyle="--", color="k", linewidth=1,
                 label="%.0f%% rating" % config.LOADING_LIMIT)
    axes.set_xlabel("Contingency (element removed)")
    axes.set_ylabel("Highest remaining branch loading (%)")
    axes.set_title("Maximum post-contingency branch loading")
    axes.tick_params(axis="x", rotation=90)
    axes.grid(axis="y", alpha=0.3)
    axes.legend()

    return save_figure(figure, path)


def plot_voltage_profile(base, outage_voltages, outage_name, path):
    buses = sorted(base["voltages"].keys())

    base_values = []
    outage_values = []
    for bus in buses:
        base_values.append(base["voltages"][bus])
        outage_values.append(outage_voltages[bus])

    figure, axes = plt.subplots(figsize=(11, 5))
    axes.plot(buses, base_values, "o-", markersize=4, color="#2166ac", label="Base case")
    axes.plot(buses, outage_values, "s-", markersize=4, color="#b2182b",
              label="Outage " + outage_name)
    axes.axhline(config.V_MIN, linestyle="--", color="k", linewidth=1)
    axes.axhline(config.V_MAX, linestyle="--", color="k", linewidth=1)
    axes.set_xlabel("Bus")
    axes.set_ylabel("Voltage magnitude (pu)")
    axes.set_title("Voltage profile: base case vs " + outage_name)
    axes.grid(alpha=0.3)
    axes.legend()

    return save_figure(figure, path)


def get_bus_positions(network, graph):
    """
    Coordinates for the network drawing.

    case39 ships with real one-line diagram coordinates in net.bus.geo, stored as
    GeoJSON text. Using them puts the figure in the same geography as the
    published diagram instead of an abstract force-directed blob.
    """
    positions = {}
    for bus in graph.nodes():
        geo_text = network.bus.at[bus, "geo"]
        coordinates = json.loads(geo_text)["coordinates"]
        positions[bus] = (coordinates[0], coordinates[1])
    return positions


def plot_network_map(network, branches, outage_branch, overloaded_names, path):
    graph = pandapower.topology.create_nxgraph(network, respect_switches=False)
    positions = get_bus_positions(network, graph)

    # networkx gives edges back as bus pairs, so the branch names have to be
    # matched back to pairs to know which edge to colour.
    removed_pair = sorted([outage_branch["from_bus"], outage_branch["to_bus"]])
    overloaded_pairs = []
    for branch in branches:
        if branch["name"] in overloaded_names:
            overloaded_pairs.append(sorted([branch["from_bus"], branch["to_bus"]]))

    edge_colors = []
    edge_widths = []
    for bus_a, bus_b in graph.edges():
        pair = sorted([int(bus_a), int(bus_b)])
        if pair == removed_pair:
            edge_colors.append("#b2182b")
            edge_widths.append(3.5)
        elif pair in overloaded_pairs:
            edge_colors.append("#ef8a62")
            edge_widths.append(3.0)
        else:
            edge_colors.append("#bbbbbb")
            edge_widths.append(1.0)

    generator_buses = list(network.gen["bus"]) + list(network.ext_grid["bus"])
    load_buses = list(network.load["bus"])

    node_colors = []
    node_sizes = []
    for bus in graph.nodes():
        if bus in generator_buses:
            node_colors.append("#2166ac")
            node_sizes.append(300)
        elif bus in load_buses:
            node_colors.append("#f7f7f7")
            node_sizes.append(230)
        else:
            node_colors.append("#cccccc")
            node_sizes.append(150)

    figure, axes = plt.subplots(figsize=(12, 10))
    networkx.draw_networkx_edges(graph, positions, edge_color=edge_colors,
                                 width=edge_widths, ax=axes)
    networkx.draw_networkx_nodes(graph, positions, node_color=node_colors,
                                 node_size=node_sizes, edgecolors="#333333",
                                 linewidths=0.8, ax=axes)
    networkx.draw_networkx_labels(graph, positions, font_size=8, ax=axes)

    legend_lines = [
        plt.Line2D([], [], color="#b2182b", linewidth=3.5,
                   label="removed: " + outage_branch["name"]),
        plt.Line2D([], [], color="#ef8a62", linewidth=3.0, label="overloaded after outage"),
        plt.Line2D([], [], color="#bbbbbb", linewidth=1.5, label="in service, within rating"),
        plt.Line2D([], [], marker="o", linestyle="", markerfacecolor="#2166ac",
                   markeredgecolor="#333", markersize=11, label="generator bus"),
        plt.Line2D([], [], marker="o", linestyle="", markerfacecolor="#f7f7f7",
                   markeredgecolor="#333", markersize=10, label="load bus"),
    ]
    axes.legend(handles=legend_lines, loc="lower left", framealpha=0.95, fontsize=9)
    axes.set_title("Worst solvable contingency: outage of " + outage_branch["name"]
                   + "\n" + str(len(overloaded_names)) + " branch(es) driven above rating",
                   fontsize=13)
    axes.axis("off")

    return save_figure(figure, path)
