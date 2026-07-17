"""
navbar.py
Top navbar + live ticker bar, replacing Streamlit's default sidebar page list
(which gets hidden via CSS in theme.py) with a horizontal nav matching the
Clean Light design reference.

Usage: call render_navbar(current="Dashboard") near the top of every page,
right after apply_theme(). The sidebar remains available for page-specific
filters/settings (symbol picker, timeframe, etc.) -- only the auto-generated
page list is hidden, not the sidebar itself.
"""

import streamlit as st

# (display label, target page path, icon) -- path must match the actual file
# under pages/ (or "app.py" for the main page).
NAV_ITEMS = [
    ("Dashboard", "app.py", "📊"),
    ("Pro Chart", "pages/1_Pro_Chart.py", "📉"),
    ("Option Chain", "pages/2_Option_Chain.py", "🔗"),
    ("Greeks", "pages/6_Greeks_Panel.py", "🧮"),
    ("Strategy", "pages/7_Strategy_Builder.py", "🏗️"),
    ("Journal", "pages/3_Trading_Journal.py", "📝"),
    ("Risk", "pages/4_Risk_Manager.py", "🛡️"),
    ("Adjustments", "pages/8_Adjustments.py", "🔄"),
    ("Order Preview", "pages/5_Order_Preview.py", "🧾"),
]

TICKER_SYMBOLS = ["NIFTY 50", "NIFTY BANK", "INDIA VIX", "SENSEX"]


def render_navbar(current: str):
    """Renders the horizontal pill-style navbar. `current` must match a label
    in NAV_ITEMS so that item renders as active."""
    cols = st.columns(len(NAV_ITEMS))
    for col, (label, path, icon) in zip(cols, NAV_ITEMS):
        with col:
            if label == current:
                st.markdown(
                    f'<div class="pmp-nav-active">{icon} {label}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.page_link(path, label=f"{icon} {label}")
    st.markdown('<hr class="pmp-nav-rule">', unsafe_allow_html=True)


def render_ticker():
    """Renders a live index ticker strip. Best-effort -- fails silently (shows
    nothing) if the data source can't supply quotes, rather than breaking the page."""
    try:
        from modules.data_source import get_data_source
        ds = get_data_source()
    except Exception:
        return

    cells = []
    for sym in TICKER_SYMBOLS:
        try:
            ltp = ds.get_ltp(sym)
            cells.append((sym, f"{ltp:,.2f}"))
        except Exception:
            continue

    if not cells:
        return

    html = '<div class="pmp-ticker">'
    for sym, price in cells:
        html += f'<div class="pmp-ticker-cell"><span class="s">{sym}</span><span class="p">{price}</span></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)
