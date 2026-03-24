"""
orion.visualization

Module for generating interactive HTML visualizations of Orion test results
using plotly. Generates self-contained HTML files with embedded JS.
"""

import re

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from orion.logger import SingletonLogger


class VizData:  # pylint: disable=too-few-public-methods
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
        filename_suffix: str = "",
    ):
        self.test_name = test_name
        self.dataframe = dataframe
        self.metrics_config = metrics_config
        self.change_points_by_metric = change_points_by_metric
        self.uuid_field = uuid_field
        self.version_field = version_field
        self.acked_entries = acked_entries or []
        self.filename_suffix = filename_suffix


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


def _build_test_figure(viz_data: VizData) -> go.Figure:
    """Build a plotly Figure for a single test with one subplot per metric."""
    df = viz_data.dataframe
    metrics = list(viz_data.metrics_config.keys())

    def _sort_key(m):
        cps = viz_data.change_points_by_metric.get(m, [])
        if not cps:
            return (2, m)  # stable → bottom
        direction = viz_data.metrics_config[m].get("direction", 0)
        has_regression = any(
            _classify_changepoint(cp.stats, direction)[1] for cp in cps
        )
        return (0, m) if has_regression else (1, m)

    metrics = sorted(metrics, key=_sort_key)
    n_metrics = len(metrics)

    if n_metrics == 0:
        fig = go.Figure()
        fig.update_layout(title_text=f"Orion: {viz_data.test_name} (no metrics)")
        return fig

    timestamps = _prepare_timestamps(df)
    versions = df.get(viz_data.version_field, pd.Series(["N/A"] * len(df)))
    uuids = df.get(viz_data.uuid_field, pd.Series(["N/A"] * len(df)))
    build_urls = df.get("buildUrl", pd.Series([""] * len(df)))

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
        metric_config = viz_data.metrics_config[metric_name]
        values = df[metric_name]
        change_points = viz_data.change_points_by_metric.get(metric_name, [])
        line_color = line_colors[(row_idx - 1) % len(line_colors)]

        # Rich hover with all relevant metadata
        hover_texts = []
        for i, (ts, v, u, val) in enumerate(
            zip(timestamps, versions, uuids, values)
        ):
            url = build_urls.iloc[i] if i < len(build_urls) else ""
            hover_texts.append(
                f"<b>{metric_name}: {val}</b><br>"
                f"Date: {ts.strftime('%Y-%m-%d %H:%M UTC')}<br>"
                f"Version: {v}<br>"
                f"UUID: {u}<br>"
                f"Build: {url[-60:]}"
            )

        # Main time-series trace
        fig.add_trace(
            go.Scatter(
                x=x_indices,
                y=values,
                mode="lines+markers",
                name=metric_name,
                hovertext=hover_texts,
                hoverinfo="text",
                customdata=[[build_urls.iloc[i]] for i in range(len(df))],
                marker={"size": 6, "color": line_color},
                line={"width": 2, "color": line_color},
                connectgaps=False,
                showlegend=False,
            ),
            row=row_idx,
            col=1,
        )

        # Mean line
        mean_val = values.mean()
        fig.add_hline(
            y=mean_val,
            row=row_idx,
            col=1,
            line_dash="dot",
            line_color="rgba(255,255,255,0.3)",
            line_width=1,
            annotation_text=f"avg: {mean_val:,.0f}",
            annotation_position="right",
            annotation_font_color="rgba(255,255,255,0.5)",
            annotation_font_size=9,
        )

        # Changepoint markers and annotations
        for cp in change_points:
            idx = cp.index
            if idx >= len(df):
                continue
            cp_value = values.iloc[idx]

            direction = metric_config.get("direction", 0)
            pct_change, is_regression = _classify_changepoint(
                cp.stats, direction
            )
            color = "#ff4444" if is_regression else "#39ff14"
            cp_build_url = (
                build_urls.iloc[idx] if idx < len(build_urls) else ""
            )

            # Changepoint marker
            fig.add_trace(
                go.Scatter(
                    x=[idx],
                    y=[cp_value],
                    mode="markers",
                    marker={
                        "size": 14,
                        "color": color,
                        "symbol": "diamond",
                        "line": {"width": 2, "color": "white"},
                    },
                    showlegend=False,
                    hovertext=(
                        f"<b>CHANGEPOINT</b><br>"
                        f"{pct_change:+.1f}% change<br>"
                        f"Mean before: {cp.stats.mean_1:,.2f}<br>"
                        f"Mean after: {cp.stats.mean_2:,.2f}<br>"
                        f"Build: {cp_build_url[-60:]}"
                    ),
                    hoverinfo="text",
                    customdata=[[cp_build_url]],
                ),
                row=row_idx,
                col=1,
            )

            # Vertical dashed line at changepoint
            fig.add_vline(
                x=idx,
                row=row_idx,
                col=1,
                line_dash="dash",
                line_color=color,
                line_width=1.5,
            )

            # Percentage change annotation
            y_range = values.max() - values.min()
            fig.add_annotation(
                x=idx,
                y=values.max() + y_range * 0.08,
                text=f"<b>{pct_change:+.1f}%</b>",
                showarrow=False,
                font={"color": color, "size": 11},
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
                    hovertext=(
                        f"<b>ACKed</b><br>"
                        f"Reason: {ack['reason']}<br>"
                        f"UUID: {ack['uuid'][:8]}"
                    ),
                    hoverinfo="text",
                    customdata=[[ack_build_url]],
                ),
                row=row_idx,
                col=1,
            )

        # Add consistent y-axis padding so all subplots look similar.
        # For nearly-flat metrics, ensure at least 5% of the mean as padding
        # so the data fills the subplot instead of being a thin line.
        y_min = values.min()
        y_max = values.max()
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
        len(v) for v in viz_data.change_points_by_metric.values()
    )

    # Build per-metric changepoint summary
    cp_parts = []
    for metric_name, cps in viz_data.change_points_by_metric.items():
        for cp in cps:
            direction = viz_data.metrics_config.get(
                metric_name, {}
            ).get("direction", 0)
            pct, is_regression = _classify_changepoint(
                cp.stats, direction
            )
            color = "#ff4444" if is_regression else "#39ff14"
            cp_parts.append(
                f"<span style='color:{color}'>"
                f"{metric_name}: {pct:+.1f}%</span>"
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
        margin={"t": 160, "b": 40, "l": 80, "r": 40},
        autosize=True,
    )

    for row_idx in range(1, n_metrics + 1):
        fig.update_xaxes(
            tickvals=x_indices,
            ticktext=tick_labels,
            tickangle=0,
            tickfont={"size": 9},
            gridcolor="rgba(255,255,255,0.08)",
            row=row_idx,
            col=1,
        )

    return fig


def generate_test_html(viz_data: VizData, output_base_path: str) -> str:
    """Generate a self-contained HTML file for one test.

    Args:
        viz_data: VizData container with all needed data.
        output_base_path: Base path for output files (without extension).

    Returns:
        str: Path to the generated HTML file.
    """
    logger = SingletonLogger.get_logger("Orion")

    fig = _build_test_figure(viz_data)
    suffix = f"_{viz_data.filename_suffix}" if viz_data.filename_suffix else ""
    output_file = f"{output_base_path}_{viz_data.test_name}{suffix}_viz.html"
    fig.write_html(
        output_file, include_plotlyjs="cdn", full_html=True,
        default_width="100%",
    )

    # Inject full-width style and click handler for build URLs
    injected = """
<style>
  body { margin: 0; padding: 0; }
  .plotly-graph-div { width: 100% !important; }
</style>
<script>
(function attachClickHandlers() {
  var divs = document.querySelectorAll('.plotly-graph-div');
  var allReady = divs.length > 0 && Array.prototype.every.call(divs, function(gd) {
    return typeof gd.on === 'function';
  });
  if (!allReady) {
    setTimeout(attachClickHandlers, 200);
    return;
  }
  divs.forEach(function(gd) {
    gd.on('plotly_click', function(data) {
      var pt = data.points[0];
      if (pt.customdata && pt.customdata[0]) {
        window.open(pt.customdata[0], '_blank');
      }
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
