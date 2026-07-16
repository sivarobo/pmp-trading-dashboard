"""
chart.py
Builds the main candlestick chart with VWAP / CPR / PDH-PDL overlays
using Plotly, styled for a dark trading-terminal look.
"""

import plotly.graph_objects as go
import pandas as pd


def build_plain_chart(df: pd.DataFrame, title: str = "Chart") -> go.Figure:
    """Simple candlestick chart without VWAP/CPR/PDH-PDL overlays -- for daily/weekly/monthly
    timeframes where those session-based concepts don't apply."""
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["datetime"] if "datetime" in df.columns else df["date"],
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a", decreasing_fillcolor="#ef5350",
        name="Price",
    ))
    fig.update_layout(
        title=title, template="plotly_dark", paper_bgcolor="#131722", plot_bgcolor="#131722",
        xaxis_rangeslider_visible=False, height=560, margin=dict(l=10, r=60, t=40, b=10),
        font=dict(size=11),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#2a2e39")
    fig.update_yaxes(showgrid=True, gridcolor="#2a2e39")
    return fig


def build_regime_chart(day_df: pd.DataFrame, vwap: pd.Series, cpr: dict,
                        pdh_pdl: dict, ib: dict, weekly_hl: dict = None,
                        title: str = "NIFTY 50 — 15 Min") -> go.Figure:
    fig = go.Figure()

    # --- Candlesticks ---
    fig.add_trace(go.Candlestick(
        x=day_df["datetime"],
        open=day_df["open"],
        high=day_df["high"],
        low=day_df["low"],
        close=day_df["close"],
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a",
        decreasing_fillcolor="#ef5350",
        name="Price",
    ))

    # --- VWAP ---
    fig.add_trace(go.Scatter(
        x=day_df["datetime"], y=vwap.values,
        line=dict(color="#ffb300", width=1.6),
        name="VWAP",
    ))

    # --- CPR lines (pivot / TC / BC) ---
    if cpr:
        for label, val, color, dash in [
            ("Pivot", cpr["pivot"], "#82b1ff", "dot"),
            ("TC", cpr["tc"], "#64b5f6", "dash"),
            ("BC", cpr["bc"], "#64b5f6", "dash"),
        ]:
            fig.add_hline(y=val, line_color=color, line_dash=dash, line_width=1,
                          annotation_text=label, annotation_position="right",
                          annotation_font_size=10, annotation_font_color=color)

    # --- PDH / PDL ---
    if pdh_pdl.get("pdh"):
        fig.add_hline(y=pdh_pdl["pdh"], line_color="#ce93d8", line_dash="dashdot", line_width=1,
                      annotation_text="PDH", annotation_position="right",
                      annotation_font_size=10, annotation_font_color="#ce93d8")
    if pdh_pdl.get("pdl"):
        fig.add_hline(y=pdh_pdl["pdl"], line_color="#ce93d8", line_dash="dashdot", line_width=1,
                      annotation_text="PDL", annotation_position="right",
                      annotation_font_size=10, annotation_font_color="#ce93d8")

    # --- Weekly High / Low ---
    if weekly_hl:
        if weekly_hl.get("wh"):
            fig.add_hline(y=weekly_hl["wh"], line_color="#ff8a65", line_dash="longdash", line_width=1.2,
                          annotation_text="WH", annotation_position="right",
                          annotation_font_size=10, annotation_font_color="#ff8a65")
        if weekly_hl.get("wl"):
            fig.add_hline(y=weekly_hl["wl"], line_color="#ff8a65", line_dash="longdash", line_width=1.2,
                          annotation_text="WL", annotation_position="right",
                          annotation_font_size=10, annotation_font_color="#ff8a65")

    # --- Initial Balance shading ---
    if ib.get("ib_high") and ib.get("ib_low"):
        fig.add_hrect(y0=ib["ib_low"], y1=ib["ib_high"],
                      fillcolor="#90a4ae", opacity=0.08, line_width=0)

    fig.update_layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor="#131722",
        plot_bgcolor="#131722",
        xaxis_rangeslider_visible=False,
        height=560,
        margin=dict(l=10, r=60, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(size=11),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#2a2e39")
    fig.update_yaxes(showgrid=True, gridcolor="#2a2e39")

    return fig
