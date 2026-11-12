# GreenAI - Viva preparation (30 questions)
Numbers change slightly if you retrain; check `REPORT.md` for the exact values from your run.

**1. What is the aim of the project?** To analyse global sustainability data: predict renewable energy share, classify high/low adoption, and cluster countries by sustainability profile.

**2. Which dataset did you use?** Kaggle "Global Data on Sustainable Energy": 3,649 rows, 176 countries, years 2000-2020, 21 columns.

**3. What is the target variable for regression?** Renewable energy share in total final energy consumption (%).

**4. Why not use "Electricity from renewables (TWh)" as an input?** It is almost the same thing as the target, so the model would be "cheating" (target leakage) and would not teach us anything.

**5. What is data leakage?** When information from the test set (or the answer) influences training, making results look better than they really are.

**6. How did you handle missing values?** Columns with more than 50% missing were dropped. The rest use median imputation (numbers) or mode (categories) inside a pipeline, fitted on training data only.

**7. Why median instead of mean?** Many columns are skewed (GDP, emissions); the median is not distorted by extreme values.

**8. What is a pipeline and why use it?** A chain of steps (impute -> scale -> model) that is fitted only on training data, preventing leakage and making saving/loading easy.

**9. One-Hot vs Label Encoding?** One-hot makes one 0/1 column per category (no fake order) - used for country. Label encoding maps categories to integers and is only suitable for a target or ordered categories - we demonstrate it only on the High/Low label.

**10. Min-Max scaling vs StandardScaler?** Min-Max squeezes values to 0-1 using min and max; StandardScaler subtracts the mean and divides by the standard deviation (mean 0, std 1). Standard scaling is less affected by the range and is what we use for KNN, logistic regression and K-Means.

**11. Why log-transform some columns?** GDP, CO2, energy use etc. are strongly right-skewed; log(1+x) makes them more symmetric so linear models and distance-based methods behave better.

**12. Why a chronological split for regression?** We want to predict later years from earlier ones; a random split would let the model "see the future".

**13. Explain R2.** The fraction of variance in the target explained by the model. 1 is perfect, 0 equals always predicting the mean, negative is worse than that.

**14. MAE, MSE, RMSE?** MAE = average absolute error; MSE = average squared error (punishes big errors); RMSE = square root of MSE, in the same units as the target (percentage points).

**15. Why include a baseline model?** It shows the minimum a useful model must beat (predicting the training mean gives R2 about 0).

**16. Why does the country one-hot regression score so well?** It learns each country's typical level. That works for known countries but not for countries it never saw.

**17. How is the classification target defined?** High = share above the median of the training set; otherwise Low. The threshold uses only training data.

**18. Why split by country for classification?** A country's yearly rows are nearly identical; a random split would put near-copies in train and test and inflate accuracy.

**19. Accuracy vs precision vs recall vs F1?** Accuracy = fraction correct; precision = of predicted High, how many are truly High; recall = of true High, how many we found; F1 = harmonic mean of precision and recall.

**20. What is a confusion matrix?** A table of actual vs predicted classes: true/false positives and negatives.

**21. Is there class imbalance?** The code checks the majority/minority ratio and uses class_weight="balanced" if it exceeds 1.5; with the median threshold classes are near-balanced.

**22. Why do KNN and Logistic Regression need scaling but trees do not?** They depend on distances/magnitudes; trees split on thresholds, which are unaffected by scale.

**23. Bagging vs Random Forest?** Bagging trains many trees on bootstrap samples and votes. Random Forest also picks a random subset of features at each split, making trees more diverse.

**24. Why is plain stratified CV higher than grouped CV?** Rows of the same country appear in both training and validation folds, leaking information. Grouped CV keeps a country in one fold only, giving an honest estimate.

**25. GridSearchCV vs RandomizedSearchCV?** Grid tries every combination; Randomized tries a fixed number of random combinations - faster, often almost as good. Our run times and scores are in `results/tuning_results.csv`.

**26. How did you pick the final classifier?** By cross-validated F1 on training data only, then evaluated once on the test set. We did not change the rule after seeing test results.

**27. How does K-Means work and how did you choose K?** It assigns points to the nearest of K centroids and updates the centroids until stable. We used the elbow plot and silhouette score (K=3-6 for interpretability).

**28. What is the silhouette score?** How well a point fits its own cluster versus the nearest other cluster; from -1 to 1, higher is better.

**29. K-Means vs GMM - hard vs soft clustering?** K-Means gives each country exactly one cluster. GMM gives probabilities of belonging to each cluster, so borderline countries are visible. BIC/AIC compare GMM fits (lower is better).

**30. What are the limitations?** Observational data (no causation), many missing values, renewable share includes traditional biomass (high share is not always "clean"), one split is noisy, clusters depend on chosen indicators.

**Bonus: Why PCA?** To squeeze 7 indicators into 2 axes so clusters can be drawn on a plot; it is used only for visualisation.
