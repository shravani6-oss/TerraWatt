"""Modules E and F: K-Means and Gaussian Mixture clustering of countries."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from .config import CLUSTER_FEATURES, CLUSTER_LAST_YEARS, CLUSTER_LOG, LABELS, RANDOM_STATE
from .plot_utils import save_fig


def build_country_table(df, features=None, last_years=CLUSTER_LAST_YEARS):
    """One row per country: mean of each indicator over the most recent years."""
    features = [f for f in (features or CLUSTER_FEATURES) if f in df.columns]
    recent = df[df.year > df.year.max() - last_years]
    table = recent.groupby("country")[features].mean()
    table = table.dropna(thresh=max(3, len(features) - 2))   # drop countries with almost no data
    return table, features


def prepare_matrix(table, features):
    """Median-impute, log-transform skewed columns, then standardise (original table untouched)."""
    X = pd.DataFrame(SimpleImputer(strategy="median").fit_transform(table), index=table.index,
                     columns=features)
    for c in CLUSTER_LOG:
        if c in X:
            X[c] = np.log1p(X[c].clip(lower=0))
    scaler = StandardScaler().fit(X)
    return scaler.transform(X), scaler, X


def k_selection(X, k_max=12):
    ks = list(range(1, min(k_max, len(X) - 1) + 1))
    inertia, sil = [], {}
    for k in ks:
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(X)
        inertia.append(km.inertia_)
        if k >= 2:
            sil[k] = silhouette_score(X, km.labels_)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].plot(ks, inertia, "o-", color="#2e8b57")
    axes[0].set(title="Elbow method", xlabel="Number of clusters K", ylabel="Inertia (within-cluster SSE)")
    axes[1].plot(list(sil), list(sil.values()), "s-", color="#e67e22")
    axes[1].set(title="Silhouette score", xlabel="Number of clusters K", ylabel="Silhouette")
    fig.tight_layout(); save_fig(fig, "km_elbow_silhouette")
    return ks, inertia, sil


def choose_k(sil, low=3, high=6):
    """Highest silhouette among K=3..6. K=2 usually wins silhouette but is too coarse to be
    useful for high/medium/low profiling, so it is excluded (documented in the report)."""
    cand = {k: v for k, v in sil.items() if low <= k <= high}
    return max(cand, key=cand.get) if cand else max(sil, key=sil.get)


def label_clusters(profile, col="renewable_share"):
    """High/Medium/Low from the measured mean renewable share of each cluster (rank terciles)."""
    order = profile[col].sort_values().index.tolist()
    n = len(order)
    labels = {}
    for rank, cid in enumerate(order):
        tier = "Low" if rank < n / 3 else ("High" if rank >= n - n / 3 else "Medium")
        labels[cid] = f"{tier} renewable adoption (mean {profile.loc[cid, col]:.1f}%)"
    return labels


def priority_countries(table, n=10):
    """Intervention-priority score: average percentile rank across 5 deficits.
    Higher score = bigger gap: low renewable share, low electricity access, low clean cooking
    access, low low-carbon electricity, high energy intensity (wasteful energy use)."""
    pieces = {}
    for col, higher_is_worse in [("renewable_share", False), ("electricity_access", False),
                                 ("clean_cooking_access", False), ("low_carbon_elec_pct", False),
                                 ("energy_intensity", True)]:
        if col in table:
            r = table[col].rank(pct=True)
            pieces[col] = r if higher_is_worse else 1 - r
    score = pd.DataFrame(pieces).mean(axis=1).rename("priority_score")
    out = table.join(score).sort_values("priority_score", ascending=False).head(n)
    return out.round(2)


def run_kmeans(df):
    table, features = build_country_table(df)
    X, scaler, X_log = prepare_matrix(table, features)
    ks, inertia, sil = k_selection(X)
    k = choose_k(sil)
    km = KMeans(n_clusters=k, n_init=20, random_state=RANDOM_STATE).fit(X)
    table = table.assign(cluster=km.labels_)
    profile = table.groupby("cluster")[features].mean().round(2)       # original units
    profile["n_countries"] = table.groupby("cluster").size()
    names = label_clusters(profile)
    table["cluster_label"] = table.cluster.map(names)
    centroids = pd.DataFrame(km.cluster_centers_, columns=features).round(3)  # standardised space
    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    pcs = pca.fit_transform(X)
    table["pc1"], table["pc2"] = pcs[:, 0], pcs[:, 1]

    palette = sns.color_palette("Set2", k)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for cid in range(k):
        m = table.cluster == cid
        axes[0].scatter(table.loc[m, "clean_cooking_access"], table.loc[m, "renewable_share"],
                        color=palette[cid], s=35, label=f"C{cid}: {names[cid].split(' (')[0]}")
        axes[1].scatter(table.loc[m, "pc1"], table.loc[m, "pc2"], color=palette[cid], s=35, label=f"C{cid}")
    axes[0].set(title="Clusters: clean-cooking access vs renewable share",
                xlabel=LABELS["clean_cooking_access"], ylabel=LABELS["renewable_share"])
    axes[1].set(title=f"PCA view ({pca.explained_variance_ratio_.sum():.0%} of variance in 2 components)",
                xlabel="PC1", ylabel="PC2")
    axes[0].legend(fontsize=8); axes[1].legend(fontsize=8)
    fig.tight_layout(); save_fig(fig, "km_clusters")

    priority = priority_countries(table[features])
    priority = priority.join(table[["cluster_label"]])
    return {"table": table, "features": features, "profile": profile, "labels": names,
            "centroids_standardised": centroids, "k": k, "ks": ks, "inertia": inertia,
            "silhouette": sil, "priority": priority, "X": X, "pca": pca, "model": km,
            "scaler": scaler, "silhouette_chosen": sil[k]}


def run_gmm(km_res):
    X, table, features = km_res["X"], km_res["table"], km_res["features"]
    rows, models = [], {}
    for n in (3, 4, 5):
        if n >= len(X):
            continue
        g = GaussianMixture(n_components=n, covariance_type="full", n_init=5, random_state=RANDOM_STATE).fit(X)
        lab = g.predict(X)
        rows.append({"Components": n, "BIC": g.bic(X), "AIC": g.aic(X),
                     "Silhouette": silhouette_score(X, lab) if len(set(lab)) > 1 else np.nan})
        models[n] = g
    comp = pd.DataFrame(rows).round(3)
    best_n = int(comp.sort_values("BIC").iloc[0]["Components"])
    g = models[best_n]
    probs = g.predict_proba(X)
    labels = g.predict(X)
    km_labels = km_res["model"].labels_
    summary = {"best_n_by_bic": best_n, "ARI_vs_kmeans": adjusted_rand_score(km_labels, labels),
               "kmeans_silhouette": km_res["silhouette_chosen"],
               "gmm_silhouette": float(comp.loc[comp.Components == best_n, "Silhouette"].iloc[0])}
    gtable = table[["pc1", "pc2"]].copy()
    gtable["gmm_cluster"] = labels
    gtable["max_probability"] = probs.max(axis=1).round(3)
    prob_df = pd.DataFrame(probs, index=table.index, columns=[f"P(comp {i})" for i in range(best_n)]).round(3)
    gtable = gtable.join(prob_df)
    gtable["kmeans_cluster"] = km_labels
    # plots
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    axes[0].plot(comp.Components, comp.BIC, "o-", label="BIC"); axes[0].plot(comp.Components, comp.AIC, "s-", label="AIC")
    axes[0].set(title="GMM model selection (lower = better)", xlabel="Components"); axes[0].legend()
    sc = axes[1].scatter(gtable.pc1, gtable.pc2, c=gtable.gmm_cluster, cmap="Set2", s=40)
    axes[1].set(title=f"GMM clusters ({best_n} components), PCA view", xlabel="PC1", ylabel="PC2")
    sc2 = axes[2].scatter(gtable.pc1, gtable.pc2, c=gtable.max_probability, cmap="viridis", s=40)
    fig.colorbar(sc2, ax=axes[2], label="Highest membership probability")
    axes[2].set(title="Soft clustering: confidence per country", xlabel="PC1", ylabel="PC2")
    fig.tight_layout(); save_fig(fig, "gmm_overview")
    uncertain = gtable.sort_values("max_probability").head(25)
    fig, ax = plt.subplots(figsize=(8, 8))
    sns.heatmap(uncertain[list(prob_df.columns)], annot=True, fmt=".2f", cmap="Greens", ax=ax)
    ax.set(title="Membership probabilities of the 25 least certain countries")
    fig.tight_layout(); save_fig(fig, "gmm_soft_membership")
    return {"comparison": comp, "summary": summary, "assignments": gtable, "best_n": best_n, "model": g}
