"""Household carbon-footprint maths. Factors are typical published averages (IPCC / DEFRA-style
magnitudes) and are approximate; the grid factor comes from the selected country's generation mix."""
from __future__ import annotations

FACTORS = {
    "gas_kg_per_m3": 2.0,        # natural gas combustion, ~56 kg/GJ x ~36 MJ/m3
    "car_kg_per_km": 0.17,       # average petrol passenger car, tailpipe + fuel chain
    "flight_kg_per_km": 0.15,    # average economy passenger-km
}
FALLBACK_GRID_G_PER_KWH = 440.0  # used only when a country has no mix data (labelled in the response)


def compute(electricity_kwh: float, gas_m3: float, car_km: float, flight_km: float, renewable_pct: float,
            grid_g_per_kwh: float) -> dict:
    grid_kg = grid_g_per_kwh / 1000
    elec = electricity_kwh * (1 - renewable_pct / 100) * grid_kg
    parts = {"electricity": elec, "gas": gas_m3 * FACTORS["gas_kg_per_m3"],
             "car": car_km * FACTORS["car_kg_per_km"], "flights": flight_km * FACTORS["flight_kg_per_km"]}
    parts = {k: round(v, 2) for k, v in parts.items()}
    return {"total_kg": round(sum(parts.values()), 2), "parts": parts, "grid_g_per_kwh": round(grid_g_per_kwh, 1)}


def recommendations(entry: dict, grid_g_per_kwh: float) -> list[dict]:
    """Actions ranked by kg CO2e avoided per month, computed from the user's own numbers."""
    g = grid_g_per_kwh / 1000
    out = []
    kwh, r = entry["electricity_kwh"], entry["renewable_pct"]
    if kwh > 0 and r < 100:
        saved = kwh * (1 - r / 100) * 0.5 * g
        out.append({"title": "Switch half of your remaining grid power to renewables",
                    "detail": "A green tariff or rooftop solar covering half of the electricity you still buy from the grid.",
                    "saving_kg_month": round(saved, 1), "category": "electricity"})
        out.append({"title": "Cut electricity use by 15%",
                    "detail": "LED lighting, efficient appliances and no standby draw typically trim 10–20%.",
                    "saving_kg_month": round(kwh * (1 - r / 100) * 0.15 * g, 1), "category": "electricity"})
    if entry["car_km"] > 0:
        out.append({"title": "Replace 25% of car kilometres with transit, cycling or carpooling",
                    "detail": f"{entry['car_km'] * 0.25:.0f} km a month moved off the car.",
                    "saving_kg_month": round(entry["car_km"] * 0.25 * FACTORS["car_kg_per_km"], 1), "category": "car"})
    if entry["gas_m3"] > 0:
        out.append({"title": "Lower heating demand by 10%",
                    "detail": "Draught-proofing and a 1°C lower thermostat setting.",
                    "saving_kg_month": round(entry["gas_m3"] * 0.10 * FACTORS["gas_kg_per_m3"], 1), "category": "gas"})
    if entry["flight_km"] > 0:
        out.append({"title": "Swap one in four flight-kilometres for rail or a video call",
                    "detail": f"{entry['flight_km'] * 0.25:.0f} km avoided.",
                    "saving_kg_month": round(entry["flight_km"] * 0.25 * FACTORS["flight_kg_per_km"], 1), "category": "flights"})
    out.sort(key=lambda x: -x["saving_kg_month"])
    return out[:5]
