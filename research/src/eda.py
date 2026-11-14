"""Module B: Exploratory Data Analysis. Every function returns a matplotlib Figure."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from .config import LABELS, TARGET
from .plot_utils import save_fig

sns.set_theme(style="whitegrid")
GREEN = "#2e8b57"

EXPLANATIONS = {
    "eda_distributions": "Most country-years have a low renewable share, with a long tail of countries that depend heavily on renewables (often biomass/hydro in low-income countries).",
    "eda_share_by_country": "Renewable share varies hugely between countries. Left: how many countries fall into each share band. Right: highest and lowest countries in the chosen year.",
    "eda_access_vs_renewable": "Countries with low electricity access tend to have a HIGH renewable share, mainly traditional biomass. High renewable share therefore does not automatically mean modern clean energy.",
    "eda_co2_vs_renewable": "CO2 emissions are plotted on a log axis. Large emitters mostly have modest renewable shares, but the relationship is weak because emissions also depend on country size.",
    "eda_trends": "Left: the global average share is drifting down or flat when averaged across countries. Right: selected countries show very different trajectories.",
    "eda_correlation": "Red = positive correlation, blue = negative. Look for features that move together (e.g. GDP per capita and clean cooking access) and those related to renewable share.",
    "eda_top10": "Top 10 countries by average renewable share over the most recent years in the data.",
    "eda_country_compare": "Side-by-side comparison of selected countries (latest available year) on key sustainability indicators.",
}


def _pick(df, cols):
    return [c for c in cols if c in df.columns]


def plot_distributions(df):
    cols = _pick(df, ["renewable_share", "low_carbon_elec_pct", "renewables_primary_pct",
                      "elec_renewable_twh"])
    fig, axes = plt.subplots(1, len(cols), figsize=(4.5 * len(cols), 4))
    axes = np.atleast_1d(axes)
    for ax, col in zip(axes, cols):
        data = df[col].dropna()
        if col == "elec_renewable_twh":
            data = np.log1p(data.clip(lower=0))
            ax.set_xlabel("log(1 + TWh)")
        else:
            ax.set_xlabel(LABELS.get(col, col), fontsize=8)
        sns.histplot(data, bins=30, kde=True, color=GREEN, ax=ax)
        ax.set_title(col.replace("_", " ").title(), fontsize=10)
    fig.suptitle("Distribution of renewable energy indicators", y=1.02)
    fig.tight_layout()
    return fig


def plot_share_by_country(df, year=None):
    year = year or int(df.year.max())
    snap = df[df.year == year].dropna(subset=[TARGET])
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    sns.histplot(snap[TARGET], bins=20, color=GREEN, ax=axes[0])
    axes[0].set(title=f"Countries by renewable share band ({year})",
                xlabel="Renewable share (%)", ylabel="Number of countries")
    ranked = snap.sort_values(TARGET)
    sel = pd.concat([ranked.head(8), ranked.tail(8)])
    colors = ["#c0392b"] * min(8, len(ranked.head(8))) + [GREEN] * min(8, len(ranked.tail(8)))
    axes[1].barh(sel.country, sel[TARGET], color=colors)
    axes[1].set(title=f"Lowest 8 (red) and highest 8 (green), {year}", xlabel="Renewable share (%)")
    fig.tight_layout()
    return fig


def plot_access_vs_renewable(df):
    fig, ax = plt.subplots(figsize=(8, 5.5))
    d = df.dropna(subset=["electricity_access", TARGET])
    sc = ax.scatter(d.electricity_access, d[TARGET], c=d.year, cmap="viridis", s=14, alpha=.7)
    fig.colorbar(sc, ax=ax, label="Year")
    ax.set(title="Electricity access vs renewable energy share",
           xlabel=LABELS["electricity_access"], ylabel=LABELS[TARGET])
    fig.tight_layout()
    return fig


def plot_co2_vs_renewable(df):
    d = df.dropna(subset=["co2_kt", TARGET])
    d = d[d.co2_kt > 0]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.scatter(d.co2_kt, d[TARGET], s=12, alpha=.5, color="#8e44ad", label="country-year")
    ax.set_xscale("log")
    ax.set(title="CO2 emissions vs renewable energy share", xlabel="CO2 emissions (kt, log scale)",
           ylabel=LABELS[TARGET])
    ax.legend()
    fig.tight_layout()
    return fig


def plot_trends(df, countries=None):
    countries = countries or [c for c in ["India", "China", "United States", "Brazil", "Germany",
                                          "Nigeria"] if c in set(df.country)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    g = df.groupby("year")[TARGET].agg(["mean", "median"])
    axes[0].plot(g.index, g["mean"], marker="o", color=GREEN, label="Mean across countries")
    axes[0].plot(g.index, g["median"], marker="s", color="#e67e22", label="Median across countries")
    axes[0].set(title="Global renewable share over time", xlabel="Year", ylabel="Share (%)")
    axes[0].legend()
    for c in countries:
        s = df[df.country == c].sort_values("year")
        axes[1].plot(s.year, s[TARGET], label=c)
    axes[1].set(title="Selected countries", xlabel="Year", ylabel="Share (%)")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    return fig


def plot_correlation(df):
    num = df.select_dtypes("number").drop(columns=["year"], errors="ignore")
    fig, ax = plt.subplots(figsize=(11, 9))
    sns.heatmap(num.corr(), cmap="coolwarm", center=0, annot=True, fmt=".2f",
                annot_kws={"size": 6}, ax=ax)
    ax.set_title("Correlation heatmap of numerical features")
    fig.tight_layout()
    return fig


def top_countries(df, n=10, last_years=5):
    recent = df[df.year > df.year.max() - last_years]
    return (recent.groupby("country")[TARGET].mean().dropna().sort_values(ascending=False)
            .head(n).round(2).reset_index(name="avg_renewable_share_pct"))


def plot_top10(df, last_years=5):
    t = top_countries(df, 10, last_years)
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=t, y="country", x="avg_renewable_share_pct", color=GREEN, ax=ax)
    ax.set(title=f"Top 10 countries by renewable share (avg last {last_years} years)",
           xlabel="Average renewable share (%)", ylabel="")
    fig.tight_layout()
    return fig


def plot_country_compare(df, countries=None):
    countries = countries or [c for c in ["India", "China", "United States", "Brazil", "Germany"]
                              if c in set(df.country)]
    metrics = _pick(df, [TARGET, "electricity_access", "clean_cooking_access", "low_carbon_elec_pct"])
    rows = []
    for c in countries:
        s = df[df.country == c].sort_values("year")
        if len(s):
            rows.append(s.ffill().iloc[-1][metrics].rename(c))
    comp = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(10, 5))
    comp.plot(kind="bar", ax=ax, width=.8)
    ax.set(title="Country sustainability comparison (latest year)", ylabel="Percent", xlabel="")
    ax.legend([LABELS[m].split("(")[0].strip() for m in metrics], fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=0)
    fig.tight_layout()
    return fig


ALL_PLOTS = {
    "eda_distributions": plot_distributions, "eda_share_by_country": plot_share_by_country,
    "eda_access_vs_renewable": plot_access_vs_renewable, "eda_co2_vs_renewable": plot_co2_vs_renewable,
    "eda_trends": plot_trends, "eda_correlation": plot_correlation, "eda_top10": plot_top10,
    "eda_country_compare": plot_country_compare,
}


def run_eda(df):
    """Create and save all EDA charts. Returns {name: path}."""
    paths = {}
    for name, fn in ALL_PLOTS.items():
        try:
            paths[name] = str(save_fig(fn(df), name))
        except KeyError as exc:  # a needed column is missing in a user-supplied file
            print(f"[EDA] skipped {name}: missing column {exc}")
    return paths
