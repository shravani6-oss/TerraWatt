# GreenAI - Project Report
**Green Energy Analytics: A Machine Learning Approach to Renewable Energy and Sustainability**

> All numbers in this report were produced by `python train.py` on the Kaggle file
> *Global Data on Sustainable Energy* (3649 rows, 176 countries, years 2000-2020).
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
* Duplicate rows removed: 0.
* Columns with more than 50% missing values were dropped: financial_flows_usd, renewables_primary_pct.
* Rows without the target (renewable share) were removed for supervised learning: 194 rows.
* Remaining gaps are filled **inside the scikit-learn pipelines** (median for numbers, mode for categories), so the
  imputer only learns from training data. Skewed columns get log(1+x); linear/distance models are standardised.
* **Leakage control.** Direct renewable indicators (elec_renewable_twh, renew_capacity_per_capita, renewables_primary_pct, low_carbon_elec_pct) were NOT used as inputs because they measure almost the same thing as the target.

## 4. Methodology and algorithms
| Module | Method | Key design decision |
|---|---|---|
| Regression | Simple & multiple Linear Regression | Train on years <= 2016, test on later years (2932 / 523 rows) |
| Classification | Logistic Regression, KNN, Gaussian NB, Decision Tree, Bagging, Random Forest | "High" = share above the TRAINING median (23.93%); hold-out split by country |
| Clustering | K-Means (+ elbow, silhouette), PCA | Country averages of the latest 5 years, K chosen from 3-6 |
| GMM | Gaussian Mixture, 3/4/5 components | BIC/AIC and silhouette; soft probabilities |
| Validation | Stratified(Group)KFold 5/10, GridSearchCV, RandomizedSearchCV | Grouped CV keeps a country's years in the same fold |

## 5. Results
### 5.1 Regression (target: renewable share %, test years > 2016)
| Model | MAE | MSE | RMSE | R2 |
|---|---|---|---|---|
| Baseline (predict train mean) | 23.7717 | 777.1949 | 27.8782 | -0.0023 |
| Simple Linear Regression | 13.9605 | 363.4218 | 19.0636 | 0.5313 |
| Multiple Linear Regression | 10.2713 | 212.3082 | 14.5708 | 0.7262 |
| Multiple LR + country (one-hot) | 3.5552 | 26.5046 | 5.1483 | 0.9658 |

* The baseline (always predicting the training mean) scores R2 = -0.002; any useful model must beat it.
* Simple regression uses `clean_cooking_access` (the feature most correlated with the target in the training years): R2 = 0.531, RMSE = 19.06 percentage points.
* Multiple regression: R2 = 0.726, RMSE = 14.57.
* Best model by RMSE: **Multiple LR + country (one-hot)** (R2 = 0.966, RMSE = 5.15).
  Models that include the country as a one-hot variable mostly learn each country's typical level, so they are
  strong at predicting *known* countries but say little about unseen ones.

Cross-validation of the multiple regression on the training years:

| CV | Mean R2 | Std R2 |
|---|---|---|
| KFold (k=5) - random rows | 0.7905 | 0.0176 |
| GroupKFold (k=5) - unseen countries | 0.7433 | 0.0901 |

Plain KFold lets the same country appear in train and validation folds; GroupKFold does not. The gap between them shows how much a random split can overstate performance.

### 5.2 Classification (High = renewable share > 23.93%)
Class balance in training: {'Low(0)': 1381, 'High(1)': 1381, 'ratio_majority_to_minority': 1.0}. Class imbalance handling needed: **no (classes are near-balanced)**.

| Model | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| Logistic Regression | 0.8384 | 1.0 | 0.6627 | 0.7971 |
| KNN (k=5) | 0.8268 | 0.8232 | 0.8133 | 0.8182 |
| Gaussian Naive Bayes | 0.8658 | 0.9918 | 0.7259 | 0.8383 |
| Decision Tree | 0.8413 | 0.8908 | 0.762 | 0.8214 |
| Bagging | 0.8629 | 0.9575 | 0.747 | 0.8393 |
| Random Forest | 0.9004 | 0.9647 | 0.8223 | 0.8878 |

Best test F1: **Random Forest** (F1 = 0.888, accuracy = 0.900).
Tree ensembles usually do well here because the relationship between access, income, energy use and renewable share is non-linear; the ranking above is the measured result, and small differences between close models may not be significant with one split.

### 5.3 Clustering (K-Means, K = 3)
Silhouette scores for K = 2..12 are in `results/kmeans_silhouette.csv`. K = 2 can score highest but is too coarse for profiling, so K was chosen from 3-6 (chosen silhouette = 0.297).

| cluster | label | renewable_share | electricity_access | clean_cooking_access | gdp_per_capita | energy_per_capita_kwh | low_carbon_elec_pct | energy_intensity | n_countries |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Medium renewable adoption (mean 34.4%) | 34.42 | 97.29 | 85.62 | 22519.34 | 30374.69 | 72.0 | 3.91 | 52 |
| 1 | High renewable adoption (mean 62.6%) | 62.57 | 50.09 | 14.9 | 1321.83 | 1807.4 | 41.19 | 5.71 | 49 |
| 2 | Low renewable adoption (mean 8.8%) | 8.8 | 97.54 | 90.41 | 20023.38 | 38091.81 | 13.48 | 4.36 | 74 |

Labels come from each cluster's measured mean renewable share. **Caveat:** a cluster with a high renewable share is not necessarily "clean": in this data the high-share cluster typically combines a high share with low electricity access and low clean-cooking access, i.e. traditional biomass use.

Top 10 countries for sustainability intervention (score = average percentile deficit in renewable share, electricity access, clean cooking, low-carbon electricity and energy intensity):

| country | renewable_share | electricity_access | clean_cooking_access | low_carbon_elec_pct | energy_intensity | priority_score |
|---|---|---|---|---|---|---|
| Libya | 2.71 | 69.48 | nan | 0.03 | 8.88 | 0.87 |
| South Sudan | 28.18 | 5.89 | 0.0 | 1.08 | nan | 0.82 |
| Guinea-Bissau | 86.59 | 28.35 | 1.1 | 0.0 | 8.94 | 0.77 |
| Benin | 45.31 | 38.52 | 4.14 | 1.87 | 6.02 | 0.75 |
| Mongolia | 3.29 | 95.16 | 48.68 | 7.29 | 6.42 | 0.75 |
| Yemen | 3.0 | 71.31 | 61.37 | 10.46 | nan | 0.74 |
| Liberia | 85.43 | 23.08 | 0.4 | 11.91 | 13.88 | 0.73 |
| Kiribati | 42.42 | 89.82 | 8.18 | 0.0 | 5.84 | 0.72 |
| Turkmenistan | 0.06 | 99.98 | 99.9 | 0.0 | 13.84 | 0.72 |
| South Africa | 10.42 | 84.48 | 85.68 | 10.41 | 7.88 | 0.7 |

### 5.4 Gaussian Mixture Model
| Components | BIC | AIC | Silhouette |
|---|---|---|---|
| 3 | 1723.82 | 1385.188 | 0.151 |
| 4 | 1797.285 | 1344.721 | 0.129 |
| 5 | 1767.638 | 1201.141 | 0.114 |

Best component count by BIC: **3**. GMM silhouette = 0.151 vs K-Means = 0.297; agreement between the two (Adjusted Rand Index) = 0.295 (1 = identical).
K-Means gives *hard* labels; GMM gives a probability for every cluster, so borderline countries can be identified (`plots/gmm_soft_membership.png`).

### 5.5 Ensembles, cross-validation and tuning
| Folds | CV strategy | Model | Mean F1 | Std F1 |
|---|---|---|---|---|
| 5 | Grouped stratified (honest) | Decision Tree | 0.8139 | 0.0522 |
| 5 | Grouped stratified (honest) | Bagging | 0.8386 | 0.0198 |
| 5 | Grouped stratified (honest) | Random Forest | 0.8602 | 0.0209 |
| 5 | Plain stratified (optimistic) | Decision Tree | 0.9732 | 0.0049 |
| 5 | Plain stratified (optimistic) | Bagging | 0.9829 | 0.0034 |
| 5 | Plain stratified (optimistic) | Random Forest | 0.9862 | 0.0037 |
| 10 | Grouped stratified (honest) | Decision Tree | 0.8151 | 0.0753 |
| 10 | Grouped stratified (honest) | Bagging | 0.8441 | 0.0605 |
| 10 | Grouped stratified (honest) | Random Forest | 0.8423 | 0.1008 |
| 10 | Plain stratified (optimistic) | Decision Tree | 0.9732 | 0.0075 |
| 10 | Plain stratified (optimistic) | Bagging | 0.9837 | 0.007 |
| 10 | Plain stratified (optimistic) | Random Forest | 0.9837 | 0.006 |

| Search | Candidates | Best CV F1 | Seconds | Best parameters |
|---|---|---|---|---|
| Grid | 36 | 0.8679 | 81.0503 | {'clf__max_depth': None, 'clf__max_features': 0.5, 'clf__min_samples_leaf': 2, 'clf__n_estimators': 100} |
| Randomized | 12 | 0.8679 | 28.2501 | {'clf__n_estimators': 100, 'clf__min_samples_leaf': 2, 'clf__max_features': 0.5, 'clf__max_depth': None} |

Final model (chosen by cross-validation on training data only): **Logistic Regression**. Evaluated once on the untouched test countries:
accuracy = 0.838, precision = 1.000, recall = 0.663, F1 = 0.797.

Top permutation-importance features (selected model, test set): clean_cooking_access, elec_fossil_twh, land_area_km2, energy_intensity, elec_nuclear_twh.

**Model-selection note (important).** The final model was chosen by cross-validation on the training data only, not by looking at test scores. Cross-validated F1: Logistic Regression 0.869, KNN (k=5) 0.804, Gaussian Naive Bayes 0.820, Decision Tree 0.814, Bagging 0.839, Random Forest 0.860, Tuned Random Forest 0.868. These top scores are almost tied, so Logistic Regression won by a tiny margin. On the single held-out split, Random Forest scored F1 = 0.888 versus 0.797 for Logistic Regression, and the tuned Random Forest scored F1 = 0.865. A one-split test result is noisy, so no model is declared decisively superior. The selection rule was deliberately not changed after seeing test results (that would leak test information). All models are saved so the dashboard can compare them.

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
