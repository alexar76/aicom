"""Render the Glama article figures from the saved HISTOR calculations.

Run with Matplotlib: python3 render.py OUTPUT_DIR
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle
from matplotlib.ticker import FixedLocator, NullLocator


ARTIFACTS = Path(__file__).resolve().parent.parent
FIGURES = ARTIFACTS / "glama-figures-2026-11-02"
WEEKLY = ARTIFACTS / "cache-churn-2026-11-01"
SNAPSHOT = "HISTOR · 2 Nov 2026 snapshot · DOI 10.5281/zenodo.23884408"
INK = "#152936"
MUTED = "#4E6471"
TEAL = "#006E69"
BLUE = "#315879"
ORANGE = "#F6C984"
LIGHT_BLUE = "#DCE9F2"
GREY = "#E8EDF0"
GRID = "#CDD7DE"
WHITE = "#FFFFFF"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": INK,
    "svg.fonttype": "path",
    "svg.hashsalt": "histor-glama-2026-11-02",
    "savefig.facecolor": WHITE,
})


def read_json(path):
    return json.loads(path.read_text())


def number(value):
    return f"{value:,}"


def percent(value, total):
    return f"{value / total:.1%}"


def label(ax, x, y, message, *, size=13, colour=INK, weight="normal", align="left"):
    ax.text(x, y, message, fontsize=size, color=colour, fontweight=weight,
            ha=align, va="center")


def canvas(tag, title, subtitle, height=5.45):
    fig = plt.figure(figsize=(11.4, height), facecolor=WHITE)
    ax = fig.add_axes([0.055, 0.055, 0.89, 0.89])
    ax.set(xlim=(0, 100), ylim=(0, 100))
    ax.axis("off")
    label(ax, 0, 98, tag, size=10, colour=TEAL, weight="bold")
    label(ax, 0, 87, title, size=25, weight="bold")
    label(ax, 0, 77.5, subtitle, size=12, colour=MUTED)
    return fig, ax


def footer(ax, text=SNAPSHOT):
    ax.plot([0, 100], [5.5, 5.5], color=GRID, linewidth=0.8)
    label(ax, 0, 1, text, size=9, colour=MUTED)


def box(ax, x, y, width, height, title, detail, *, colour=GREY):
    ax.add_patch(Rectangle((x, y), width, height, facecolor=colour, linewidth=0))
    label(ax, x + width / 2, y + height * 0.65, title, size=19, weight="bold", align="center")
    label(ax, x + width / 2, y + height * 0.25, detail, size=10.5, colour=MUTED, align="center")


def arrow(ax, start, end, y):
    ax.add_patch(FancyArrowPatch((start, y), (end, y), color=MUTED, linewidth=1.4,
                                 arrowstyle="-|>", mutation_scale=14))


def stacked_bar(ax, y, height, segments, *, show_count=False):
    total = sum(count for count, _, _ in segments)
    left = 0
    centres = []
    for count, colour, text_colour in segments:
        width = count / total * 100
        centre = left + width / 2
        ax.add_patch(Rectangle((left, y), width, height, facecolor=colour, linewidth=0))
        value = percent(count, total)
        if show_count:
            value = f"{number(count)}  ·  {value}"
        label(ax, centre, y + height / 2, value, size=13, colour=text_colour,
              weight="bold", align="center")
        centres.append(centre)
        left += width
    return centres


def key(ax, x, y, colour, text):
    ax.add_patch(Rectangle((x, y - 1.1), 1.8, 2.2, facecolor=colour, linewidth=0))
    label(ax, x + 2.7, y, text, size=10.5, colour=MUTED)


def save(fig, out, stem):
    fig.savefig(out / f"{stem}.png", dpi=220)
    fig.savefig(out / f"{stem}.svg", metadata={"Date": None})
    plt.close(fig)


def counting_figure(stats, host_stats, out):
    total = stats["all"]["changes"]
    kept = stats["without_two_operators"]["changes"]
    host_count, hosts_changed = host_stats["hosts"]
    entries = next(row[1] for row in stats["top_hosts_by_changes"] if row[1] == 1916)
    fig, ax = canvas(
        "01  /  COUNTING CHANGES", "One edit can appear in many records",
        "Illustration of a catalogue counter shared across a publisher’s entries",
        height=5.8,
    )
    box(ax, 0, 51, 26, 19, "500 → 501", "Catalogue counter", colour=ORANGE)
    box(ax, 37, 51, 26, 19, number(entries), "Entries share the description", colour=LIGHT_BLUE)
    box(ax, 74, 51, 26, 19, f"Up to {number(entries)}", "Recorded changes", colour=GREY)
    arrow(ax, 27, 36, 60.5)
    arrow(ax, 64, 73, 60.5)
    label(ax, 0, 43, f"All {number(total)} recorded changes", size=14, weight="bold")
    centres = stacked_bar(ax, 25.5, 12, [(total - kept, ORANGE, INK), (kept, TEAL, WHITE)], show_count=True)
    label(ax, centres[0], 20, "Changes from two excluded publishers", size=10.5, colour=MUTED, align="center")
    label(ax, centres[1], 20, "Events retained for analysing edits", size=10.5, colour=MUTED, align="center")
    label(ax, 0, 11.5, f"With all publishers included, {number(hosts_changed)} of {number(host_count)} hosts "
          f"had a tool-list change ({percent(hosts_changed, host_count)}).", size=11.5)
    footer(ax)
    save(fig, out, "01-counting-changes")


def pin_figure(stats, out):
    events = stats["changes"]
    full = stats["full"]
    description = stats["tool_description_touched"][0]
    only = stats["descriptions_only_tool"][0]
    missed = stats["schema_pin_misses"][0]
    fig, ax = canvas(
        "02  /  TOOL DEFINITIONS", "What a pin on names and input schemas misses",
        "Both comparisons exclude the two publishers analysed separately.",
        height=6.2,
    )
    label(ax, 0, 67, f"{percent(description, events)} touched a tool description  ·  "
          f"{number(events)} recorded changes", size=14, weight="bold")
    stacked_bar(ax, 50.5, 11, [
        (only, TEAL, WHITE), (description - only, LIGHT_BLUE, INK),
        (full - description, BLUE, WHITE), (events - full, GREY, INK),
    ])
    key(ax, 0, 44, TEAL, f"{number(only)}  Description only")
    key(ax, 0, 38, LIGHT_BLUE, f"{number(description - only)}  Description and other changes")
    key(ax, 52, 44, BLUE, f"{number(full - description)}  Full comparison, no description edit")
    key(ax, 52, 38, GREY, f"{number(events - full)}  Names-only comparison")
    label(ax, 0, 28.7, f"Results for the pin  ·  {number(full)} full comparisons", size=14, weight="bold")
    centres = stacked_bar(ax, 12.5, 10.8, [(full - missed, BLUE, WHITE), (missed, ORANGE, INK)], show_count=True)
    label(ax, centres[0], 8.2, "Detected", size=10.5, colour=MUTED, align="center")
    label(ax, centres[1], 8.2, "Missed", size=10.5, colour=MUTED, align="center")
    footer(ax)
    save(fig, out, "02-what-the-pin-misses")


def token_figure(stats, out):
    fig, ax = canvas(
        "03  /  TOKEN BUDGET", "Tool-list size at the median and p99",
        "Current non-empty lists after excluding two publishers",
        height=5.85,
    )
    plot = fig.add_axes([0.218, 0.365, 0.718, 0.295])
    plot.set(xscale="log", xlim=(850, 70000), ylim=(-0.36, 1.53))
    plot.xaxis.set_major_locator(FixedLocator([1000, 2000, 5000, 10000, 20000, 50000]))
    plot.set_xticklabels(["1k", "2k", "5k", "10k", "20k", "50k"], color=MUTED, fontsize=10)
    plot.xaxis.set_minor_locator(NullLocator())
    plot.set_yticks([1, 0], ["Remote entries", "Packages"], fontsize=12)
    plot.tick_params(axis="y", length=0, pad=13)
    plot.tick_params(axis="x", length=0, pad=8)
    plot.grid(axis="x", color=GRID, linewidth=0.75)
    plot.set_axisbelow(True)
    for spine in plot.spines.values():
        spine.set_visible(False)
    for y, kind in [(1, "current_remote"), (0, "current_package")]:
        median, p99 = stats[kind]["p50"], stats[kind]["p99"]
        plot.hlines(y, median, p99, color=GRID, linewidth=2.1)
        plot.scatter(median, y, s=100, color=TEAL, zorder=3)
        plot.scatter(p99, y, s=105, color=BLUE, marker="D", zorder=3)
        for value in [median, p99]:
            plot.annotate(number(value), (value, y), xytext=(0, 12), textcoords="offset points",
                          ha="center", fontsize=12, fontweight="bold", color=INK)
    handles = [
        Line2D([], [], color=TEAL, marker="o", linestyle="None", markersize=8, label="Median"),
        Line2D([], [], color=BLUE, marker="D", linestyle="None", markersize=7, label="99th percentile (p99)"),
    ]
    plot.legend(handles=handles, loc="upper right", bbox_to_anchor=(1.005, 1.28),
                frameon=False, ncols=2, fontsize=11)
    label(ax, 58, 26.3, "Tokens per tool list · logarithmic scale", size=10.5, colour=MUTED, align="center")
    change = stats["changes"]
    label(ax, 0, 16.5, f"More tokens in {change['grew'] / change['counted']:.0%} of full comparisons", size=13, weight="bold")
    label(ax, 52, 16.5, f"{number(stats['servers_net']['doubled'])} lists at least doubled in size", size=13, weight="bold")
    label(ax, 0, 10.1, "o200k_base applied to the compact JSON array of names, descriptions and input schemas.",
          size=10.3, colour=MUTED)
    footer(ax)
    save(fig, out, "03-tool-list-token-size")


def timestamp_figure(stats, examples, out):
    kind = "only dates or timestamps"
    total = stats["kinds"][kind]
    top = max(row["changes"].get("dates", 0) for row in examples["byServer"])
    others = stats["serversByKind"][kind] - 1
    fig, ax = canvas(
        "04  /  REPEATED EDITS", "One entry drove most timestamp edits",
        f"{number(total)} date or timestamp edits with no other change  ·  25 Oct to 1 Nov 2026 (UTC)",
    )
    centres = stacked_bar(ax, 54, 14, [(top, TEAL, WHITE), (total - top, LIGHT_BLUE, INK)], show_count=True)
    label(ax, centres[0], 48.5, "One entry", size=12, colour=MUTED, align="center")
    label(ax, centres[1], 48.5, f"Other {others} entries", size=12, colour=MUTED, align="center")
    label(ax, 0, 36, "A tool description can include the time a feed was last read", size=13, weight="bold")
    box(ax, 0, 12, 43, 17.8, "12:00 UTC", "Timestamp in previous description", colour=GREY)
    box(ax, 57, 12, 43, 17.8, "12:05 UTC", "Timestamp in next description", colour=GREY)
    arrow(ax, 45, 55, 20.9)
    footer(ax, "HISTOR weekly dataset · histor.modelmarket.dev/datasets/cache-churn-2026-11-01/")
    save(fig, out, "04-timestamp-edits")


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    stats = read_json(FIGURES / "figures-1102.json")
    counting_figure(stats, read_json(FIGURES / "cohort-by-host-1102.json"), out)
    pin_figure(stats["without_two_operators"], out)
    token_figure(read_json(FIGURES / "token-figures-1102.json"), out)
    timestamp_figure(read_json(WEEKLY / "result.json"), read_json(WEEKLY / "examples.json"), out)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
