import math
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import seaborn as sns
from loguru import logger
from matplotlib import font_manager

from . import pathes

logger.info(f"Загружен модуль {__name__}!")


font_properties = font_manager.FontEntry(fname=pathes.font, name="minecraft")
font_manager.fontManager.ttflist.append(font_properties)


def getsigint(num_points: int) -> int:
    if num_points < 2:
        return 1
    return max(
        1,
        num_points // max(2, int(math.log10(num_points / 5) * 20 + 2)),
    )


def create_plot(data_dict, output_file=pathes.chart) -> None:
    """Линейный график сообщений по датам."""
    dates = [datetime.strptime(date, "%Y.%m.%d") for date in data_dict]
    values = list(data_dict.values())

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = font_properties.name
    prop = font_manager.FontProperties(fname=pathes.font)
    title_font = {
        "fontproperties": prop,
        "fontsize": 16,
        "fontweight": "bold",
        "color": "white",
    }
    label_font = {"fontproperties": prop, "fontsize": 11, "color": "white"}
    tick_font = {"fontproperties": prop, "fontsize": 10, "color": "lightgray"}

    plt.style.use("dark_background")
    sns.set_style(
        "darkgrid",
        {
            "axes.facecolor": "#1e1e1e",
            "figure.facecolor": "#1e1e1e",
            "grid.color": "#3d3d3d",
            "text.color": "white",
        },
    )
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#1e1e1e")

    sns.lineplot(
        x=dates,
        y=values,
        marker="o",
        color="#ff8222",
        linewidth=3,
        markersize=0,
        markerfacecolor="white",
        ax=ax,
    )

    ax.set_title("Статистика", **title_font)
    ax.set_xlabel("Дата", **tick_font)
    ax.set_ylabel("Сообщений", **label_font)

    ax.tick_params(colors="lightgray")
    for spine in ax.spines.values():
        spine.set_color("#3d3d3d")
    for label in (*ax.get_xticklabels(), *ax.get_yticklabels()):
        label.set_fontproperties(prop)
        label.set_color("lightgray")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m.%d"))
    plt.xticks(rotation=90)
    ax.grid(visible=True, linestyle="--", alpha=0.5, color="#3d3d3d")

    step = getsigint(len(dates))
    for n, (date, value) in enumerate(zip(dates, values, strict=False)):
        if n % step == 0:
            ax.text(
                date,
                value + 5,
                str(value),
                ha="center",
                va="bottom",
                fontsize=9,
                color="white",
                bbox={
                    "facecolor": "#333333",
                    "alpha": 0.7,
                    "edgecolor": "none",
                    "boxstyle": "round,pad=0.2",
                },
            )
    ax.set_facecolor("#1e1e1e")
    plt.tight_layout()

    plt.savefig(
        output_file,
        dpi=300,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
        bbox_inches="tight",
    )
    plt.close()
    logger.info("График сохранён")
