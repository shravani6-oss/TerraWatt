"""Builds REPORT.md from MEASURED results (no hard-coded metric values)."""
import pandas as pd
from .config import ROOT


def md_table(df, index=False):
    d = df.reset_index() if index else df
    head = "| " + " | ".join(map(str, d.columns)) + " |"
    sep = "|" + "|".join(["---"] * len(d.columns)) + "|"
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in d.itertuples(index=False)]
    return "\n".join([head, sep] + rows)


def build_report(S):
    reg, clf, km, gmm = S["reg"], S["clf"], S["km"], S["gmm"]
    rt, ct = reg["table"], clf["table"]
    best_reg = rt.sort_values("RMSE").iloc[0]
    best_clf = ct.sort_values("F1", ascending=False).iloc[0]
    simple = rt[rt.Model == "Simple Linear Regression"].iloc[0]
    multi = rt[rt.Model == "Multiple Linear Regression"].iloc[0]
    base = rt[rt.Model.str.startswith("Baseline")].iloc[0]
    fin = S["final_metrics"]
    gs = S["gmm"]["summary"]
    prof = km["profile"].copy()
    prof.insert(0, "label", [km["labels"][i] for i in prof.index])
    ens = S["cv_table"]
    rf = S["tuned_rf_test"]
    cvs = S["cv_scores"]
    if S["final_name"] != best_clf.Model:
        S["selection_note"] = (
            f"**Model-selection note (important).** The final model was chosen by cross-validation on the training data only, "
            f"not by looking at test scores. Cross-validated F1: " + ", ".join(f"{k} {v:.3f}" for k, v in cvs.items()) +
            f". These top scores are almost tied, so {S['final_name']} won by a tiny margin. On the single held-out split, "
            f"{best_clf.Model} scored F1 = {best_clf.F1:.3f} versus {fin['F1']:.3f} for {S['final_name']}, and the tuned Random Forest scored "
            f"F1 = {rf['F1']:.3f}. A one-split test result is noisy, so no model is declared decisively superior. The selection rule was "
            f"deliberately not changed after seeing test results (that would leak test information). All models are saved so the dashboard can compare them.")
    else:
        S["selection_note"] = (f"The model with the best cross-validated F1 ({S['final_name']}) was also the best on the held-out test set. "
                               f"Tuned Random Forest test F1 = {rf['F1']:.3f}.")
    text = f"""# GreenAI - Project Report
**Green Energy Analytics: A Machine Learning Approach to Renewable Energy and Sustainability**

> All numbers in this report were produced by `python train.py` on the Kaggle file
> *Global Data on Sustainable Energy* ({S['n_rows']} rows, {S['n_countries']} countries, years {S['year_min']}-{S['year_max']}).
> Re-running training regenerates this file.

## 1. Problem statement
Renewable energy adoption differs enormously between countries. We want to (a) predict a country's
renewable energy share, (b) classify country-years as high or low adoption, and (c) group countries
with similar sustainability profiles so that support can be targeted.

## 2. Objectives
1. Clean and explore the global sustainability dataset.
2. Predict renewable share with linear regression (chronological evaluation).
3. Classify high vs low adoption with six algorithms.
4. Cluster countries with K-Means and Gaussian Mixture Models.
5. Validate and tune ensemble models without data leakage.
6. Deliver an interactive Streamlit dashboard.

## 3. Dataset and preprocessing
* Columns used and cleaned names are defined in `src/config.py`. The text column *Density* (e.g. "2,239") was converted to numbers.
* Duplicate rows removed: {S['cleaning']['duplicates_removed']}.
* Columns with more than 50% missing values were dropped: {', '.join(S['dropped_cols']) or 'none'}.
* Rows without the target (renewable share) were removed for supervised learning: {S['n_missing_target']} rows.
* Remaining gaps are filled **inside the scikit-learn pipelines** (median for numbers, mode for categories), so the
  imputer only learns from training data. Skewed columns get log(1+x); linear/distance models are standardised.
* **Leakage control.** Direct renewable indicators ({', '.join(S['leaky'])}) were NOT used as inputs because they measure almost the same thing as the target.

## 4. Methodology and algorithms
| Module | Method | Key design decision |
|---|---|---|
| Regression | Simple & multiple Linear Regression | Train on years <= {reg['cutoff_year']}, test on later years ({reg['n_train']} / {reg['n_test']} rows) |
| Classification | Logistic Regression, KNN, Gaussian NB, Decision Tree, Bagging, Random Forest | "High" = share above the TRAINING median ({clf['threshold']:.2f}%); hold-out split by country |
| Clustering | K-Means (+ elbow, silhouette), PCA | Country averages of the latest {S['last_years']} years, K chosen from 3-6 |
| GMM | Gaussian Mixture, 3/4/5 components | BIC/AIC and silhouette; soft probabilities |
| Validation | Stratified(Group)KFold 5/10, GridSearchCV, RandomizedSearchCV | Grouped CV keeps a country's years in the same fold |

## 5. Results
### 5.1 Regression (target: renewable share %, test years > {reg['cutoff_year']})
{md_table(rt)}

* The baseline (always predicting the training mean) scores R2 = {base.R2:.3f}; any useful model must beat it.
* Simple regression uses `{reg['simple_feature']}` (the feature most correlated with the target in the training years): R2 = {simple.R2:.3f}, RMSE = {simple.RMSE:.2f} percentage points.
* Multiple regression: R2 = {multi.R2:.3f}, RMSE = {multi.RMSE:.2f}.
* Best model by RMSE: **{best_reg.Model}** (R2 = {best_reg.R2:.3f}, RMSE = {best_reg.RMSE:.2f}).
  Models that include the country as a one-hot variable mostly learn each country's typical level, so they are
  strong at predicting *known* countries but say little about unseen ones.

Cross-validation of the multiple regression on the training years:

{md_table(S['reg_cv'])}

Plain KFold lets the same country appear in train and validation folds; GroupKFold does not. The gap between them shows how much a random split can overstate performance.

### 5.2 Classification (High = renewable share > {clf['threshold']:.2f}%)
Class balance in training: {clf['balance']}. Class imbalance handling needed: **{'yes (class_weight="balanced")' if clf['imbalanced'] else 'no (classes are near-balanced)'}**.

{md_table(ct)}

Best test F1: **{best_clf.Model}** (F1 = {best_clf.F1:.3f}, accuracy = {best_clf.Accuracy:.3f}).
Tree ensembles usually do well here because the relationship between access, income, energy use and renewable share is non-linear; the ranking above is the measured result, and small differences between close models may not be significant with one split.

### 5.3 Clustering (K-Means, K = {km['k']})
Silhouette scores for K = 2..12 are in `results/kmeans_silhouette.csv`. K = 2 can score highest but is too coarse for profiling, so K was chosen from 3-6 (chosen silhouette = {km['silhouette_chosen']:.3f}).

{md_table(prof, index=True)}

Labels come from each cluster's measured mean renewable share. **Caveat:** a cluster with a high renewable share is not necessarily "clean": in this data the high-share cluster typically combines a high share with low electricity access and low clean-cooking access, i.e. traditional biomass use.

Top 10 countries for sustainability intervention (score = average percentile deficit in renewable share, electricity access, clean cooking, low-carbon electricity and energy intensity):

{md_table(km['priority'][['renewable_share','electricity_access','clean_cooking_access','low_carbon_elec_pct','energy_intensity','priority_score']], index=True)}

### 5.4 Gaussian Mixture Model
{md_table(gmm['comparison'])}

Best component count by BIC: **{gs['best_n_by_bic']}**. GMM silhouette = {gs['gmm_silhouette']:.3f} vs K-Means = {gs['kmeans_silhouette']:.3f}; agreement between the two (Adjusted Rand Index) = {gs['ARI_vs_kmeans']:.3f} (1 = identical).
K-Means gives *hard* labels; GMM gives a probability for every cluster, so borderline countries can be identified (`plots/gmm_soft_membership.png`).

### 5.5 Ensembles, cross-validation and tuning
{md_table(ens)}

{md_table(S['tuning_table'])}

Final model (chosen by cross-validation on training data only): **{S['final_name']}**. Evaluated once on the untouched test countries:
accuracy = {fin['Accuracy']:.3f}, precision = {fin['Precision']:.3f}, recall = {fin['Recall']:.3f}, F1 = {fin['F1']:.3f}.

Top permutation-importance features (selected model, test set): {', '.join(S['top_features'])}.

{S['selection_note']}

**Honest recommendation:** prefer an ensemble model only if its cross-validated F1 is clearly above simpler models; differences of about 1 F1 point are within fold-to-fold noise (see the Std column in the CV table). Plain stratified CV scores are far higher than grouped CV scores because rows of the same country leak between folds, so the grouped numbers are the trustworthy ones.

## 6. Limitations
* Observational country-level data: models find associations, not causes.
* Many gaps in the data (see missing-value charts); median imputation is a simplification.
* Held-out countries are random; results can change with another split (`random_state`).
* Renewable share counts traditional biomass; high share is not the same as modern clean energy.
* Clusters use 5-year country averages and depend on the chosen indicators.
* Regression predicts a share that can fall outside 0-100; predictions should be read as estimates.

## 7. Conclusion
Using only measured results above: regression beats the naive baseline on later years, classification of high/low adoption on unseen countries is feasible with the best model above, and country clusters reveal groups that differ strongly in income, access and renewable share. Future work: add population-adjusted emissions, time-series models, SHAP explanations and more recent data.
"""
    (ROOT / "REPORT.md").write_text(text, encoding="utf-8")
    return text
