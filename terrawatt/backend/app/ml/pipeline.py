"""Shared feature definitions and sklearn preprocessing (kept importable so joblib can unpickle)."""
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

TARGET = "renewable_share"
# Direct renewable indicators (renewable TWh / capacity / % primary / low-carbon %) are excluded
# on purpose: they would leak the target. Columns with >50% missing values are dropped.
FEATURES = ["electricity_access", "clean_cooking_access", "elec_fossil_twh", "elec_nuclear_twh",
            "energy_per_capita_kwh", "energy_intensity", "co2_kt", "gdp_growth", "gdp_per_capita",
            "density", "land_area_km2", "latitude", "longitude"]
LOG_COLS = ["elec_fossil_twh", "elec_nuclear_twh", "energy_per_capita_kwh", "co2_kt",
            "gdp_per_capita", "density", "land_area_km2"]
FEATURE_LABELS = {
    "electricity_access": "Access to electricity (%)", "clean_cooking_access": "Clean cooking access (%)",
    "elec_fossil_twh": "Fossil electricity (TWh)", "elec_nuclear_twh": "Nuclear electricity (TWh)",
    "energy_per_capita_kwh": "Energy per person (kWh)", "energy_intensity": "Energy intensity (MJ/$ PPP)",
    "co2_kt": "CO₂ emissions (kt)", "gdp_growth": "GDP growth (%)", "gdp_per_capita": "GDP per capita (US$)",
    "density": "Population density (/km²)", "land_area_km2": "Land area (km²)",
    "latitude": "Latitude", "longitude": "Longitude", "year": "Year"}
# The what-if UI lets people change these (the others are fixed country characteristics).
SCENARIO_FEATURES = ["electricity_access", "clean_cooking_access", "elec_fossil_twh", "elec_nuclear_twh",
                     "energy_per_capita_kwh", "energy_intensity", "gdp_per_capita", "gdp_growth"]


def safe_log1p(x):
    return np.log1p(np.clip(x, 0, None))


def build_preprocessor(numeric, categorical=(), scale=True):
    logged = [c for c in numeric if c in LOG_COLS]
    plain = [c for c in numeric if c not in LOG_COLS]

    def num(use_log):
        steps = [("impute", SimpleImputer(strategy="median"))]
        if use_log:
            steps.append(("log", FunctionTransformer(safe_log1p, feature_names_out="one-to-one")))
        if scale:
            steps.append(("scale", StandardScaler()))
        return Pipeline(steps)

    parts = []
    if plain:
        parts.append(("num", num(False), plain))
    if logged:
        parts.append(("num_log", num(True), logged))
    if categorical:
        parts.append(("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                                       ("onehot", OneHotEncoder(handle_unknown="ignore"))]), list(categorical)))
    return ColumnTransformer(parts, verbose_feature_names_out=False)
