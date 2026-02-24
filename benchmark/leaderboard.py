#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import Dict


def _require_streamlit():
    try:
        import streamlit as st  # type: ignore

        return st
    except Exception as exc:
        raise SystemExit("streamlit is required: pip install streamlit plotly pandas") from exc


def _require_plotly():
    try:
        import plotly.express as px  # type: ignore
        import plotly.graph_objects as go  # type: ignore

        return px, go
    except Exception as exc:
        raise SystemExit("plotly is required: pip install plotly") from exc


def _load_parquet(path: str):
    try:
        import pandas as pd  # type: ignore

        return pd.read_parquet(path)
    except Exception as exc:
        raise SystemExit("pandas is required: pip install pandas pyarrow") from exc


def _top_level_map(case_df) -> Dict[str, str]:
    mapping = {}
    for _, row in case_df.iterrows():
        cat = row.get("vcfcst_category", {})
        if isinstance(cat, dict):
            mapping[row.get("case_id")] = cat.get("level1", "")
    return mapping


def main():
    ap = argparse.ArgumentParser(description="VC-FCST Benchmark Leaderboard")
    ap.add_argument("--results", default="runs/benchmark_results.parquet")
    ap.add_argument("--case-bank", default="datasets/case_bank.parquet")
    args = ap.parse_args()

    st = _require_streamlit()
    px, go = _require_plotly()

    results = _load_parquet(args.results)
    case_bank = _load_parquet(args.case_bank) if Path(args.case_bank).exists() else None

    st.title("VC-FCST Benchmark Leaderboard")

    if results.empty:
        st.warning("No results found.")
        return

    if case_bank is not None:
        level1_map = _top_level_map(case_bank)
        results = results.copy()
        results["level1"] = results["case_id"].map(level1_map)
    else:
        results["level1"] = ""

    overall = results.groupby("agent_name").agg(
        total_cases=("case_id", "count"),
        passed=("passed", "sum"),
        avg_duration=("duration_sec", "mean"),
    )
    overall["pass_rate"] = overall["passed"] / overall["total_cases"] * 100
    overall = overall.sort_values("pass_rate", ascending=False).reset_index()

    st.subheader("Overall Ranking")
    st.dataframe(overall, use_container_width=True)

    st.subheader("Top-Level Category Radar")
    if results["level1"].nunique() > 1:
        radar = results.groupby(["agent_name", "level1"]).agg(pass_rate=("passed", "mean")).reset_index()
        fig = go.Figure()
        for agent in radar["agent_name"].unique():
            sub = radar[radar["agent_name"] == agent]
            fig.add_trace(
                go.Scatterpolar(r=sub["pass_rate"] * 100, theta=sub["level1"], fill="toself", name=agent)
            )
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Top-level category data not available.")

    st.subheader("Category Detail")
    category_stats = results.groupby(["agent_name", "category_id"]).agg(pass_rate=("passed", "mean")).reset_index()
    fig = px.bar(category_stats, x="agent_name", y="pass_rate", color="category_id", barmode="group")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Case Detail")
    st.dataframe(results, use_container_width=True)


if __name__ == "__main__":
    raise SystemExit(main())
