"""Plotly chart helpers — neutral styling, no alarm colors."""

from __future__ import annotations

from typing import Any

import plotly.express as px
import plotly.graph_objects as go


NEUTRAL_COLORS = ["#4A6FA5", "#6B8F71", "#8B7355", "#5C6B7A", "#9A8C7A"]


def bar_chart(
    rows: list[dict[str, Any]],
    *,
    x: str,
    y: str,
    title: str,
    y_title: str | None = None,
    color: str | None = None,
) -> go.Figure:
    if not rows:
        fig = go.Figure()
        fig.update_layout(
            title=title,
            annotations=[dict(text="NOT_AVAILABLE", showarrow=False)],
            height=320,
        )
        return fig
    fig = px.bar(
        rows,
        x=x,
        y=y,
        color=color,
        title=title,
        color_discrete_sequence=NEUTRAL_COLORS,
    )
    fig.update_layout(
        margin=dict(l=40, r=20, t=50, b=40),
        height=320,
        yaxis_title=y_title or y,
    )
    return fig


def single_metric_bars(
    rows: list[dict[str, Any]],
    *,
    label_key: str,
    value_key: str,
    title: str,
    y_title: str,
) -> go.Figure:
    """One metric per chart — avoids mixing higher-is-better with lower-is-better."""
    if not rows:
        fig = go.Figure()
        fig.update_layout(
            title=title,
            annotations=[dict(text="NOT_AVAILABLE", showarrow=False)],
            height=300,
        )
        return fig
    fig = go.Figure(
        data=[
            go.Bar(
                x=[r[label_key] for r in rows],
                y=[r[value_key] for r in rows],
                marker_color=NEUTRAL_COLORS[0],
                text=[f"{float(r[value_key]):.4f}" for r in rows],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=title,
        xaxis_title="Hypothesis",
        yaxis_title=y_title,
        margin=dict(l=40, r=20, t=50, b=80),
        height=320,
    )
    fig.update_xaxes(tickangle=-20)
    return fig


def quality_pie(counts: dict[str, int], *, title: str = "Quality label distribution") -> go.Figure:
    if not counts or sum(counts.values()) == 0:
        fig = go.Figure()
        fig.update_layout(
            title=title,
            annotations=[dict(text="NOT_AVAILABLE", showarrow=False)],
            height=320,
        )
        return fig
    labels = list(counts.keys())
    values = list(counts.values())
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.35,
                marker=dict(colors=NEUTRAL_COLORS[: len(labels)]),
                textinfo="label+percent",
            )
        ]
    )
    fig.update_layout(title=title, margin=dict(l=20, r=20, t=50, b=20), height=360)
    return fig
