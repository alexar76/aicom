"""Conventional, editable article charts from existing HISTOR calculations.

Usage: python3 render.py OUTPUT_DIRECTORY [--lang ru|en]
Implementation and validation evidence remain in aicom; publication exports
belong in the article's PromoMaterials pack.
"""

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/histor-simple-charts-matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter
from PIL import Image, ImageOps, ImageDraw


HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parent
FIGURES = ARTIFACTS / "glama-figures-2026-11-02"
WEEKLY = ARTIFACTS / "cache-churn-2026-11-01"
BLUE = "#3C6D9D"
GREY = "#B7C0C8"
INK = "#222222"
MUTED = "#555555"
GRID = "#E5E5E5"
SOURCE = "Источник: HISTOR, срез 02.11.2026 · DOI: 10.5281/zenodo.23884408"
LANGUAGE = "ru"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 13,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": INK,
    "svg.fonttype": "none",  # Preserve editable text, rather than glyph paths.
    "svg.hashsalt": "histor-simple-charts-2026-11-07",
    "savefig.facecolor": "white",
})


def read(path):
    return json.loads(path.read_text())


def tr(russian, english):
    return english if LANGUAGE == "en" else russian


def number(value):
    return f"{value:,}" if LANGUAGE == "en" else f"{value:,}".replace(",", " ")


def percent(value, total):
    value = f"{100 * value / total:.1f}"
    return (value if LANGUAGE == "en" else value.replace(".", ",")) + "%"


def canvas(title, subtitle, *, left=0.27, bottom=0.32):
    fig = plt.figure(figsize=(10, 6), dpi=160, facecolor="white")
    fig.text(0.055, 0.92, title, fontsize=18, fontweight="bold", va="top")
    fig.text(0.055, 0.85, subtitle, fontsize=11.3, color=MUTED, va="top")
    ax = fig.add_axes([left, bottom, 0.94 - left, 0.73 - bottom])
    ax.set_axisbelow(True)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#AAAAAA")
    ax.tick_params(axis="both", length=0, pad=9)
    return fig, ax


def notes(fig, lines, source=None):
    if source is None:
        source = tr(SOURCE, "Source: HISTOR · 2 Nov 2026 snapshot · DOI: 10.5281/zenodo.23884408")
    for i, line in enumerate(lines):
        fig.text(0.055, 0.155 - i * 0.036, line, fontsize=9.6, color=MUTED)
    fig.text(0.055, 0.048, source, fontsize=8.6, color=MUTED)


def percent_axis(ax):
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_locator(FixedLocator([0, 20, 40, 60, 80, 100]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.grid(axis="x", color=GRID, linewidth=0.7)


def save(fig, output, stem, caption):
    fig.savefig(output / f"{stem}.png", dpi=160)
    fig.savefig(output / f"{stem}.svg", metadata={"Date": None, "Description": caption})
    # Check actual rendered text boundaries, rather than relying on tight cropping.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, height = fig.canvas.get_width_height()
    for text in fig.findobj(match=matplotlib.text.Text):
        if not text.get_visible() or not text.get_text():
            continue
        box = text.get_window_extent(renderer)
        if box.x0 < -1 or box.y0 < -1 or box.x1 > width + 1 or box.y1 > height + 1:
            raise ValueError(f"Clipped text in {stem}: {text.get_text()!r}, {box.bounds}")
    plt.close(fig)


def cohort_chart(output):
    data = read(FIGURES / "cohort-by-host-1102.json")
    rows = [
        (tr("Записи реестра", "Registry entries"), *data["entries"]),
        (tr("Хосты", "Hosts"), *data["hosts"]),
        (tr("Хосты с одной\nзаписью", "Single-entry\nhosts"), *data["single_entry_hosts"]),
    ]
    fig, ax = canvas(tr("Сколько записей и хостов изменилось за 39 дней", "Entries and hosts with a changed tool list"), tr("24 сентября — 2 ноября 2026 · каждый хост учитывается один раз", "24 September–2 November 2026 · each host counted once"))
    ax.set_ylim(-0.6, 2.6)
    for y, (label, total, changed) in zip([2, 1, 0], rows):
        value = changed / total * 100
        ax.barh(y, value, height=0.48, color=BLUE)
        ax.text(value + 1.5, y, percent(changed, total), va="center", fontsize=14, fontweight="bold")
    ax.set_yticks([2, 1, 0], [f"{label}\n{number(changed)} {tr('из', 'of')} {number(total)}" for label, total, changed in rows], fontsize=12)
    percent_axis(ax)
    ax.set_xlabel(tr("Доля записей или хостов с изменениями", "Share with at least one tool-list change"), fontsize=11.3, labelpad=12)
    notes(fig, [tr("Все издатели включены. У группы был сохранён список к концу 24 сентября;", "Entries had a saved list by the end of 24 September and were still listed on 2 November."), tr("записи оставались в реестре на дату среза.", "All publishers included. A host counts as changed if any eligible entry changed.")])
    save(fig, output, "01-changed-hosts", tr("Доли изменившихся записей и хостов в исходной группе: 50,0%, 41,3%, 41,0%.", "Shares with changes in the baseline cohort: registry entries 50.0%, hosts 41.3%, single-entry hosts 41.0%."))
    return rows


def pin_chart(output):
    data = read(FIGURES / "figures-1102.json")["without_two_operators"]
    total = data["full"]
    rows = [(tr("Только имена", "Names only"), data["name_pin_misses"][0]), (tr("Имена и входные\nсхемы", "Names and\ninput schemas"), data["schema_pin_misses"][0])]
    fig, ax = canvas(tr("Какие правки пропускает проверка определений", "Changes missed by partial tool-definition pins"), tr(f"{number(total)} изменений с полными данными · два крупных издателя исключены", f"{number(total)} changes with complete data · two large publishers excluded"))
    ax.set_ylim(-0.55, 1.55)
    for y, (label, missed) in zip([1, 0], rows):
        value = missed / total * 100
        ax.barh(y, value, height=0.43, color=BLUE)
        ax.text(value + 1.5, y, percent(missed, total), va="center", fontsize=14, fontweight="bold")
    ax.set_yticks([1, 0], [f"{label}\n{number(missed)} {tr('пропущено', 'missed')}" for label, missed in rows], fontsize=12)
    percent_axis(ax)
    ax.set_xlabel(tr("Доля пропущенных изменений", "Share of changes missed"), fontsize=11.3, labelpad=12)
    notes(fig, [tr("Проверка имён и входных схем пропускает правки описаний и выходных схем,", "A pin on names and input schemas misses description and output-schema edits"), tr("если имена инструментов и входные схемы остались прежними.", "when tool names and input schemas remain unchanged.")])
    save(fig, output, "02-pin-misses", tr("Проверка только имён пропускает 23 218 из 34 066 изменений; имён и входных схем — 10 293 из 34 066.", "A names-only pin misses 23,218 of 34,066 changes; a names-and-input-schemas pin misses 10,293 of 34,066."))
    return {"total": total, "rows": rows}


def token_chart(output):
    data = read(FIGURES / "token-figures-1102.json")
    remote, package = data["current_remote"], data["current_package"]
    fig, ax = canvas(tr("Размер списка инструментов в токенах", "Tool-list size in tokens"), tr("Текущие непустые списки · два крупных издателя исключены", "Current non-empty lists · two large publishers excluded"), left=0.12, bottom=0.28)
    positions = [0, 1]
    width = 0.26
    for offset, key, label, color in [(-width / 2, "p50", tr("Медиана", "Median"), GREY), (width / 2, "p99", tr("99-й процентиль (p99)", "99th percentile (p99)"), BLUE)]:
        values = [remote[key], package[key]]
        bars = ax.bar([x + offset for x in positions], values, width=width, color=color, label=label)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 1100, number(value), ha="center", fontsize=12.5, fontweight="bold")
    ax.set_xticks(positions, [f"{tr('Удалённые записи', 'Remote entries')}\nn = {number(remote['servers'])}", f"{tr('Пакеты npm / PyPI', 'npm / PyPI packages')}\nn = {number(package['servers'])}"], fontsize=11.5)
    ax.set_ylim(0, 50000)
    ax.set_xlim(-0.55, 1.55)
    ax.yaxis.set_major_locator(FixedLocator([0, 10000, 20000, 30000, 40000, 50000]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number(int(value))))
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.set_ylabel(tr("Токенов на список", "Tokens per tool list"), fontsize=11.3, labelpad=10)
    ax.legend(loc="upper left", frameon=False, fontsize=10.5)
    notes(fig, [tr("o200k_base; компактный JSON: name, description, inputSchema; без outputSchema.", "o200k_base; compact JSON: name, description, inputSchema; outputSchema excluded."), tr("p99 — порог, ниже которого находятся примерно 99% списков.", "p99 is the threshold below which approximately 99% of lists fall.")])
    save(fig, output, "03-token-size", tr("Удалённые: медиана 1 229, p99 34 302 токена. Пакеты: медиана 1 210, p99 40 330 токенов.", "Remote entries: median 1,229, p99 34,302 tokens. Packages: median 1,210, p99 40,330 tokens."))
    return {"remote": remote, "package": package}


def timestamp_chart(output):
    data = read(WEEKLY / "result.json")
    examples = read(WEEKLY / "examples.json")
    kind = "only dates or timestamps"
    total = data["kinds"][kind]
    top = max(row["changes"].get("dates", 0) for row in examples["byServer"])
    other_entries = data["serversByKind"][kind] - 1
    fig, ax = canvas(tr("На одну запись пришлось 72% правок дат и времени", "One entry accounted for 72% of date and time edits"), tr(f"{number(total)} изменение только дат или отметок времени · 25 октября — 1 ноября 2026", f"{number(total)} changes affecting only dates or timestamps · 25 October–1 November 2026"), left=0.28)
    rows = [(tr("Одна запись", "One entry"), top), (tr(f"Остальные {other_entries}\nзаписей", f"Other {other_entries}\nentries"), total - top)]
    ax.set_ylim(-0.55, 1.55)
    for y, (label, count) in zip([1, 0], rows):
        ax.barh(y, count, height=0.43, color=BLUE)
        ax.text(count + 5, y, number(count), fontsize=14, fontweight="bold", va="center")
    ax.set_yticks([1, 0], [row[0] for row in rows], fontsize=12)
    ax.set_xlim(0, 300)
    ax.xaxis.set_major_locator(FixedLocator([0, 50, 100, 150, 200, 250, 300]))
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.set_xlabel(tr("Число изменений", "Number of changes"), fontsize=11.3, labelpad=12)
    notes(fig, [tr("Отдельный недельный набор, 27 записей. Учитываются только правки дат и времени.", "Separate weekly dataset: 27 entries with date- or timestamp-only changes.")], source=tr("Источник: HISTOR · histor.modelmarket.dev/datasets/cache-churn-2026-11-01/", "Source: HISTOR · histor.modelmarket.dev/datasets/cache-churn-2026-11-01/"))
    save(fig, output, "04-timestamp-edits", tr("Из 331 изменения только дат или времени 237 пришлись на одну запись, 94 — на остальные 26.", "Of 331 date- or timestamp-only changes, 237 came from one entry and 94 from the other 26 entries."))
    return {"total": total, "top_entry": top, "other_entries": other_entries, "others": total - top}


def contact_sheet(output):
    paths = sorted(output.glob("*.png"))
    sheet = Image.new("RGB", (1600, 1020), "#dddddd")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        tile = ImageOps.contain(Image.open(path).convert("RGB"), (790, 474))
        x, y = (index % 2) * 800 + 5, (index // 2) * 510 + 28
        sheet.paste(tile, (x, y))
        draw.text((x + 5, y - 19), path.stem, fill="#222222")
    sheet.save(HERE / tr("contact-sheet.png", "contact-sheet-en.png"))


def main():
    global LANGUAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--lang", choices=["ru", "en"], default="ru")
    args = parser.parse_args()
    LANGUAGE = args.lang
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {
        "cohort": cohort_chart(output),
        "pin": pin_chart(output),
        "tokens": token_chart(output),
        "timestamps": timestamp_chart(output),
        "source_files": [str(FIGURES / file) for file in ["cohort-by-host-1102.json", "figures-1102.json", "token-figures-1102.json"]] + [str(WEEKLY / file) for file in ["result.json", "examples.json"]],
    }
    (HERE / tr("source-values.json", "source-values-en.json")).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    contact_sheet(output)
    print(f"Rendered {len(list(output.glob('*.png')))} PNG charts and matching editable SVGs to {output}")


if __name__ == "__main__":
    main()
