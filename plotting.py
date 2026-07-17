"""Matplotlib polar plots for antenna-pattern cuts and comparisons."""

import math


def plot_patterns(
    antenna,
    comparison=None,
    output_path=None,
    show=False,
    floor_db=None,
    primary_label="PLANET",
    comparison_label="NSMA",
):
    """Create separate polar panels for each antenna-pattern cut.

    PLANET data is drawn as a solid trace. When ``comparison`` is supplied,
    matching NSMA cuts are overlaid with dashed traces and sparse markers.
    ``floor_db`` controls clipping and the innermost displayed gain level. If
    omitted, the floor is selected from the deepest pattern value and rounded
    down to a 10 dB boundary. The figure may be saved, displayed, or both.
    """

    if floor_db is None:
        patterns = [antenna]
        if comparison is not None:
            patterns.append(comparison)
        minimum_level = min(
            level
            for pattern in patterns
            for cut in pattern.cuts
            for _, level in cut.points
        )
        floor_db = min(-10.0, math.floor(minimum_level / 10.0) * 10.0)

    if floor_db >= 0:
        raise ValueError("Plot floor must be below 0 dB")

    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Polar plotting requires Matplotlib; install it with "
            "'python -m pip install matplotlib'."
        ) from exc

    cut_count = len(antenna.cuts)
    figure, plot_axes = plt.subplots(
        1,
        cut_count,
        figsize=(7 * cut_count, 7),
        subplot_kw={"projection": "polar"},
        squeeze=False,
    )
    plot_axes = plot_axes[0]
    comparison_cuts = (
        {cut.axis: cut for cut in comparison.cuts} if comparison is not None else {}
    )
    comparison_colors = ["tab:cyan", "tab:red", "tab:purple", "tab:green"]

    for index, (axes, cut) in enumerate(zip(plot_axes, antenna.cuts)):
        angles = [math.radians(angle) for angle, _ in cut.points]
        levels = [max(value, floor_db) - floor_db for _, value in cut.points]
        axes.plot(angles, levels, linewidth=1.5, label=primary_label)

        comparison_cut = comparison_cuts.get(cut.axis)
        if comparison_cut is not None:
            comparison_angles = [
                math.radians(angle) for angle, _ in comparison_cut.points
            ]
            comparison_levels = [
                max(value, floor_db) - floor_db for _, value in comparison_cut.points
            ]
            axes.plot(
                comparison_angles,
                comparison_levels,
                linewidth=1.8,
                linestyle="--",
                color=comparison_colors[index % len(comparison_colors)],
                marker="o",
                markevery=max(1, len(comparison_cut.points) // 24),
                markersize=3.5,
                markerfacecolor="white",
                markeredgewidth=1.0,
                zorder=3,
                label=comparison_label,
            )

        angle_ticks = list(range(0, 360, 10))
        axes.set_xticks([math.radians(angle) for angle in angle_ticks])
        axes.set_xticklabels(
            [f"{angle}°" if angle % 30 == 0 else "" for angle in angle_ticks]
        )

        radial_range = -floor_db
        radial_ticks = list(range(0, int(radial_range) + 1, 5))
        axes.set_rticks(radial_ticks)
        axes.set_yticklabels(
            [
                f"{level:g}\ndB" if abs(level % 10) < 1e-9 else ""
                for level in (tick + floor_db for tick in radial_ticks)
            ]
        )
        for radial_label in axes.get_yticklabels():
            radial_label.set_horizontalalignment("center")
            radial_label.set_verticalalignment("center")
        axes.set_ylim(0, radial_range)
        axes.set_theta_zero_location("N")
        axes.set_theta_direction(-1)
        axes.set_rlabel_position(90)
        plane_name = "H" if cut.axis in {"H", "AZ"} else "E"
        axes.set_title(f"{plane_name} plane", pad=18)
        axes.legend(loc="upper right", bbox_to_anchor=(1.15, 1.12))
        axes.grid(True, alpha=0.6)

    figure.suptitle(
        f"{antenna.fields.get('NAME', 'Antenna')} radiation patterns", fontsize=16
    )
    figure.tight_layout()

    if output_path is not None:
        figure.savefig(output_path, dpi=160, bbox_inches="tight")
    if show:
        plt.show()

    plt.close(figure)
