# ===== Imports =====
import os
import pandas as pd
from functools import lru_cache
import re
from pathlib import Path


# ===== Canonicalization Helpers =====
# Regex for SOC (occupation) code canonicalization
def _canon_soc(x: str):
    if x is None:
        return None
    s = str(x).replace("–", "-").replace("—", "-").strip()
    digits = re.sub(r"[^\d]", "", s)
    if len(digits) == 7:
        return f"{digits[:2]}-{digits[2:]}"
    return s


# ===== File Locations / Config =====
# Default filenames (OEWS 2024 downloads)
DATA_DIR = Path(__file__).parent / "data"  

DEFAULT_FILES = {
    "national": DATA_DIR / "national_M2024_dl.xlsx",
    "state":    DATA_DIR / "state_M2024_dl.xlsx",
    "msa":      DATA_DIR / "MSA_M2024_dl.xlsx",
    "natsector":DATA_DIR / "natsector_M2024_dl.xlsx",
}

# Optional fallback directory 
FALLBACK_DIR = "/mnt/data"


# ===== Path Resolution =====
# Resolve file path with fallback
FALLBACK_DIR = Path("/mnt/data")  # keep if you want the fallback

def _resolve_path(p) -> str:
    p = Path(p)                          # accept Path or str
    if p.is_absolute():
        return str(p) if p.exists() else str(p)  # absolute -> just return (or fail later)

    here = Path.cwd()
    p1 = here / p
    if p1.exists():
        return str(p1)

    if FALLBACK_DIR:
        p2 = FALLBACK_DIR / p.name
        if p2.exists():
            return str(p2)

    return str(p1)   # non-existent; caller will error if missing



# ===== Table Loading & Normalization =====
# Load a formatted table with caching
@lru_cache(maxsize=8)
def load_table(kind: str):
    if kind not in DEFAULT_FILES:
        raise ValueError(f"Unknown table kind: {kind}")
    path = _resolve_path(DEFAULT_FILES[kind])
    df = pd.read_excel(path, engine="openpyxl")

    # Make sure codes are strings (prevents 15-1212 becoming 151212 etc.)
    for c in ["OCC_CODE", "AREA", "AREA_TITLE", "O_GROUP", "NAICS_TITLE"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    # Add a numeric mirror for AREA_TYPE (OEWS: 2=state, 4=MSA)
    if "AREA_TYPE" in df.columns:
        df["AREA_TYPE_NUM"] = pd.to_numeric(df["AREA_TYPE"], errors="coerce")

    # Numeric coercions (some values are '**', '#', '—' etc.)
    numeric_cols = [
        "TOT_EMP", "EMP_PRSE", "JOBS_1000",
        "LOC_QUOTIENT", "LOC_Q",  
        "PCT_TOTAL", "PCT_RPT",
        "H_MEAN", "A_MEAN", "MEAN_PRSE",
        "H_PCT10", "H_PCT25", "H_MEDIAN", "H_PCT75", "H_PCT90",
        "A_PCT10", "A_PCT25", "A_MEDIAN", "A_PCT75", "A_PCT90"
    ]
    
    # Coerce numeric columns
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Create an alias for LOC_Q
    if "LOC_Q" in df.columns and "LOC_QUOTIENT" not in df.columns:
        df["LOC_QUOTIENT"] = df["LOC_Q"]

    # Canonicalized keys for robust filters/joins
    if "OCC_CODE" in df.columns:
        df["SOC_CANON"] = df["OCC_CODE"].apply(_canon_soc)

    # Annual median fallback from hourly median (covers occupations with missing A_MEDIAN)
    if "A_MEDIAN" in df.columns:
        df["A_MEDIAN_ANNUAL"] = df["A_MEDIAN"].copy()
        if "H_MEDIAN" in df.columns:
            needs_fill = df["A_MEDIAN_ANNUAL"].isna() & df["H_MEDIAN"].notna()
            df.loc[needs_fill, "A_MEDIAN_ANNUAL"] = df.loc[needs_fill, "H_MEDIAN"] * 2080.0
    return df


# ===== National Aggregates =====
# U.S. median wage (from national file, "All Occupations" row)
def us_median_wage():
    nat = national_crosswalk()
    # "All Occupations" is commonly OCC_CODE == '00-0000'
    row = nat[nat["OCC_CODE"] == "00-0000"]
    if not row.empty and "A_MEDIAN" in row.columns:
        return float(row.iloc[0]["A_MEDIAN"])
    # Fallback: median of medians (not ideal, but a backup)
    if "A_MEDIAN" in nat.columns:
        return float(nat["A_MEDIAN"].dropna().median())
    return float("nan")


# ===== Lists & Snapshots =====
# Top occupations by national employment
def top_occupations_by_employment(k: int = 10):
    nat = national_crosswalk()
    df = nat.copy()
    df = df[df["OCC_CODE"] != "00-0000"]
    if "TOT_EMP" in df.columns:
        df = df.sort_values("TOT_EMP", ascending=False)
    return df[["OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN", "A_MEAN"]].head(k)

# Full occupation list, alphabetically by title
def occupation_list_az():
    nat = national_crosswalk().copy()
    nat = nat[nat["OCC_CODE"] != "00-0000"]
    return nat.drop_duplicates(subset=["OCC_CODE", "OCC_TITLE"]).sort_values("OCC_TITLE")

# Snapshot summary for an occupation
def snapshot_for_occ(occ_code: str):
    nat = national_crosswalk()
    row = nat[nat["OCC_CODE"] == occ_code]
    if row.empty:
        return {}
    row = row.iloc[0]
    us_med = us_median_wage()
    snap = {
        "OCC_CODE": occ_code,
        "OCC_TITLE": row.get("OCC_TITLE", ""),
        "Median annual wage (A_MEDIAN)": row.get("A_MEDIAN", float("nan")),
        "Wage range P10–P90 (A_PCT10–A_PCT90)": (row.get("A_PCT10", float("nan")), row.get("A_PCT90", float("nan"))),
        "Mean wage (A_MEAN)": row.get("A_MEAN", float("nan")),
        "Employment size (TOT_EMP)": row.get("TOT_EMP", float("nan")),
        "Relative wage multiplier (A_MEDIAN / US median)": (float(row.get("A_MEDIAN"))/us_med) if (pd.notna(row.get("A_MEDIAN")) and pd.notna(us_med) and us_med>0) else float("nan"),
    }
    return snap

# Wage distribution series for an occupation (P10, P25, P50, P75, P90)
def wage_distribution_for_occ(occ_code: str):
    nat = national_crosswalk()
    row = nat[nat["OCC_CODE"] == occ_code]
    if row.empty:
        return pd.Series(dtype=float)
    row = row.iloc[0]
    data = {
        "P10": row.get("A_PCT10", float("nan")),
        "P25": row.get("A_PCT25", float("nan")),
        "P50": row.get("A_MEDIAN", float("nan")),
        "P75": row.get("A_PCT75", float("nan")),
        "P90": row.get("A_PCT90", float("nan")),
    }
    return pd.Series(data)


# ===== Geography Queries: Top Median Wages =====
# Top geographies by median wage for an occupation
def top_geographies_for_occ(occ_code: str, level: str = "state", top_n: int = 10):
    # Load the correct table and normalize the code
    df = load_table("state" if level == "state" else "msa").copy()
    code = _canon_soc(occ_code)

    # SOC filter
    if "SOC_CANON" in df.columns:
        sub = df.loc[df["SOC_CANON"] == code].copy()
    else:
        sub = df.loc[df["OCC_CODE"].apply(_canon_soc) == code].copy()
    if sub.empty:
        return pd.DataFrame(columns=["AREA_TITLE", "A_MEDIAN", "TOT_EMP", "LOC_QUOTIENT"])

    # Filter by geography level (state vs. MSA)
    if "AREA_TYPE_NUM" in sub.columns and sub["AREA_TYPE_NUM"].notna().any():
        target = 2 if level == "state" else 4
        sub = sub.loc[sub["AREA_TYPE_NUM"] == target].copy()
    elif "AREA_TYPE" in sub.columns:
        atl = sub["AREA_TYPE"].astype(str).str.lower()
        if level == "state":
            sub = sub.loc[atl.str.contains("state", na=False)]
        else:
            sub = sub.loc[
                atl.str.contains("metro", na=False)
                | atl.str.contains("metropolitan", na=False)
                | atl.str.contains("micro", na=False)
                | atl.str.contains("nonmetro", na=False)
            ]
    if sub.empty:
        return pd.DataFrame(columns=["AREA_TITLE", "A_MEDIAN", "TOT_EMP", "LOC_QUOTIENT"])

    # Choose a usable wage column
    wage_col = "A_MEDIAN_ANNUAL" if "A_MEDIAN_ANNUAL" in sub.columns else ("A_MEDIAN" if "A_MEDIAN" in sub.columns else None)
    if wage_col is None and "H_MEDIAN" in sub.columns:
        sub["A_MEDIAN_TMP"] = pd.to_numeric(sub["H_MEDIAN"], errors="coerce") * 2080.0
        wage_col = "A_MEDIAN_TMP"
    if wage_col is None:
        return pd.DataFrame(columns=["AREA_TITLE", "A_MEDIAN", "TOT_EMP", "LOC_QUOTIENT"])

    # Clean and sort by wage descending
    sub[wage_col] = pd.to_numeric(sub[wage_col], errors="coerce")
    sub = sub.dropna(subset=[wage_col]).sort_values(wage_col, ascending=False)

    # Select output columns
    cols = ["AREA_TITLE", wage_col]
    if "TOT_EMP" in sub.columns: cols.append("TOT_EMP")
    if "LOC_QUOTIENT" in sub.columns: cols.append("LOC_QUOTIENT")

    # Return top geographies, rename col for consistency
    out = sub[cols].head(top_n).copy().rename(columns={wage_col: "A_MEDIAN"})
    out.reset_index(drop=True, inplace=True)
    return out


# ===== Geography Queries: Employment Concentration (LQ) =====
# Top geographies by employment concentration (location quotient) for an occupation
def employment_concentration_for_occ(occ_code: str, level: str = "state", top_n: int = 10):
    # Load the correct table: state-level or MSA-level
    df = load_table("state" if level == "state" else "msa").copy()

    # Return an empty DataFrame with consistent columns
    def _empty():
        return pd.DataFrame(columns=["AREA_TITLE", "LOC_QUOTIENT", "TOT_EMP", "A_MEDIAN"])

    # Normalize the SOC code
    code = _canon_soc(occ_code)

    # Filter by SOC code
    if "SOC_CANON" in df.columns:
        sub = df.loc[df["SOC_CANON"] == code].copy()
    elif "OCC_CODE" in df.columns:
        sub = df.loc[df["OCC_CODE"].apply(_canon_soc) == code].copy()
    else:
        return _empty()
    if sub.empty:
        return _empty()

    # Filter by geography level (state vs. MSA)
    if "AREA_TYPE_NUM" in sub.columns and sub["AREA_TYPE_NUM"].notna().any():
        target = 2 if level == "state" else 4
        sub = sub.loc[sub["AREA_TYPE_NUM"] == target].copy()
    elif "AREA_TYPE" in sub.columns:
        atl = sub["AREA_TYPE"].astype(str).str.lower()
        if level == "state":
            sub = sub.loc[atl.str.contains("state", na=False)]
        else:
            sub = sub.loc[
                atl.str.contains("metro", na=False)
                | atl.str.contains("metropolitan", na=False)
                | atl.str.contains("micro", na=False)
                | atl.str.contains("nonmetro", na=False)
            ]
    if sub.empty:
        return _empty()

    # Ensure usable LQ column
    if "LOC_QUOTIENT" not in sub.columns and "LOC_Q" in sub.columns:
        sub["LOC_QUOTIENT"] = pd.to_numeric(sub["LOC_Q"], errors="coerce")
    if "LOC_QUOTIENT" in sub.columns:
        sub["LOC_QUOTIENT"] = pd.to_numeric(sub["LOC_QUOTIENT"], errors="coerce")

    # If no LQ, approximte it from JOBS_1000 values
    if "LOC_QUOTIENT" not in sub.columns or sub["LOC_QUOTIENT"].isna().all():
        nat = national_crosswalk()
        if "SOC_CANON" not in nat.columns:
            nat = nat.copy(); nat["SOC_CANON"] = nat["OCC_CODE"].apply(_canon_soc)
        nat_row = nat.loc[nat["SOC_CANON"] == code]
        nat_jobs1000 = pd.to_numeric(nat_row["JOBS_1000"], errors="coerce").iloc[0] if ("JOBS_1000" in nat.columns and not nat_row.empty) else float("nan")
        if pd.notna(nat_jobs1000) and nat_jobs1000 > 0 and "JOBS_1000" in sub.columns:
            sub["LOC_QUOTIENT"] = pd.to_numeric(sub["JOBS_1000"], errors="coerce") / float(nat_jobs1000)

    # If still no LQ, return empty
    if "LOC_QUOTIENT" not in sub.columns:
        return _empty()

    # Clean + sort by LQ descending
    sub["LOC_QUOTIENT"] = pd.to_numeric(sub["LOC_QUOTIENT"], errors="coerce")
    sub = sub.dropna(subset=["LOC_QUOTIENT"]).sort_values("LOC_QUOTIENT", ascending=False)

    # Add wage context
    wage_col = "A_MEDIAN_ANNUAL" if "A_MEDIAN_ANNUAL" in sub.columns else ("A_MEDIAN" if "A_MEDIAN" in sub.columns else None)
    if wage_col is None and "H_MEDIAN" in sub.columns:
        sub["A_MEDIAN_TMP"] = pd.to_numeric(sub["H_MEDIAN"], errors="coerce") * 2080.0
        wage_col = "A_MEDIAN_TMP"

    # Select output columns
    out_cols = ["AREA_TITLE", "LOC_QUOTIENT"]
    if "TOT_EMP" in sub.columns: out_cols.append("TOT_EMP")
    if wage_col: out_cols.append(wage_col)

    # Slice down, rename wage column to "A_MEDIAN" for consistency
    out = sub[out_cols].head(top_n).copy()
    if wage_col and wage_col != "A_MEDIAN":
        out = out.rename(columns={wage_col: "A_MEDIAN"})
    out.reset_index(drop=True, inplace=True)
    return out


# ===== Industry Mix =====
# Industry mix for an occupation
def industry_mix_for_occ(occ_code: str, top_n: int = 10):
    df = load_table("natsector").copy()
    sub = df[df["OCC_CODE"] == occ_code].copy()
    if sub.empty:
        return sub
    if "PCT_TOTAL" in sub.columns and sub["PCT_TOTAL"].notna().any():
        sub["share_pct"] = sub["PCT_TOTAL"]
    else:
        # Fallback compute share from TOT_EMP within this occupation
        if "TOT_EMP" in sub.columns and sub["TOT_EMP"].notna().any():
            tot = sub["TOT_EMP"].sum(skipna=True)
            sub["share_pct"] = (sub["TOT_EMP"] / tot) * 100.0 if tot else 0.0
        else:
            sub["share_pct"] = float("nan")
    # Clean industry labels
    if "NAICS_TITLE" in sub.columns:
        sub["industry"] = sub["NAICS_TITLE"].str.replace("Sector: ", "", regex=False)
    else:
        sub["industry"] = sub.get("NAICS", "").astype(str)
    return sub.sort_values("share_pct", ascending=False)[["industry", "share_pct"]].head(top_n)


# ===== Crosswalk Cache =====
# Cached national crosswalk with canonical SOC codes and filtered groups
@lru_cache(maxsize=1)
def national_crosswalk():
    nat = load_table("national")
    if "SOC_CANON" not in nat.columns and "OCC_CODE" in nat.columns:
        nat["SOC_CANON"] = nat["OCC_CODE"].apply(_canon_soc)
    if "O_GROUP" in nat.columns:
        nat = nat[nat["O_GROUP"].isin(["detailed", "broad", "total"])].copy()
    return nat