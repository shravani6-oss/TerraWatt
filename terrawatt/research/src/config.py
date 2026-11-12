"""Central configuration: paths, column names, feature lists, constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
PLOTS_DIR = ROOT / "plots"
RESULTS_DIR = ROOT / "results"
RANDOM_STATE = 42

# Original Kaggle column name -> short snake_case name used in the code.
RENAME_MAP = {
    "Entity": "country",
    "Year": "year",
    "Access to electricity (% of population)": "electricity_access",
    "Access to clean fuels for cooking": "clean_cooking_access",
    "Renewable-electricity-generating-capacity-per-capita": "renew_capacity_per_capita",
    "Financial flows to developing countries (US $)": "financial_flows_usd",
    "Renewable energy share in the total final energy consumption (%)": "renewable_share",
    "Electricity from fossil fuels (TWh)": "elec_fossil_twh",
    "Electricity from nuclear (TWh)": "elec_nuclear_twh",
    "Electricity from renewables (TWh)": "elec_renewable_twh",
    "Low-carbon electricity (% electricity)": "low_carbon_elec_pct",
    "Primary energy consumption per capita (kWh/person)": "energy_per_capita_kwh",
    "Energy intensity level of primary energy (MJ/$2017 PPP GDP)": "energy_intensity",
    "Value_co2_emissions_kt_by_country": "co2_kt",
    "Renewables (% equivalent primary energy)": "renewables_primary_pct",
    "gdp_growth": "gdp_growth",
    "gdp_per_capita": "gdp_per_capita",
    "Density\\n(P/Km2)": "density",
    "Land Area(Km2)": "land_area_km2",
    "Latitude": "latitude",
    "Longitude": "longitude",
}

# Human-readable labels for charts / dashboard
LABELS = {
    "renewable_share": "Renewable energy share of final energy (%)",
    "electricity_access": "Access to electricity (% of population)",
    "clean_cooking_access": "Access to clean cooking fuels (%)",
    "renew_capacity_per_capita": "Renewable electricity capacity per capita (W)",
    "financial_flows_usd": "Financial flows to developing countries (US$)",
    "elec_fossil_twh": "Electricity from fossil fuels (TWh)",
    "elec_nuclear_twh": "Electricity from nuclear (TWh)",
    "elec_renewable_twh": "Electricity from renewables (TWh)",
    "low_carbon_elec_pct": "Low-carbon electricity (% of electricity)",
    "energy_per_capita_kwh": "Primary energy use per person (kWh)",
    "energy_intensity": "Energy intensity (MJ per $2017 PPP GDP)",
    "co2_kt": "CO2 emissions (kt)",
    "renewables_primary_pct": "Renewables (% of primary energy)",
    "gdp_growth": "GDP growth (%)",
    "gdp_per_capita": "GDP per capita (US$)",
    "density": "Population density (people / km2)",
    "land_area_km2": "Land area (km2)",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "year": "Year",
}

REQUIRED_COLUMNS = ["country", "year", "renewable_share"]
TARGET = "renewable_share"

# Columns dropped before modelling because > 50% of values are missing.
MAX_MISSING_FRACTION = 0.50

# Model inputs. Direct renewable-energy indicators (renewable TWh, renewable capacity,
# renewables % of primary energy, low-carbon %) are EXCLUDED to avoid target leakage:
# they measure (almost) the same thing as the target.
MODEL_FEATURES = [
    "electricity_access", "clean_cooking_access", "elec_fossil_twh", "elec_nuclear_twh",
    "energy_per_capita_kwh", "energy_intensity", "co2_kt", "gdp_growth",
    "gdp_per_capita", "density", "land_area_km2", "latitude", "longitude",
]
LEAKY_COLUMNS = ["elec_renewable_twh", "renew_capacity_per_capita", "renewables_primary_pct",
                 "low_carbon_elec_pct"]
# Right-skewed, non-negative columns that get log(1+x) inside the pipeline
LOG_COLS = ["elec_fossil_twh", "elec_nuclear_twh", "energy_per_capita_kwh", "co2_kt",
            "gdp_per_capita", "density", "land_area_km2"]

# Country-level indicators used for clustering (modules E/F)
CLUSTER_FEATURES = ["renewable_share", "electricity_access", "clean_cooking_access",
                    "gdp_per_capita", "energy_per_capita_kwh", "low_carbon_elec_pct",
                    "energy_intensity"]
CLUSTER_LOG = ["gdp_per_capita", "energy_per_capita_kwh"]
CLUSTER_LAST_YEARS = 5          # average of the most recent 5 years per country
TEST_YEARS = 4                  # chronological regression test = last 4 years
