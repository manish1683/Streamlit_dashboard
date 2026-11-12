import html
import io
import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================ design tokens ==
INK = "#14213D"
TEAL = "#0E7C86"
AMBER = "#E09F3E"
BRICK = "#C8553D"
MUTED = "#5B6B7F"
RULE = "#DDE3EA"
GRID = "#E8ECF1"
PALETTE = [TEAL, AMBER, INK, BRICK, "#6B9080", "#8E7DBE", "#9AA5B1"]
SCALE = ["#E6F2F3", TEAL, INK]
FONT = "IBM Plex Sans, Segoe UI, sans-serif"

st.set_page_config(page_title="Report Explorer", page_icon="📊", layout="wide")

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');
.stApp {{ font-family: {FONT}; }}
h1, h2, h3, h4 {{ font-family: {FONT}; color: {INK}; letter-spacing: -0.01em; }}
#MainMenu, footer, .stDeployButton {{ visibility: hidden; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }}

/* header banner */
.banner {{ background: {INK}; color: #fff; border-radius: 6px; padding: 22px 28px; margin-bottom: 14px; }}
.banner h1 {{ color: #fff; font-size: 1.55rem; margin: 0 0 4px 0; padding: 0; font-weight: 600; }}
.banner p {{ color: #B9C4D4; margin: 0; font-size: 0.92rem; }}

/* KPI strip: one connected bar, divided by rules */
.kpi-strip {{ display: flex; background: #fff; border: 1px solid {RULE}; border-radius: 6px; margin-bottom: 18px; overflow: hidden; }}
.kpi {{ flex: 1; padding: 14px 20px; border-right: 1px solid {RULE}; min-width: 0; }}
.kpi:last-child {{ border-right: none; }}
.kpi-label {{ color: {MUTED}; font-size: 0.8rem; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.kpi-value {{ color: {INK}; font-size: 1.65rem; font-weight: 600; line-height: 1.2; }}
.kpi-note {{ color: {MUTED}; font-size: 0.78rem; margin-top: 2px; }}

/* chart cards */
[data-testid="stVerticalBlockBorderWrapper"] {{ background: #fff; border-color: {RULE} !important; border-radius: 6px; }}

/* tabs */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid {RULE}; }}
.stTabs [data-baseweb="tab"] {{ height: 42px; padding: 0 14px; font-weight: 500; }}
.stTabs [aria-selected="true"] {{ color: {TEAL}; }}

/* sidebar */
[data-testid="stSidebar"] {{ border-right: 1px solid {RULE}; }}
.brand {{ font-weight: 600; font-size: 1.15rem; color: {INK}; margin-bottom: 2px; }}
.brand-sub {{ color: {MUTED}; font-size: 0.82rem; margin-bottom: 14px; }}
</style>
""",
    unsafe_allow_html=True,
)


# ================================================================= helpers ====
def human(n) -> str:
    if n is None or pd.isna(n):
        return "–"
    n = float(n)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}"
    return f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"


def kpi_strip(items):
    cells = "".join(
        f'<div class="kpi"><div class="kpi-label">{html.escape(str(l))}</div>'
        f'<div class="kpi-value">{html.escape(str(v))}</div>'
        f'<div class="kpi-note">{html.escape(str(n))}</div></div>'
        for l, v, n in items
    )
    st.markdown(f'<div class="kpi-strip">{cells}</div>', unsafe_allow_html=True)


def style(fig, height=400):
    fig.update_layout(
        template="simple_white",
        height=height,
        colorway=PALETTE,
        font=dict(family=FONT, size=13, color=INK),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=52, b=8),
        title=dict(font=dict(size=15), x=0, xanchor="left"),
        legend=dict(orientation="h", y=-0.22, title=None),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    fig.update_xaxes(showgrid=False, linecolor=RULE, title_font=dict(size=12, color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title_font=dict(size=12, color=MUTED))
    return fig


def card(fig):
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False})


def pick(label, options, container=st, allow_none=False, **kw):
    opts = ([None] if allow_none else []) + list(options)
    return container.selectbox(label, opts, format_func=lambda v: "None" if v is None else v, **kw)


# ============================================================== data loading ==
@st.cache_data(show_spinner=False)
def get_sheet_names(file_bytes: bytes):
    return pd.ExcelFile(io.BytesIO(file_bytes)).sheet_names


@st.cache_data(show_spinner="Reading file...")
def load_data(file_bytes: bytes, filename: str, sheet=None) -> pd.DataFrame:
    if filename.lower().endswith(".csv"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes))
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1")
    else:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet)

    df.columns = [str(c).strip() for c in df.columns]

    # Convert text columns that are really dates
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s) or pd.api.types.is_bool_dtype(s):
            continue
        sample = s.dropna().head(200)
        if sample.empty:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ok = pd.to_datetime(sample, errors="coerce").notna().mean() > 0.9
            if ok:
                df[col] = pd.to_datetime(s, errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def demo_data() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 1500
    dates = pd.to_datetime("2025-01-01") + pd.to_timedelta(rng.integers(0, 600, n), unit="D")
    region = rng.choice(["North", "South", "East", "West", "Central"], n, p=[0.25, 0.2, 0.2, 0.2, 0.15])
    product = rng.choice(["Router", "Switch", "Firewall", "Access Point", "Cable Kit", "Gateway"], n)
    channel = rng.choice(["Direct", "Partner", "Online"], n, p=[0.4, 0.35, 0.25])
    units = rng.integers(1, 40, n)
    price = pd.Series(product).map(
        {"Router": 120, "Switch": 210, "Firewall": 560, "Access Point": 150, "Cable Kit": 25, "Gateway": 310}
    ).to_numpy()
    season = 1 + 0.25 * np.sin((dates.dayofyear.to_numpy() / 365) * 2 * np.pi)
    sales = (units * price * season * rng.normal(1, 0.08, n)).round(2)
    cost = (sales * rng.uniform(0.55, 0.8, n)).round(2)
    df = pd.DataFrame(
        {"Order Date": dates, "Region": region, "Product": product, "Channel": channel,
         "Units": units, "Sales": sales, "Cost": cost}
    )
    df["Profit"] = (df["Sales"] - df["Cost"]).round(2)
    df.loc[rng.choice(n, 25, replace=False), "Channel"] = None
    return df.sort_values("Order Date").reset_index(drop=True)


# ================================================================== sidebar ===
with st.sidebar:
    st.markdown('<div class="brand">Report Explorer</div><div class="brand-sub">Upload a report, explore it visually</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("Reports (CSV or Excel)", type=["csv", "xlsx", "xls"], accept_multiple_files=True)

if not uploaded and not st.session_state.get("demo"):
    st.markdown(
        '<div class="banner"><h1>Report Explorer</h1><p>Turn CSV and Excel reports into charts you can read at a glance.</p></div>',
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown("#### Get started")
        st.write("Upload one or more reports from the sidebar, or load sample sales data to see how the dashboard works.")
        if st.button("Load sample data", type="primary"):
            st.session_state["demo"] = True
            st.rerun()
    st.stop()

with st.sidebar:
    sheet = None
    if uploaded:
        st.session_state["demo"] = False
        names = [f.name for f in uploaded]
        chosen_name = st.selectbox("Report", names)
        file_bytes = next(f for f in uploaded if f.name == chosen_name).getvalue()
        if not chosen_name.lower().endswith(".csv"):
            sheet = st.selectbox("Sheet", get_sheet_names(file_bytes))
        df_raw = load_data(file_bytes, chosen_name, sheet)
    else:
        chosen_name = "sample_sales.csv"
        df_raw = demo_data()
        st.caption("Showing sample data. Upload a file to replace it.")
        if st.button("Clear sample data"):
            st.session_state["demo"] = False
            st.rerun()

    num_all = df_raw.select_dtypes(include="number").columns.tolist()
    st.markdown("---")
    metric = st.selectbox("Main metric", num_all, help="Used for the headline numbers and the Overview charts.") if num_all else None

    st.markdown("---")
    st.markdown("**Filters**")
    df = df_raw.copy()
    filter_cols = st.multiselect("Columns to filter", df.columns.tolist())
    for col in filter_cols:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            lo, hi = float(s.min()), float(s.max())
            if lo < hi:
                r = st.slider(col, lo, hi, (lo, hi))
                df = df[df[col].between(*r)]
        elif pd.api.types.is_datetime64_any_dtype(s) and s.notna().any():
            r = st.date_input(col, (s.min().date(), s.max().date()))
            if isinstance(r, tuple) and len(r) == 2:
                df = df[(df[col].dt.date >= r[0]) & (df[col].dt.date <= r[1])]
        else:
            opts = sorted(s.dropna().astype(str).unique().tolist())
            sel = st.multiselect(col, opts, default=opts)
            df = df[df[col].astype(str).isin(sel) | df[col].isna()]

num_cols = df.select_dtypes(include="number").columns.tolist()
date_cols = df.select_dtypes(include="datetime").columns.tolist()
cat_cols = [c for c in df.columns if c not in num_cols and c not in date_cols]
cat_small = [c for c in cat_cols if 2 <= df[c].nunique() <= 50]

# ================================================================== header ====
sub = chosen_name + (f"  /  {sheet}" if sheet else "")
st.markdown(
    f'<div class="banner"><h1>{html.escape(sub)}</h1>'
    f'<p>{len(df):,} of {len(df_raw):,} rows shown after filters</p></div>',
    unsafe_allow_html=True,
)

if df.empty:
    st.warning("No rows match the current filters. Widen or clear a filter in the sidebar.")
    st.stop()

items = [("Rows", f"{len(df):,}", f"{df.shape[1]} columns")]
if metric:
    items += [
        (f"{metric}, total", human(df[metric].sum()), f"across {len(df):,} rows"),
        (f"{metric}, average", human(df[metric].mean()), f"median {human(df[metric].median())}"),
        (f"{metric}, highest", human(df[metric].max()), f"lowest {human(df[metric].min())}"),
    ]
miss_pct = df.isna().sum().sum() / df.size * 100
items.append(("Missing values", f"{miss_pct:.1f}%", f"{int(df.isna().sum().sum()):,} empty cells"))
kpi_strip(items)

tab_over, tab_build, tab_data, tab_quality = st.tabs(["Overview", "Chart builder", "Data table", "Data quality"])

# ================================================================= overview ===
with tab_over:
    if not metric:
        st.info("This report has no numeric columns, so there is nothing to chart yet. Use the Data quality tab to inspect it.")
    else:
        if date_cols:
            dcol = date_cols[0]
            span_days = (df[dcol].max() - df[dcol].min()).days
            freq, label = ("MS", "month") if span_days > 90 else ("D", "day")
            trend = df.set_index(dcol)[metric].resample(freq).sum().reset_index()
            fig = px.area(trend, x=dcol, y=metric, title=f"{metric} by {label}")
            fig.update_traces(line_color=TEAL, fillcolor="rgba(14,124,134,0.15)")
            card(style(fig, 340))

        c1, c2 = st.columns(2)
        with c1:
            if cat_small:
                ccol = st.selectbox("Break down by", cat_small, key="ov_cat")
                top = df.groupby(ccol)[metric].sum().nlargest(10).sort_values().reset_index()
                fig = px.bar(top, x=metric, y=ccol, orientation="h", title=f"{metric} by {ccol}")
                fig.update_traces(marker_color=TEAL)
                card(style(fig, 380))
            else:
                st.info("No category columns found for a breakdown.")
        with c2:
            st.markdown("<div style='height:5.2rem'></div>" if cat_small else "", unsafe_allow_html=True)
            fig = px.histogram(df, x=metric, nbins=30, title=f"How {metric} is distributed")
            fig.update_traces(marker_color=AMBER)
            card(style(fig, 380))

# ================================================================== builder ===
AGGS = ["sum", "mean", "median", "min", "max", "count"]
with tab_build:
    all_cols = df.columns.tolist()
    ctrl = st.container(border=True)
    with ctrl:
        chart_type = st.radio(
            "Chart type", ["Bar", "Line", "Area", "Scatter", "Histogram", "Box", "Pie", "Correlation"], horizontal=True
        )
        fig, err = None, None
        try:
            if chart_type in ("Bar", "Line", "Area"):
                a, b, c, d = st.columns(4)
                x = pick("X axis", all_cols, a)
                y = pick("Value", num_cols or all_cols, b)
                color = pick("Split by", [c_ for c_ in all_cols if c_ != x], c, allow_none=True)
                agg = pick("Aggregate", AGGS, d)
                group = [x] + ([color] if color else [])
                plot = df.groupby(group, dropna=False, as_index=False)[y].agg(agg)
                if chart_type == "Bar":
                    top_n = st.slider("Show top", 5, 100, 20)
                    keep = plot.groupby(x)[y].sum().nlargest(top_n).index
                    plot = plot[plot[x].isin(keep)]
                    fig = px.bar(plot, x=x, y=y, color=color, barmode="group", title=f"{agg.title()} of {y} by {x}")
                else:
                    plot = plot.sort_values(x)
                    fn = px.line if chart_type == "Line" else px.area
                    fig = fn(plot, x=x, y=y, color=color, title=f"{agg.title()} of {y} by {x}")
            elif chart_type == "Scatter":
                a, b, c, d = st.columns(4)
                x = pick("X", num_cols, a)
                y = pick("Y", [n for n in num_cols if n != x] or num_cols, b)
                color = pick("Colour", all_cols, c, allow_none=True)
                size = pick("Size", num_cols, d, allow_none=True)
                fig = px.scatter(df, x=x, y=y, color=color, size=size, opacity=0.75, title=f"{y} against {x}")
            elif chart_type == "Histogram":
                a, b, c = st.columns(3)
                x = pick("Column", all_cols, a)
                color = pick("Split by", cat_small, b, allow_none=True)
                bins = c.slider("Bins", 5, 100, 30)
                fig = px.histogram(df, x=x, color=color, nbins=bins, title=f"Distribution of {x}")
            elif chart_type == "Box":
                a, b = st.columns(2)
                y = pick("Value", num_cols, a)
                x = pick("Group by", cat_small, b, allow_none=True)
                fig = px.box(df, x=x, y=y, title=f"Spread of {y}")
            elif chart_type == "Pie":
                a, b, c = st.columns(3)
                names = pick("Category", cat_small or all_cols, a)
                values = pick("Value", num_cols, b)
                top_n = c.slider("Top slices", 3, 20, 8)
                plot = df.groupby(names, as_index=False)[values].sum().nlargest(top_n, values)
                fig = px.pie(plot, names=names, values=values, hole=0.45, title=f"Share of {values} by {names}")
            elif chart_type == "Correlation":
                if len(num_cols) < 2:
                    err = "Correlation needs at least two numeric columns."
                else:
                    fig = px.imshow(df[num_cols].corr(), text_auto=".2f", aspect="auto",
                                    color_continuous_scale=SCALE, zmin=-1, zmax=1,
                                    title="How strongly numeric columns move together")
        except Exception as e:
            err = f"This combination can't be charted: {e}"

    if err:
        st.warning(err)
    elif fig is not None:
        card(style(fig, 520))
        st.download_button("Download chart (HTML)", fig.to_html(include_plotlyjs="cdn"), "chart.html", "text/html")

# =================================================================== table ====
with tab_data:
    st.dataframe(df, width="stretch", height=480)
    st.download_button(
        "Download filtered data (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"filtered_{chosen_name.rsplit('.', 1)[0]}.csv",
        mime="text/csv",
    )

# ================================================================== quality ===
with tab_quality:
    profile = pd.DataFrame(
        {
            "Column": df.columns,
            "Type": [str(t) for t in df.dtypes],
            "Filled": df.notna().sum().values,
            "Missing %": (df.isna().mean() * 100).round(1).values,
            "Unique values": df.nunique().values,
        }
    )
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Column profile**")
        st.dataframe(profile, width="stretch", hide_index=True, height=420)
    with right:
        miss = profile[profile["Missing %"] > 0].sort_values("Missing %")
        if miss.empty:
            st.success("Every column is fully filled.")
        else:
            fig = px.bar(miss, x="Missing %", y="Column", orientation="h", title="Columns with missing values")
            fig.update_traces(marker_color=BRICK)
            card(style(fig, 420))
    if num_cols:
        with st.expander("Summary statistics for numeric columns"):
            st.dataframe(df[num_cols].describe().T, width="stretch")
