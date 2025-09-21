# ===== Imports =====
import streamlit as st
import pandas as pd
import plotly.express as px
from data_loader import (
    load_table, national_crosswalk, top_occupations_by_employment,
    occupation_list_az, snapshot_for_occ, wage_distribution_for_occ,
    top_geographies_for_occ, employment_concentration_for_occ,
    industry_mix_for_occ, us_median_wage
)


# ===== Initial UI Configurations =====
# Page config
st.set_page_config(page_title="HireSight: Labor Market Dashboard", layout="wide")

#Bar chart color scheme
COOL_SLATE_SEQ = ["#475569", "#0EA5E9", "#94A3B8", "#22C55E"]
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = COOL_SLATE_SEQ


# ===== Sidebar: Navigation & “Top Lists” =====
st.sidebar.header("Browse Occupations")

# Highest Employment Occupations (Top 10)
top10 = top_occupations_by_employment(10)
default_occ_code = top10.iloc[0]["OCC_CODE"] if not top10.empty else None
with st.sidebar.expander("Highest-Employment Jobs", expanded=False):
    for i, row in top10.reset_index(drop=True).iterrows():
        workers = f"{int(row['TOT_EMP']):,}" if pd.notna(row['TOT_EMP']) else "NA"
        mean_wage = f"${int(row['A_MEAN']):,}" if pd.notna(row['A_MEAN']) else "NA"
        
        st.markdown(
            f"""
            {i+1}. **{row['OCC_TITLE']}**  
            &nbsp;&nbsp;Workers: {workers}  
            &nbsp;&nbsp;Mean Wage: {mean_wage}
            """
        )

# Highest Median Wage Occupations (Top 10)
with st.sidebar.expander("Highest Median Annual Wage Jobs", expanded=False):
    nat = load_table("national").copy()

    # Unified annual median series (prefer A_MEDIAN, else H_MEDIAN×2080)
    A_MED = "A_MEDIAN" if "A_MEDIAN" in nat.columns else None
    H_MED = "H_MEDIAN" if "H_MEDIAN" in nat.columns else None

    med = pd.to_numeric(nat[A_MED], errors="coerce") if A_MED else pd.Series([float("nan")] * len(nat), index=nat.index)
    if H_MED:
        med = med.fillna(pd.to_numeric(nat[H_MED], errors="coerce") * 2080)

    nat["_MED_ANNUAL"] = med
    top_med = (
        nat.dropna(subset=["_MED_ANNUAL"])
           .sort_values("_MED_ANNUAL", ascending=False)
           .reset_index(drop=True)
           .head(10)
    )

    for i, row in top_med.iterrows():
        st.markdown(
            f"""
            {i+1}. **{row['OCC_TITLE']}**  
            &nbsp;&nbsp;Median Wage: ${int(row['_MED_ANNUAL']):,}
            """
        )

# Highest 90th Percentile Annual Wage (Top 10)
with st.sidebar.expander("Highest 90th Percentile Wage Jobs", expanded=False):
    nat = load_table("national").copy()

    # Build unified annual P90 series (prefer A_PCT90, else H_PCT90×2080)
    a = "A_PCT90" if "A_PCT90" in nat.columns else None
    h = "H_PCT90" if "H_PCT90" in nat.columns else None

    p90 = pd.to_numeric(nat[a], errors="coerce") if a else pd.Series([float("nan")] * len(nat), index=nat.index)
    if h:
        p90 = p90.fillna(pd.to_numeric(nat[h], errors="coerce") * 2080)

    # If still empty, try deriving from a P10–P90 tuple column
    if p90.notna().sum() == 0:
        rng_cols = [c for c in nat.columns if ("P10" in str(c) and "P90" in str(c))]
        if rng_cols:
            expanded = pd.DataFrame(nat[rng_cols[0]].tolist(), index=nat.index, columns=["_P10", "_P90"])
            p90 = pd.to_numeric(expanded["_P90"], errors="coerce")

    if p90.notna().sum() == 0:
        st.info("No usable 90th percentile wage values.")
    else:
        nat["_P90_ANNUAL"] = p90
        top_p90 = (
            nat.dropna(subset=["_P90_ANNUAL"])
               .sort_values("_P90_ANNUAL", ascending=False)
               .reset_index(drop=True)
               .head(10)
        )

        for i, row in top_p90.iterrows():
            st.markdown(
                f"""
                {i+1}. **{row['OCC_TITLE']}**  
                &nbsp;&nbsp;90th Percentile Wage: ${int(row['_P90_ANNUAL']):,}
                """
            )

# A→Z occupation picker
all_occ = occupation_list_az()
occ_titles = all_occ["OCC_TITLE"].tolist()
occ_codes = all_occ["OCC_CODE"].tolist()

selected_title = st.sidebar.selectbox(
    "Select an occupation (A→Z)",
    occ_titles,
    index=occ_titles.index(all_occ[all_occ["OCC_CODE"] == default_occ_code]["OCC_TITLE"].values[0]) if default_occ_code in occ_codes else 0,
    key="occ_selectbox"
)
selected_code = all_occ[all_occ["OCC_TITLE"] == selected_title]["OCC_CODE"].values[0]


# ===== Page Header =====
st.title("HireSight: Labor Market Dashboard")
st.caption("HireSight helps you explore career paths, compare job outlooks, and track hiring trends — whether you’re landing your first job, planning a transition, or mapping out your future.")


# ===== Snapshot =====
# High-level KPIs for the selected occupation (national view)
st.subheader("Snapshot")
snap = snapshot_for_occ(selected_code)
cols = st.columns(3)
with cols[0]:
    median = snap.get("Median annual wage (A_MEDIAN)", float("nan"))
    st.metric("Median Annual Wage", f"${median:,.0f}")

    p10, p90 = snap.get("Wage range P10–P90 (A_PCT10–A_PCT90)", (float("nan"), float("nan")))
    st.metric("Wage Range (10th–90th)", f"${p10:,.0f} – ${p90:,.0f}")

with cols[1]:
    st.metric("Mean Wage", f"${snap.get('Mean wage (A_MEAN)', float('nan')):,.0f}")
    st.metric("Employment Size", f"{snap.get('Employment size (TOT_EMP)', float('nan')):,.0f}")

with cols[2]:
    rw = snap.get("Relative wage multiplier (A_MEDIAN / US median)", float("nan"))
    st.metric("Relative Wage Multiplier", f"{rw:,.2f}")

    st.metric("US Median (All Occupations)", f"${us_median_wage():,.0f}")

st.divider()

# ===== Compensation =====
# Percentile distribution for wages (bar chart)
st.subheader("Compensation Distribution")
st.caption(
    "Wages are shown at the 10th, 25th, 50th, 75th, and 90th percentiles. "
    "These values represent typical earnings at different points in the wage distribution, "
    "with the median (50th percentile) marking the midpoint where half earn less and half earn more."
)

wd = wage_distribution_for_occ(selected_code)
if not wd.empty:
    df_wd = wd.reset_index()
    df_wd.columns = ["Percentile", "Annual Wage"]
    fig = px.bar(df_wd, x="Percentile", y="Annual Wage", text="Annual Wage")
    fig.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
    fig.update_layout(yaxis_title="Annual Wage ($)", xaxis_title="", margin=dict(t=30,b=30))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No wage distribution data available for this occupation.")

# ===== Geography: Top Paying States & Metros =====
# Two-column layout for state and MSA comparisons
colA, colB = st.columns(2)
with colA:
    st.markdown("**Top Paying States**")
    top_states = top_geographies_for_occ(selected_code, level="state", top_n=10)
    if not top_states.empty:
        fig_s = px.bar(
            top_states.sort_values("A_MEDIAN"),
            x="A_MEDIAN", y="AREA_TITLE", orientation="h",
            labels={"A_MEDIAN": "Median Salary ($)", "AREA_TITLE": ""}
        )
        st.plotly_chart(fig_s, use_container_width=True)

        # Friendly table formatting
        states_view = (
            top_states[["AREA_TITLE", "A_MEDIAN", "TOT_EMP"]]
            .rename(columns={
                "AREA_TITLE": "State",
                "A_MEDIAN": "Median Salary",
                "TOT_EMP": "Employed"
            })
        )

        states_view["Median Salary"] = states_view["Median Salary"].apply(lambda x: f"{x:,.0f}")
        states_view["Employed"] = states_view["Employed"].apply(lambda x: f"{x:,.0f}")

        st.dataframe(states_view, use_container_width=True, hide_index=True)
    else:
        st.info("No state-level rows for this occupation.")

with colB:
    st.markdown("**Top Paying Metros**")

    top_msas = top_geographies_for_occ(selected_code, level="msa", top_n=10)
    if not top_msas.empty:
        fig_m = px.bar(
            top_msas.sort_values("A_MEDIAN"),
            x="A_MEDIAN", y="AREA_TITLE", orientation="h",
            labels={"A_MEDIAN": "Median Salary ($)", "AREA_TITLE": ""}
        )
        st.plotly_chart(fig_m, use_container_width=True)

        # Select only the columns we want, rename them, and format numbers
        msas_view = (
            top_msas[["AREA_TITLE", "A_MEDIAN", "TOT_EMP"]]
            .rename(columns={
                "AREA_TITLE": "Metro Area",
                "A_MEDIAN": "Median Salary",
                "TOT_EMP": "Employed"
            })
        )

        msas_view["Median Salary"] = msas_view["Median Salary"].apply(lambda x: f"{x:,.0f}")
        msas_view["Employed"] = msas_view["Employed"].apply(lambda x: f"{x:,.0f}")

        st.dataframe(msas_view, use_container_width=True, hide_index=True)
    else:
        st.info("No MSA-level rows for this occupation.")

st.divider()


# ===== Employment Concentration (Location Quotient) =====
# LQ compares local share vs national share; >1 = more concentrated locally
st.subheader("Employment Concentration")
st.caption(
    "The location quotient (LQ) measures how concentrated an occupation is in a region "
    "compared to the national average. An LQ of 1.0 means the region matches the national "
    "average. Values above 1.0 indicate higher concentration (the job is more common locally), "
    "while values below 1.0 indicate lower concentration."
)
ec_col1, ec_col2 = st.columns(2)

with ec_col1:
    st.markdown("**States with Highest Employment**")
    lq_states = employment_concentration_for_occ(selected_code, level="state", top_n=10)
    if not lq_states.empty:
        fig_lqs = px.bar(
            lq_states.sort_values("LOC_QUOTIENT"),
            x="LOC_QUOTIENT", y="AREA_TITLE", orientation="h",
            labels={"LOC_QUOTIENT": "LQ", "AREA_TITLE": ""}
        )
        st.plotly_chart(fig_lqs, use_container_width=True)

        # Keep only needed columns, rename, and format
        states_emp_view = (
            lq_states[["AREA_TITLE", "LOC_QUOTIENT", "TOT_EMP", "A_MEDIAN"]]
            .rename(columns={
                "AREA_TITLE": "State",
                "LOC_QUOTIENT": "LQ",
                "TOT_EMP": "Employed",
                "A_MEDIAN": "Median Salary"
            })
        )

        # Round LQ (still numeric), add thousands separators to the others
        states_emp_view["LQ"] = states_emp_view["LQ"].round(2)
        states_emp_view["Employed"] = states_emp_view["Employed"].apply(lambda x: f"{x:,.0f}")
        states_emp_view["Median Salary"] = states_emp_view["Median Salary"].apply(lambda x: f"{x:,.0f}")

        st.dataframe(states_emp_view, use_container_width=True, hide_index=True)
    else:
        st.info("No state-level LQ available.")

with ec_col2:
    st.markdown("**Metros with Highest Employment**")
    lq_msas = employment_concentration_for_occ(selected_code, level="msa", top_n=10)
    if not lq_msas.empty:
        fig_lqm = px.bar(
            lq_msas.sort_values("LOC_QUOTIENT"),
            x="LOC_QUOTIENT", y="AREA_TITLE", orientation="h",
            labels={"LOC_QUOTIENT": "LQ", "AREA_TITLE": ""}
        )
        st.plotly_chart(fig_lqm, use_container_width=True)

        # Select, rename, and format
        msas_emp_view = (
            lq_msas[["AREA_TITLE", "LOC_QUOTIENT", "TOT_EMP", "A_MEDIAN"]]
            .rename(columns={
                "AREA_TITLE": "Metro Area",
                "LOC_QUOTIENT": "LQ",
                "TOT_EMP": "Employed",
                "A_MEDIAN": "Median Salary"
            })
        )

        # Keep LQ numeric (rounded), add thousands separators to counts and wages
        msas_emp_view["LQ"] = msas_emp_view["LQ"].round(2)
        msas_emp_view["Employed"] = msas_emp_view["Employed"].apply(lambda x: f"{x:,.0f}")
        msas_emp_view["Median Salary"] = msas_emp_view["Median Salary"].apply(lambda x: f"{x:,.0f}")

        st.dataframe(msas_emp_view, use_container_width=True, hide_index=True)
    else:
        st.info("No MSA-level LQ available.")


st.divider()


# ===== Industry Mix =====
# Which industries employ this occupation nationally (share of total employment)
st.subheader("Industry Mix")
st.caption(
    "This chart highlights the top industries that employ this occupation and the share "
    "each contributes to total national employment. A higher percentage indicates that "
    "a larger portion of workers in this occupation are concentrated in that industry. "
    "This helps illustrate where the occupation is most commonly found across the economy."
)
mix = industry_mix_for_occ(selected_code, top_n=10)
if not mix.empty:
    fig_mix = px.bar(
        mix.sort_values("share_pct"),
        x="share_pct", y="industry", orientation="h",
        labels={"share_pct": "% of Occupation Employment", "industry": "Industry"}
    )
    st.plotly_chart(fig_mix, use_container_width=True)

    # Rename for the table view
    mix_view = mix.rename(
        columns={
            "industry": "Industry",
            "share_pct": "% of Occupation Employment"
        }
    )
    st.dataframe(mix_view, use_container_width=True, hide_index=True)
else:
    st.info("No industry mix rows found for this occupation in the national-by-sector table.")


# ===== Notes / Sources =====
st.markdown(
    """
    ---
    **Notes:**  
    Data are from the **2024 Occupational Employment and Wage Statistics (OEWS)** program,  published by the U.S. Bureau of Labor Statistics (BLS). 
    
    Sources include:  

    • National, state, metropolitan, and nonmetropolitan area data  
    • National industry-specific data  
    • Data by ownership  

    For more details, see the [BLS OEWS homepage](https://www.bls.gov/oes/).
    """,
    unsafe_allow_html=True
)