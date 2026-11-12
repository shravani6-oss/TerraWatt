"""GreenAI - runs the COMPLETE workflow (modules A-G, I) and saves models, plots and results.

Usage:  python train.py                      (uses the CSV in the data/ folder)
        python train.py --data path/to/file.csv
"""
import argparse
import time
import warnings
import numpy as np
import pandas as pd

from src import eda
from src.classification import class_balance, evaluate_classifier, make_classification_data, run_classification
from src.clustering import run_gmm, run_kmeans
from src.config import (CLUSTER_LAST_YEARS, LEAKY_COLUMNS, MAX_MISSING_FRACTION, MODEL_FEATURES,
                        MODELS_DIR, PLOTS_DIR, RESULTS_DIR, TARGET)
from src.data_utils import available_features, drop_sparse_columns, load_dataset
from src.evaluation import (cross_validate_ensembles, feature_importance_plots, final_confusion_plot,
                            final_evaluation, regression_cv, tune_random_forest)
from src.model_io import save_json, save_model
from src.plot_utils import save_fig
from src.preprocessing import (build_preprocessor, inspect_dataset, label_encoding_demo,
                               missing_summary, onehot_demo, plot_missing_bar, plot_missing_heatmap,
                               scaling_demo)
from src.regression import run_regression
from src.report import build_report

warnings.filterwarnings("ignore")


def step(msg):
    print(f"\n=== {msg} ===", flush=True)


def main(data_path=None):
    t0 = time.time()
    for d in (MODELS_DIR, PLOTS_DIR, RESULTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    S = {}

    # ---------------- Module A ----------------
    step("Module A: loading and preprocessing")
    df, cleaning = load_dataset(data_path)
    S.update(cleaning=cleaning, n_rows=len(df), n_countries=df.country.nunique(),
             year_min=int(df.year.min()), year_max=int(df.year.max()), last_years=CLUSTER_LAST_YEARS)
    overview = inspect_dataset(df)
    (RESULTS_DIR / "data_overview.txt").write_text(overview, encoding="utf-8")
    print(overview[:1500], "...\n(full overview saved to results/data_overview.txt)")
    before = missing_summary(df)
    before.to_csv(RESULTS_DIR / "missing_before.csv")
    save_fig(plot_missing_heatmap(df), "missing_heatmap")
    save_fig(plot_missing_bar(df), "missing_bar")
    df_model, dropped = drop_sparse_columns(df, MAX_MISSING_FRACTION, protect=["country", "year", TARGET])
    S["dropped_cols"] = dropped
    S["leaky"] = [c for c in LEAKY_COLUMNS if c in df.columns]
    print("Dropped (>50% missing):", dropped)
    scaling_demo(df).to_csv(RESULTS_DIR / "scaling_demo.csv")
    onehot_demo(df).to_csv(RESULTS_DIR / "onehot_demo.csv")
    print("Label encoding demo (target labels only):", {str(k): v for k, v in label_encoding_demo(["Low", "High", "Low"]).items()})

    features = available_features(df_model, MODEL_FEATURES)
    if TARGET not in df_model or len(features) < 3:
        raise SystemExit("Not enough usable columns in this CSV to train models.")
    S["n_missing_target"] = int(df_model[TARGET].isna().sum())
    print("Model features:", features)

    # ---------------- Module B ----------------
    step("Module B: exploratory data analysis")
    eda.run_eda(df_model)
    eda.top_countries(df_model).to_csv(RESULTS_DIR / "top10_countries.csv", index=False)

    # ---------------- Module C ----------------
    step("Module C: regression")
    reg = run_regression(df_model, features)
    S["reg"] = reg
    reg["table"].to_csv(RESULTS_DIR / "regression_results.csv", index=False)
    reg["sample_predictions"].to_csv(RESULTS_DIR / "regression_sample_predictions.csv", index=False)
    print(reg["table"].to_string(index=False))
    train_r = reg["train"]
    reg_meta = {"features": features + ["year"], "target": TARGET, "train_years_max": reg["cutoff_year"],
                "defaults": train_r[features + ["year"]].median().round(4).to_dict(),
                "ranges": {c: [float(train_r[c].min()), float(train_r[c].max())] for c in features + ["year"]},
                "metrics": reg["table"].set_index("Model").to_dict("index")}
    save_model(reg["models"]["Simple Linear Regression"], "regression_simple",
               {**reg_meta, "features": [reg["simple_feature"]]})
    save_model(reg["models"]["Multiple Linear Regression"], "regression_multiple", reg_meta)
    cat_meta = {**reg_meta, "features": features + ["year", "country"],
                "countries": sorted(train_r.country.unique().tolist())}
    save_model(reg["models"]["Multiple LR + country (one-hot)"], "regression_multiple_country", cat_meta)

    # ---------------- Module D ----------------
    step("Module D: classification")
    data = make_classification_data(df_model, features)
    print("Threshold (train median):", round(data["threshold"], 2))
    print("Train balance:", class_balance(data["y_train"]), "| Test balance:", class_balance(data["y_test"]))
    clf = run_classification(data)
    S["clf"] = clf
    clf["table"].to_csv(RESULTS_DIR / "classification_results.csv", index=False)
    print(clf["table"].to_string(index=False))

    # ---------------- Module G ----------------
    step("Module G: cross-validation, tuning, final evaluation")
    cv_table = cross_validate_ensembles(data, clf["imbalanced"])
    cv_table.to_csv(RESULTS_DIR / "cv_ensembles.csv", index=False)
    S["cv_table"] = cv_table
    reg_cv = regression_cv(reg["train"], features)
    reg_cv.to_csv(RESULTS_DIR / "regression_cv.csv", index=False)
    S["reg_cv"] = reg_cv
    print(cv_table.to_string(index=False)); print(reg_cv.to_string(index=False))
    searches, tuning_table = tune_random_forest(data, clf["imbalanced"])
    tuning_table.to_csv(RESULTS_DIR / "tuning_results.csv", index=False)
    S["tuning_table"] = tuning_table
    print(tuning_table.drop(columns="Best parameters").to_string(index=False))
    best_search = max(searches.values(), key=lambda v: v["search"].best_score_)["search"]

    candidates = dict(clf["models"])
    cv_scores = final_evaluation(data, candidates)
    cv_scores["Tuned Random Forest"] = best_search.best_score_
    candidates["Tuned Random Forest"] = best_search.best_estimator_
    final_name = max(cv_scores, key=cv_scores.get)
    final_model = candidates[final_name]
    final_metrics = evaluate_classifier(final_model, data["X_test"], data["y_test"])
    cm = final_metrics.pop("confusion_matrix")
    final_confusion_plot(cm, final_name)
    S.update(final_name=final_name, final_metrics=final_metrics, cv_scores=cv_scores)
    print("CV F1 used for selection:", {k: round(v, 4) for k, v in cv_scores.items()})
    print(f"FINAL MODEL: {final_name} -> test metrics {({k: round(v, 4) for k, v in final_metrics.items()})}")
    importance = feature_importance_plots(final_model, data, "", f"- {final_name}")
    S["top_features"] = importance["permutation"].head(5).index.tolist()
    importance["permutation"].rename("importance").to_csv(RESULTS_DIR / "feature_importance_permutation.csv")
    # Tree-based importances come from the tuned Random Forest (logistic regression has none)
    rf_imp = feature_importance_plots(best_search.best_estimator_, data, "_rf", "- Tuned Random Forest")
    rf_imp["impurity"].rename("importance").to_csv(RESULTS_DIR / "feature_importance_impurity.csv")
    rf_test = evaluate_classifier(best_search.best_estimator_, data["X_test"], data["y_test"])
    S["tuned_rf_test"] = {k: v for k, v in rf_test.items() if k != "confusion_matrix"}
    save_model(best_search.best_estimator_, "classifier_tuned_rf", {"model_name": "Tuned Random Forest"})
    save_json({"final_model": final_name, "cv_f1": cv_scores, "test_metrics": final_metrics,
               "confusion_matrix": cm, "confusion_matrices_all": clf["confusion_matrices"],
               "tuned_rf_test_metrics": S["tuned_rf_test"], "best_params": best_search.best_params_,
               "threshold": data["threshold"], "class_balance_train": clf["balance"],
               "class_balance_test": class_balance(data["y_test"])}, "final_evaluation.json")
    train_c = data["train"]
    clf_meta = {"features": features, "threshold": data["threshold"], "model_name": final_name,
                "labels": {"0": "Low", "1": "High"},
                "defaults": train_c[features].median().round(4).to_dict(),
                "ranges": {c: [float(train_c[c].min()), float(train_c[c].max())] for c in features},
                "test_metrics": final_metrics}
    save_model(final_model, "classifier_final", clf_meta)
    for name, m in clf["models"].items():
        save_model(m, "clf_" + name.split(" (")[0].lower().replace(" ", "_"), clf_meta)

    # ---------------- Modules E & F ----------------
    step("Module E: K-Means clustering")
    km = run_kmeans(df_model)
    S["km"] = km
    print("Chosen K:", km["k"]); print(km["profile"].to_string())
    km["table"].to_csv(RESULTS_DIR / "clusters_kmeans.csv")
    km["profile"].assign(label=pd.Series(km["labels"])).to_csv(RESULTS_DIR / "cluster_profile.csv")
    km["centroids_standardised"].to_csv(RESULTS_DIR / "cluster_centroids_standardised.csv")
    km["priority"].to_csv(RESULTS_DIR / "priority_countries.csv")
    pd.Series(km["silhouette"], name="silhouette").to_csv(RESULTS_DIR / "kmeans_silhouette.csv")
    pd.DataFrame({"K": km["ks"], "inertia": km["inertia"]}).to_csv(RESULTS_DIR / "kmeans_elbow.csv", index=False)
    save_model({"kmeans": km["model"], "scaler": km["scaler"], "features": km["features"]}, "kmeans_bundle",
               {"k": km["k"], "labels": km["labels"], "features": km["features"]})
    step("Module F: Gaussian Mixture Model")
    gmm = run_gmm(km)
    S["gmm"] = gmm
    gmm["comparison"].to_csv(RESULTS_DIR / "gmm_comparison.csv", index=False)
    gmm["assignments"].to_csv(RESULTS_DIR / "gmm_assignments.csv")
    save_json(gmm["summary"], "gmm_summary.json")
    save_model(gmm["model"], "gmm", {"n_components": gmm["best_n"], "features": km["features"]})
    print(gmm["comparison"].to_string(index=False)); print(gmm["summary"])

    step("Writing REPORT.md")
    build_report(S)
    save_json({"rows": S["n_rows"], "countries": S["n_countries"], "features": features,
               "final_model": final_name, "seconds": round(time.time() - t0, 1)}, "run_summary.json")
    print(f"\nDONE in {time.time() - t0:.0f} s. Models: {MODELS_DIR}  Plots: {PLOTS_DIR}  Results: {RESULTS_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None, help="Path to the Kaggle CSV (default: first CSV in data/)")
    main(ap.parse_args().data)
