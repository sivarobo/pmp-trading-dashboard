"""
theme.py
Injects custom CSS to push Streamlit's default look toward the "Clean Light"
design (Template 2) -- card-style metrics, pill tabs, rounded borders, the
Inter/Roboto Mono type pairing, and the blue/green/red accent palette.

This is a CSS-injection approach, not a rebuild -- it gets Streamlit's stock
components most of the way there without fighting the framework's own DOM
structure. Call apply_theme() once near the top of every page, right after
init_env().
"""

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto+Mono:wght@400;500;600&display=swap');

:root {
    --pmp-bg: #f7f8fa;
    --pmp-card: #ffffff;
    --pmp-line: #e8eaee;
    --pmp-text: #1d2330;
    --pmp-muted: #8a92a3;
    --pmp-up: #00a25b;
    --pmp-down: #e5484d;
    --pmp-accent: #4361ee;
    --pmp-accent-soft: #eef1fe;
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, sans-serif;
}

/* Main content area breathing room */
.block-container {
    padding-top: 1.5rem;
    max-width: 1280px;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: var(--pmp-card);
    border-right: 1px solid var(--pmp-line);
}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    font-weight: 700;
    color: var(--pmp-text);
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: var(--pmp-card);
    border: 1px solid var(--pmp-line);
    border-radius: 14px;
    padding: 12px 14px;
    box-shadow: 0 1px 2px rgba(16,24,40,0.04);
    overflow: visible !important;
}
div[data-testid="stMetric"] * {
    overflow: visible !important;
    text-overflow: unset !important;
    white-space: normal !important;
}
div[data-testid="stMetricLabel"],
div[data-testid="stMetricLabel"] * {
    font-size: 10.5px !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--pmp-muted) !important;
    font-weight: 600 !important;
}
div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] * {
    font-family: 'Roboto Mono', monospace !important;
    font-weight: 700 !important;
    color: var(--pmp-text) !important;
    font-size: 1.15rem !important;
    word-break: break-word;
    line-height: 1.25 !important;
}
div[data-testid="stMetricDelta"],
div[data-testid="stMetricDelta"] * {
    font-size: 11.5px !important;
}

/* Buttons -- pill style, accent blue */
.stButton > button {
    border-radius: 8px;
    border: 1px solid var(--pmp-line);
    background: var(--pmp-card);
    color: var(--pmp-text);
    font-weight: 600;
    font-size: 13px;
    padding: 8px 18px;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    border-color: var(--pmp-accent);
    color: var(--pmp-accent);
}
.stButton > button[kind="primary"] {
    background: var(--pmp-accent);
    border-color: var(--pmp-accent);
    color: white;
}
.stButton > button[kind="primary"]:hover {
    background: #3651d4;
}

/* Tabs -- pill style */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: var(--pmp-bg);
    padding: 4px;
    border-radius: 10px;
    border: 1px solid var(--pmp-line);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 6px 16px;
    font-weight: 500;
    color: var(--pmp-muted);
}
.stTabs [aria-selected="true"] {
    background: var(--pmp-card) !important;
    color: var(--pmp-accent) !important;
    box-shadow: 0 1px 2px rgba(16,24,40,0.06);
}

/* Expanders as cards */
div[data-testid="stExpander"] {
    border: 1px solid var(--pmp-line);
    border-radius: 12px;
    background: var(--pmp-card);
}

/* Dataframes / tables */
div[data-testid="stDataFrame"] {
    border: 1px solid var(--pmp-line);
    border-radius: 10px;
    overflow: hidden;
}

/* Alert boxes -- softer, rounder */
div[data-testid="stAlert"] {
    border-radius: 10px;
    border: none;
}

/* Number/text inputs */
.stTextInput input, .stNumberInput input, .stDateInput input, .stTimeInput input {
    border-radius: 8px !important;
    border: 1px solid var(--pmp-line) !important;
}
.stSelectbox div[data-baseweb="select"] {
    border-radius: 8px;
}

/* Headings */
h1 { font-weight: 700 !important; letter-spacing: -0.3px; color: var(--pmp-text) !important; }
h2, h3 { font-weight: 600 !important; color: var(--pmp-text) !important; }

/* Captions */
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--pmp-muted) !important;
}
</style>
"""


def apply_theme():
    """Call once near the top of every page (after init_env()) to apply the
    Clean Light visual theme via CSS injection."""
    st.markdown(_CSS, unsafe_allow_html=True)
