"""
orion.visualization

Module for generating interactive HTML visualizations of Orion test results
using plotly. Generates self-contained HTML files with embedded JS.
"""

import re
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from orion.logger import SingletonLogger


class VizData:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Container for all data needed to visualize one test's results."""

    def __init__(
        self,
        test_name: str,
        dataframe: pd.DataFrame,
        metrics_config: dict,
        change_points_by_metric: dict,
        uuid_field: str,
        version_field: str,
        acked_entries: list = None,
        algorithm_name: str = "",
        build_tag_field: str = "buildTag",
    ):
        self.test_name = test_name
        self.dataframe = dataframe
        self.metrics_config = metrics_config
        self.change_points_by_metric = change_points_by_metric
        self.uuid_field = uuid_field
        self.version_field = version_field
        self.algorithm_name = algorithm_name
        self.acked_entries = acked_entries or []
        self.build_tag_field = build_tag_field


def _prepare_timestamps(df: pd.DataFrame):
    """Convert dataframe timestamps to pandas datetime for plotly display."""
    if pd.api.types.is_numeric_dtype(df["timestamp"]):
        return pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return pd.to_datetime(df["timestamp"])


def _short_version(v):
    """Extract short nightly label, e.g. 'nightly-02-03' from
    '4.22.0-0.nightly-2026-02-03-002928'."""
    v = str(v)
    m = re.search(r"nightly-\d{4}-(\d{2}-\d{2})", v)
    if m:
        return f"nightly-{m.group(1)}"
    return v[:20]


def _build_tag(viz_data: VizData, df: pd.DataFrame, idx: int) -> str:
    """Return the build tag for row idx, or 'N/A' if missing."""
    if viz_data.build_tag_field in df.columns:
        val = df[viz_data.build_tag_field].iloc[idx]
        if pd.notna(val) and str(val) != "":
            return str(val)
    return "N/A"


@dataclass
class ClassifiedChangepoint:
    """A changepoint with pre-computed classification (color, regression status)."""
    cp: object
    index: int
    pct_change: float
    is_regression: bool
    color: str


def _classify_changepoint(cp_stats, direction):
    """Return (pct_change, is_regression) for a single changepoint."""
    if cp_stats.mean_1 == 0:
        pct_change = 0.0
    else:
        pct_change = (
            (cp_stats.mean_2 - cp_stats.mean_1) / cp_stats.mean_1
        ) * 100
    is_regression = (pct_change * direction > 0) or direction == 0
    return pct_change, is_regression


def _classify_changepoints(change_points_by_metric, metrics_config):
    """Pre-compute classification for all changepoints across all metrics.

    Returns dict[str, list[ClassifiedChangepoint]].
    """
    result = {}
    for metric_name, cps in change_points_by_metric.items():
        direction = metrics_config.get(metric_name, {}).get("direction", 1)
        classified = []
        for cp in cps:
            pct_change, is_regression = _classify_changepoint(
                cp.stats, direction
            )
            color = "#ff4444" if is_regression else "#39ff14"
            classified.append(ClassifiedChangepoint(
                cp=cp, index=cp.index,
                pct_change=pct_change, is_regression=is_regression,
                color=color,
            ))
        result[metric_name] = classified
    return result


def _metric_has_data(df, metric_name):
    """Check if a metric column exists in the dataframe and has non-NaN values."""
    return metric_name in df.columns and df[metric_name].notna().any()


def _add_no_data_placeholder(fig, metric_name, row_idx):
    """Add a 'No data available' annotation to an empty subplot."""
    fig.add_trace(
        go.Scatter(
            x=[None], y=[None],
            mode="markers",
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row_idx, col=1,
    )
    fig.add_annotation(
        text="No data available",
        x=0.5, y=0.5,
        xref=f"x{row_idx} domain" if row_idx > 1 else "x domain",
        yref=f"y{row_idx} domain" if row_idx > 1 else "y domain",
        showarrow=False,
        font={"color": "rgba(255,255,255,0.4)", "size": 16},
    )
    fig.update_yaxes(
        title_text=metric_name,
        title_font={"size": 11},
        gridcolor="rgba(255,255,255,0.08)",
        row=row_idx, col=1,
    )
    fig.update_xaxes(
        showticklabels=False,
        row=row_idx, col=1,
    )


def _build_test_figure(viz_data: VizData) -> go.Figure:
    """Build a plotly Figure for a single test with one subplot per metric."""
    df = viz_data.dataframe
    metrics = list(viz_data.metrics_config.keys())
    classified_by_metric = _classify_changepoints(
        viz_data.change_points_by_metric, viz_data.metrics_config
    )

    def _sort_key(m):
        cps = classified_by_metric.get(m, [])
        if not cps:
            return (2, m)  # stable → bottom
        has_regression = any(c.is_regression for c in cps)
        return (0, m) if has_regression else (1, m)

    metrics = sorted(metrics, key=_sort_key)

    # Cap at 200 metrics (prioritize regressions first, which are already sorted to top)
    # This prevents massive slow visualizations with 1000+ metrics
    MAX_METRICS = 200
    if len(metrics) > MAX_METRICS:
        logger = SingletonLogger.get_logger("Orion")
        logger.warning(
            "Capping visualization to %d of %d metrics (prioritizing regressions). "
            "Use filters or reduce lookback period to visualize specific metrics.",
            MAX_METRICS, len(metrics)
        )
        metrics = metrics[:MAX_METRICS]

    n_metrics = len(metrics)

    if n_metrics == 0:
        fig = go.Figure()
        fig.update_layout(title_text=f"Orion: {viz_data.test_name} (no metrics)")
        return fig

    timestamps = _prepare_timestamps(df)
    versions = df.get(viz_data.version_field, pd.Series(["N/A"] * len(df)))
    uuids = df.get(viz_data.uuid_field, pd.Series(["N/A"] * len(df)))
    build_urls = df.get("buildUrl", pd.Series([""] * len(df)))
    build_tags = [_build_tag(viz_data, df, i) for i in range(len(df))]

    # Evenly spaced x-axis
    x_indices = list(range(len(df)))
    tick_labels = [
        f"{ts.strftime('%b %d')}<br>"
        f"<span style='font-size:8px'>{_short_version(v)}</span>"
        for ts, v in zip(timestamps, versions)
    ]

    fig = make_subplots(
        rows=n_metrics,
        cols=1,
        shared_xaxes=False,
        subplot_titles=metrics,
        vertical_spacing=60 / (400 * n_metrics + 100),  # ~60px gap
    )

    # Color palette for metric lines
    line_colors = [
        "#00d4ff", "#ff6ec7", "#39ff14", "#ffaa00",
        "#ff4444", "#aa88ff", "#00ffaa", "#ff8844",
    ]

    for row_idx, metric_name in enumerate(metrics, start=1):
        if not _metric_has_data(df, metric_name):
            _add_no_data_placeholder(fig, metric_name, row_idx)
            continue

        values = df[metric_name]
        line_color = line_colors[(row_idx - 1) % len(line_colors)]

        # Structured customdata for hover template and click handlers
        custom = [
            [
                build_urls.iloc[i] if i < len(build_urls) else "",
                str(uuids.iloc[i]),
                str(timestamps.iloc[i].strftime('%Y-%m-%d %H:%M UTC')),
                str(versions.iloc[i]),
                build_tags[i],
            ]
            for i in range(len(df))
        ]

        hover_tpl = (
            f"<b>{metric_name}: %{{y:,.2f}}</b><br>"
            "Date: %{customdata[2]}<br>"
            "Version: %{customdata[3]}<br>"
            "Build Tag: %{customdata[4]}<br>"
            "UUID: %{customdata[1]}<br>"
            "<i>click → build log  |  right-click → copy UUID</i>"
            "<extra></extra>"
        )

        # Main time-series trace
        fig.add_trace(
            go.Scatter(
                x=x_indices,
                y=values,
                mode="lines+markers",
                name=metric_name,
                hovertemplate=hover_tpl,
                customdata=custom,
                marker={"size": 6, "color": line_color},
                line={"width": 2, "color": line_color},
                connectgaps=False,
                showlegend=False,
            ),
            row=row_idx,
            col=1,
        )

        # Statistical reference lines and shaded bands
        mean_val = values.mean()
        std_val = values.std() if values.count() >= 2 else 0.0
        p99_val = values.quantile(0.99)

        if std_val > 0:
            # ±2σ shaded band (wider, subtler shade)
            fig.add_hrect(
                y0=mean_val - 2 * std_val,
                y1=mean_val + 2 * std_val,
                fillcolor="rgba(255, 68, 68, 0.07)",
                line_width=0,
                layer="below",
                row=row_idx, col=1,
            )
            # ±1σ shaded band (narrower, slightly more visible)
            fig.add_hrect(
                y0=mean_val - std_val,
                y1=mean_val + std_val,
                fillcolor="rgba(255, 170, 0, 0.10)",
                line_width=0,
                layer="below",
                row=row_idx, col=1,
            )

            # ±2σ boundary lines (red dotted)
            fig.add_hline(
                y=mean_val + 2 * std_val, row=row_idx, col=1,
                line_dash="dot", line_color="rgba(255,68,68,0.5)",
                line_width=1,
                annotation_text=f"+2σ ({mean_val + 2 * std_val:,.2f})",
                annotation_position="right",
                annotation_font_color="rgba(255,68,68,0.7)",
                annotation_font_size=8,
            )
            fig.add_hline(
                y=mean_val - 2 * std_val, row=row_idx, col=1,
                line_dash="dot", line_color="rgba(255,68,68,0.5)",
                line_width=1,
                annotation_text=f"-2σ ({mean_val - 2 * std_val:,.2f})",
                annotation_position="right",
                annotation_font_color="rgba(255,68,68,0.7)",
                annotation_font_size=8,
            )

            # ±1σ boundary lines (orange dash-dot)
            fig.add_hline(
                y=mean_val + std_val, row=row_idx, col=1,
                line_dash="dashdot", line_color="rgba(255,170,0,0.6)",
                line_width=1,
                annotation_text=f"+1σ ({mean_val + std_val:,.2f})",
                annotation_position="right",
                annotation_font_color="rgba(255,170,0,0.7)",
                annotation_font_size=8,
            )
            fig.add_hline(
                y=mean_val - std_val, row=row_idx, col=1,
                line_dash="dashdot", line_color="rgba(255,170,0,0.6)",
                line_width=1,
                annotation_text=f"-1σ ({mean_val - std_val:,.2f})",
                annotation_position="right",
                annotation_font_color="rgba(255,170,0,0.7)",
                annotation_font_size=8,
            )

        # Mean line (green dashed)
        fig.add_hline(
            y=mean_val, row=row_idx, col=1,
            line_dash="dash", line_color="rgba(57,255,20,0.6)",
            line_width=1.5,
            annotation_text=f"AVG ({mean_val:,.2f})",
            annotation_position="right",
            annotation_font_color="rgba(57,255,20,0.8)",
            annotation_font_size=9,
        )

        # P99 line (cyan long-dash)
        fig.add_hline(
            y=p99_val, row=row_idx, col=1,
            line_dash="longdash", line_color="rgba(0,212,255,0.5)",
            line_width=1,
            annotation_text=f"P99 ({p99_val:,.2f})",
            annotation_position="right",
            annotation_font_color="rgba(0,212,255,0.7)",
            annotation_font_size=8,
        )

        # Changepoint markers and annotations
        for cc in classified_by_metric.get(metric_name, []):
            if not 0 <= cc.index < len(df):
                continue
            cp_value = values.iloc[cc.index]
            cp_build_url = (
                build_urls.iloc[cc.index]
                if cc.index < len(build_urls) else ""
            )

            # Changepoint marker
            fig.add_trace(
                go.Scatter(
                    x=[cc.index],
                    y=[cp_value],
                    mode="markers",
                    marker={
                        "size": 14,
                        "color": cc.color,
                        "symbol": "diamond",
                        "line": {"width": 2, "color": "white"},
                    },
                    showlegend=False,
                    hovertemplate=(
                        f"<b>CHANGEPOINT</b><br>"
                        f"{cc.pct_change:+.1f}% change<br>"
                        f"Mean before: {cc.cp.stats.mean_1:,.2f}<br>"
                        f"Mean after: {cc.cp.stats.mean_2:,.2f}<br>"
                        f"Build Tag: {build_tags[cc.index]}<br>"
                        f"UUID: {uuids.iloc[cc.index]}<br>"
                        f"<i>click → build log  |  right-click → copy UUID</i>"
                        f"<extra></extra>"
                    ),
                    customdata=[
                        [cp_build_url, str(uuids.iloc[cc.index])]
                    ],
                ),
                row=row_idx,
                col=1,
            )

            # Vertical dashed line at changepoint
            fig.add_vline(
                x=cc.index,
                row=row_idx,
                col=1,
                line_dash="dash",
                line_color=cc.color,
                line_width=1.5,
            )

            # Percentage change annotation
            y_range = values.max() - values.min()
            fig.add_annotation(
                x=cc.index,
                y=values.max() + y_range * 0.08,
                text=f"<b>{cc.pct_change:+.1f}%</b>",
                showarrow=False,
                font={"color": cc.color, "size": 11},
                row=row_idx,
                col=1,
            )

        # ACK markers — green diamonds on acknowledged data points
        for ack in viz_data.acked_entries:
            if ack["metric"] != metric_name:
                continue
            matches = df.index[uuids == ack["uuid"]].tolist()
            if not matches:
                continue
            ack_idx = matches[0]
            ack_build_url = (
                build_urls.iloc[ack_idx] if ack_idx < len(build_urls) else ""
            )
            fig.add_trace(
                go.Scatter(
                    x=[ack_idx],
                    y=[values.iloc[ack_idx]],
                    mode="markers",
                    marker={
                        "size": 14, "color": "#39ff14",
                        "symbol": "diamond",
                        "line": {"width": 2, "color": "white"},
                    },
                    showlegend=False,
                    hovertemplate=(
                        f"<b>ACKed</b><br>"
                        f"Reason: {ack['reason']}<br>"
                        f"Build Tag: {build_tags[ack_idx]}<br>"
                        f"UUID: {ack['uuid'][:8]}<br>"
                        f"<i>click → build log  |  right-click → copy UUID</i>"
                        f"<extra></extra>"
                    ),
                    customdata=[[ack_build_url, ack['uuid']]],
                ),
                row=row_idx,
                col=1,
            )

        # Add consistent y-axis padding so all subplots look similar.
        # For nearly-flat metrics, ensure at least 5% of the mean as padding
        # so the data fills the subplot instead of being a thin line.
        y_min = min(values.min(), mean_val - 2 * std_val)
        y_max = max(values.max(), mean_val + 2 * std_val)
        y_span = y_max - y_min
        min_pad = abs(mean_val) * 0.05 or 1
        y_pad = max(y_span * 0.15, min_pad)
        fig.update_yaxes(
            title_text=metric_name,
            title_font={"size": 11},
            gridcolor="rgba(255,255,255,0.08)",
            range=[y_min - y_pad, y_max + y_pad],
            row=row_idx,
            col=1,
        )

    # Version change markers across all subplots (batched to avoid O(n²))
    version_change_indices = [
        i for i in range(1, len(versions))
        if versions.iloc[i] != versions.iloc[i - 1]
    ]
    if version_change_indices:
        version_shapes = []
        for i in version_change_indices:
            for row_idx in range(1, n_metrics + 1):
                xref = "x" if row_idx == 1 else f"x{row_idx}"
                yref = "y" if row_idx == 1 else f"y{row_idx}"
                version_shapes.append(
                    {
                        "type": "line",
                        "x0": i, "x1": i, "y0": 0, "y1": 1,
                        "xref": xref, "yref": f"{yref} domain",
                        "line": {
                            "dash": "dot",
                            "color": "rgba(255,170,0,0.4)",
                            "width": 1,
                        },
                    }
                )
        existing = list(fig.layout.shapes or [])
        fig.update_layout(shapes=existing + version_shapes)

    # Summary info for the title
    date_range = (
        f"{timestamps.iloc[0].strftime('%b %d')} - "
        f"{timestamps.iloc[-1].strftime('%b %d, %Y')}"
    )
    n_runs = len(df)
    total_cps = sum(
        len(v) for v in classified_by_metric.values()
    )

    # Build per-metric changepoint summary
    cp_parts = []
    for metric_name, ccs in classified_by_metric.items():
        for cc in ccs:
            cp_parts.append(
                f"<span style='color:{cc.color}'>"
                f"{metric_name}: {cc.pct_change:+.1f}%</span>"
            )

    cp_summary_line = ""
    if cp_parts:
        cp_summary_line = (
            f"<br><span style='font-size:11px'>"
            f"{' | '.join(cp_parts)}</span>"
        )

    cp_label = "changepoint" if total_cps == 1 else "changepoints"
    title = (
        f"<b>Orion: {viz_data.test_name}</b><br>"
        f"<span style='font-size:12px; color:#aaa'>"
        f"{date_range} | {n_runs} runs | "
        f"{total_cps} {cp_label}"
        f"</span>"
        f"{cp_summary_line}"
    )

    fig.update_layout(
        title_text=title,
        title_x=0.5,
        height=400 * n_metrics + 100,
        showlegend=False,
        template="plotly_dark",
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        hoverlabel={
            "bgcolor": "#1e1e3a",
            "bordercolor": "#666",
            "font_size": 12,
            "font_color": "#ffffff",
        },
        margin={"t": 160, "b": 40, "l": 80, "r": 120},
        autosize=True,
    )

    # Thin out x-axis ticks to avoid overcrowding
    max_ticks = 20
    n_points = len(x_indices)
    if n_points > max_ticks:
        step = n_points / max_ticks
        shown = [int(round(i * step)) for i in range(max_ticks)]
        shown = [i for i in shown if i < n_points]
        if (n_points - 1) not in shown:
            shown.append(n_points - 1)
        shown_tickvals = [x_indices[i] for i in shown]
        shown_ticktext = [tick_labels[i] for i in shown]
    else:
        shown_tickvals = x_indices
        shown_ticktext = tick_labels

    for row_idx in range(1, n_metrics + 1):
        fig.update_xaxes(
            tickvals=shown_tickvals,
            ticktext=shown_ticktext,
            tickangle=0,
            tickfont={"size": 9},
            gridcolor="rgba(255,255,255,0.08)",
            row=row_idx,
            col=1,
        )

    return fig


def _build_cmr_figure(viz_data: VizData) -> go.Figure:
    """Build a bar comparison figure for CMR (2-row baseline vs latest)."""
    df = viz_data.dataframe
    metrics = list(viz_data.metrics_config.keys())
    n_metrics = len(metrics)

    if n_metrics == 0 or len(df) < 2:
        fig = go.Figure()
        label = "no metrics" if n_metrics == 0 else "insufficient data"
        fig.update_layout(
            title_text=f"Orion: {viz_data.test_name} ({label})",
            template="plotly_dark",
            paper_bgcolor="#1a1a2e",
            plot_bgcolor="#16213e",
        )
        return fig

    versions = df.get(viz_data.version_field, pd.Series(["N/A"] * len(df)))
    build_tags = [_build_tag(viz_data, df, i) for i in range(len(df))]
    baseline_label = f"Baseline ({_short_version(versions.iloc[0])})"
    latest_label = f"Latest ({_short_version(versions.iloc[-1])})"

    fig = make_subplots(
        rows=n_metrics,
        cols=1,
        shared_xaxes=False,
        subplot_titles=metrics,
        vertical_spacing=80 / (300 * n_metrics + 100),
    )

    for row_idx, metric_name in enumerate(metrics, start=1):
        if (
            not _metric_has_data(df, metric_name)
            or pd.isna(df[metric_name].iloc[0])
            or pd.isna(df[metric_name].iloc[-1])
        ):
            _add_no_data_placeholder(fig, metric_name, row_idx)
            continue

        baseline_val = float(df[metric_name].iloc[0])
        latest_val = float(df[metric_name].iloc[-1])

        if baseline_val == 0:
            pct_change = None
        else:
            pct_change = ((latest_val - baseline_val) / baseline_val) * 100

        direction = viz_data.metrics_config.get(
            metric_name, {}
        ).get("direction", 1)
        if pct_change is not None:
            is_regression = (pct_change * direction > 0) or direction == 0
        else:
            is_regression = False

        latest_color = "#ff4444" if is_regression else "#39ff14"

        fig.add_trace(
            go.Bar(
                x=[baseline_label],
                y=[baseline_val],
                name="Baseline",
                marker_color="#00d4ff",
                showlegend=(row_idx == 1),
                text=[f"{baseline_val:,.2f}"],
                textposition="outside",
                textfont={"color": "#00d4ff", "size": 12},
                hovertemplate=(
                    f"<b>{metric_name}</b><br>"
                    f"Baseline: {baseline_val:,.2f}<br>"
                    f"Build Tag (baseline run): {build_tags[0]}"
                    "<extra></extra>"
                ),
            ),
            row=row_idx,
            col=1,
        )

        fig.add_trace(
            go.Bar(
                x=[latest_label],
                y=[latest_val],
                name="Latest",
                marker_color=latest_color,
                showlegend=(row_idx == 1),
                text=[f"{latest_val:,.2f}"],
                textposition="outside",
                textfont={"color": latest_color, "size": 12},
                hovertemplate=(
                    f"<b>{metric_name}</b><br>"
                    f"Latest: {latest_val:,.2f}<br>"
                    f"Build Tag (latest run): {build_tags[-1]}<br>"
                    f"Change: {pct_change:+.1f}%"
                    if pct_change is not None else
                    f"<b>{metric_name}</b><br>"
                    f"Latest: {latest_val:,.2f}<br>"
                    f"Build Tag (latest run): {build_tags[-1]}<br>"
                    "Change: N/A (zero baseline)"
                ) + "<extra></extra>",
            ),
            row=row_idx,
            col=1,
        )

        pct_color = "#ff4444" if is_regression else "#39ff14"
        pct_label = f"{pct_change:+.1f}%" if pct_change is not None else "N/A"
        y_top = max(baseline_val, latest_val)
        fig.add_annotation(
            x=latest_label,
            y=y_top,
            text=f"<b>{pct_label}</b>",
            showarrow=False,
            font={"color": pct_color, "size": 14},
            yshift=30,
            row=row_idx,
            col=1,
        )

        y_pad = max(abs(baseline_val), abs(latest_val)) * 0.25 or 1
        fig.update_yaxes(
            title_text=metric_name,
            title_font={"size": 11},
            gridcolor="rgba(255,255,255,0.08)",
            range=[0, max(baseline_val, latest_val) + y_pad],
            row=row_idx,
            col=1,
        )

    title = (
        f"<b>Orion CMR: {viz_data.test_name}</b><br>"
        f"<span style='font-size:12px; color:#aaa'>"
        f"Baseline vs Latest | {n_metrics} metrics</span>"
    )

    fig.update_layout(
        title_text=title,
        title_x=0.5,
        barmode="group",
        height=300 * n_metrics + 100,
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom",
                "y": 1.02, "xanchor": "center", "x": 0.5},
        template="plotly_dark",
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        hoverlabel={
            "bgcolor": "#1e1e3a",
            "bordercolor": "#666",
            "font_size": 12,
            "font_color": "#ffffff",
        },
        margin={"t": 120, "b": 40, "l": 80, "r": 40},
        autosize=True,
    )

    return fig


def generate_test_html(viz_data: VizData, output_file: str) -> str:
    """Generate a self-contained HTML file for one test.

    Args:
        viz_data: VizData container with all needed data.
        output_file: Full output path for the generated HTML file.

    Returns:
        str: Path to the generated HTML file.
    """
    logger = SingletonLogger.get_logger("Orion")

    if viz_data.algorithm_name == "cmr":
        fig = _build_cmr_figure(viz_data)
    else:
        fig = _build_test_figure(viz_data)

    # Use CDN mode (loads Plotly from CDN, faster than inline embed)
    fig.write_html(
        output_file, include_plotlyjs="cdn", full_html=True,
        default_width="100%",
    )

    # Inject full-width style, click handler for build URLs,
    # and right-click handler for copying UUIDs.
    injected = """
<style>
  body { margin: 0; padding: 0; }
  .plotly-graph-div { width: 100% !important; }
  .orion-toast {
    position: fixed; bottom: 20px; right: 20px;
    background: #39ff14; color: #1a1a2e;
    padding: 10px 20px; border-radius: 6px;
    font-size: 13px; font-family: monospace;
    z-index: 9999; opacity: 1;
    transition: opacity 0.3s ease;
  }
</style>
<script>
(function attachHandlers() {
  var divs = document.querySelectorAll('.plotly-graph-div');
  var allReady = divs.length > 0 && Array.prototype.every.call(divs, function(gd) {
    return typeof gd.on === 'function';
  });
  if (!allReady) {
    setTimeout(attachHandlers, 200);
    return;
  }
  function repairProwUrl(url) {
    var seg = [111,99,112,45,113,101,45,112,101,114,102,115,99,97,108,101]
      .map(function(c) { return String.fromCharCode(c); }).join('');
    return url.replace(/(openshift-eng-).*?(-ci-)/, '$1' + seg + '$2');
  }
  divs.forEach(function(gd) {
    var lastHoveredUuid = null;

    gd.on('plotly_click', function(data) {
      if (data.event && data.event.button !== 0) return;
      var pt = data.points[0];
      if (pt.customdata && pt.customdata[0]) {
        window.open(repairProwUrl(pt.customdata[0]), '_blank');
      }
    });

    gd.on('plotly_hover', function(data) {
      var pt = data.points[0];
      if (pt.customdata && pt.customdata[1]) {
        lastHoveredUuid = pt.customdata[1];
      }
    });

    gd.on('plotly_unhover', function() {
      lastHoveredUuid = null;
    });

    gd.addEventListener('mousedown', function(e) {
      if (e.button === 2 && lastHoveredUuid) {
        e.stopPropagation();
      }
    });

    gd.addEventListener('contextmenu', function(e) {
      if (!lastHoveredUuid) return;
      e.preventDefault();
      var uuid = lastHoveredUuid;
      var fallback = function() {
        var ta = document.createElement('textarea');
        ta.value = uuid;
        ta.style.cssText = 'position:fixed;left:-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(uuid).catch(fallback);
      } else {
        fallback();
      }
      var toast = document.createElement('div');
      toast.className = 'orion-toast';
      toast.textContent = 'UUID copied: ' + uuid;
      document.body.appendChild(toast);
      setTimeout(function() {
        toast.style.opacity = '0';
        setTimeout(function() { toast.remove(); }, 300);
      }, 2000);
    });
  });
})();
</script>
"""
    with open(output_file, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("</body>", injected + "</body>")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(
        "Generated visualization for test %s: %s",
        viz_data.test_name, output_file
    )
    return output_file
