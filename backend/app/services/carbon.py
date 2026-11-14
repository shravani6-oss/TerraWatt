"""Estimated household OPERATIONAL carbon footprint (electricity, cooking/heating fuel, personal and public transport,
flights, a few other activities). It deliberately excludes food, goods, services, housing construction and waste, so it is
NOT a full lifestyle footprint.

Two input modes share one engine:
  simple    everyday questions (INR bill, LPG cylinders, vehicle type + distance, ...) -> converted with DISCLOSED assumptions
  advanced  exact kWh, gas m3, vehicle km, flight pkm, renewable %

Every line item records whether its basis is ACTUAL (user supplied the physical quantity) or ESTIMATED (derived from an
approximate answer or a stated assumption), together with a relative uncertainty. Totals carry a low-high range obtained by
combining item uncertainties in quadrature (they are treated as independent).

Factors are versioned. Stored entries keep their raw inputs and are re-evaluated with the CURRENT factor version, with the
grid intensity pinned to one reporting year, so month-to-month comparisons (goals) never mix emission factors.
"""
from __future__ import annotations

import math

FACTOR_VERSION = "tw-carbon-2"
FALLBACK_GRID_G_PER_KWH = 440.0   # only when a country has no Ember intensity at all (flagged in the response)

DEFAULT_TARIFF_INR = 7.0          # all-in average Indian domestic tariff (energy + fixed + duty), disclosed; user-editable
TARIFF_PRESETS = [
    {"key": "low", "label": "Low (₹5/kWh)", "value": 5.0},
    {"key": "typical", "label": "Typical urban (₹7/kWh)", "value": 7.0},
    {"key": "high", "label": "High (₹9/kWh)", "value": 9.0},
]

# kg CO2e per unit. Combustion factors follow IPCC 2006 defaults; vehicle fuel economies are typical real-world values.
F = {
    "lpg_kg": 2.98,               # 63.1 kg/GJ x 47.3 GJ/t
    "png_m3": 2.0,                # natural gas, ~56 kg/GJ x ~36 MJ/m3
    "petrol_l": 2.31, "diesel_l": 2.68,
    "cng_car_km": 0.12,           # ~22 km/kg x 2.7 kg CO2/kg
    "cab_km": 0.11,               # taxi / auto-rickshaw, per vehicle-km (1-2 passengers)
    "bus_pkm": 0.07, "train_pkm": 0.03,
    "metro_kwh_per_pkm": 0.045,   # electric: multiplied by the grid intensity
    "flight_pkm": 0.15,           # economy passenger-km, excludes radiative forcing
    "dg_kg_per_hour": 2.68,       # ~1 L diesel per hour for a small (about 3 kVA) generator
}
VEHICLES = {  # key: (label, km per litre, fuel factor key | None, kWh per km for EVs)
    "motorcycle": ("Motorcycle (petrol)", 40.0, "petrol_l", None),
    "scooter": ("Scooter (petrol)", 45.0, "petrol_l", None),
    "petrol_car": ("Car (petrol)", 15.0, "petrol_l", None),
    "diesel_car": ("Car (diesel)", 18.0, "diesel_l", None),
    "cng_car": ("Car (CNG)", None, None, None),
    "ev_car": ("Electric car", None, None, 0.14),
    "ev_two_wheeler": ("Electric two-wheeler", None, None, 0.035),
}
FLIGHT_BANDS = {"never": (0.0, 0.0), "occasionally": (4000.0, 0.5), "frequently": (16000.0, 0.5)}  # household pkm / year, half-range
CATEGORIES = {"electricity": "Electricity", "cooking_heating": "Cooking & heating fuel", "vehicles": "Personal vehicles",
              "public_transport": "Public transport & cabs", "flights": "Flights", "other": "Other"}


def grid_factor(data, country: str) -> dict:
    """Pinned grid intensity: the country's value in the dataset's broad-coverage year (falls back to its latest year)."""
    y = data.year_for("grid_intensity")
    s = data._by_country[country]["grid_intensity"].dropna()
    if y in s.index:
        return {"g_per_kwh": float(s.loc[y]), "year": int(y), "from_data": True, "source": "Ember (lifecycle, generation-based)"}
    if len(s):
        return {"g_per_kwh": float(s.iloc[-1]), "year": int(s.index[-1]), "from_data": True, "source": "Ember (lifecycle, generation-based)"}
    return {"g_per_kwh": FALLBACK_GRID_G_PER_KWH, "year": None, "from_data": False, "source": "generic fallback"}


def _item(key, label, cat, kg, rel, basis, note):
    return {"key": key, "label": label, "category": cat, "kg": round(kg, 2), "half_range_kg": round(kg * rel, 2),
            "rel_uncertainty": rel, "basis": basis, "note": note}


def _finish(items, size, grid, mode, assumptions, skipped, extra=None):
    parts = {c: 0.0 for c in CATEGORIES}
    for i in items:
        parts[i["category"]] += i["kg"]
    total = sum(parts.values())
    err = math.sqrt(sum(i["half_range_kg"] ** 2 for i in items))
    parts = {k: round(v, 2) for k, v in parts.items()}
    res = {"mode": mode, "factor_version": FACTOR_VERSION, "household_size": size, "total_kg": round(total, 2),
           "low_kg": round(max(0.0, total - err), 2), "high_kg": round(total + err, 2),
           "per_person_kg": round(total / size, 2), "parts": parts, "items": items,
           "grid": {k: grid[k] for k in ("g_per_kwh", "year", "from_data", "source")}, "assumptions": assumptions,
           "skipped": skipped, "estimated_share": round(sum(i["kg"] for i in items if i["basis"] != "actual") / total, 3) if total else 0.0,
           "scope": "Estimated household operational carbon footprint: electricity, cooking/heating fuel, transport and flights. "
                    "Excludes food, goods, services, home construction and waste."}
    res.update(extra or {})
    return res


def _electricity(inp: dict, grid, assumptions, skipped):
    kwh, basis, rel, note = None, "actual", 0.05, ""
    if inp.get("kwh") not in (None, ""):
        kwh = float(inp["kwh"])
        note = "Your meter/bill reading."
    elif inp.get("bill_inr") not in (None, "", 0):
        tariff = float(inp.get("tariff_inr_per_kwh") or DEFAULT_TARIFF_INR)
        kwh, basis, rel = float(inp["bill_inr"]) / tariff, "estimated", 0.25
        note = f"Bill ₹{float(inp['bill_inr']):,.0f} ÷ tariff ₹{tariff:g}/kWh = {kwh:,.0f} kWh."
        assumptions.append(f"Electricity bill converted at ₹{tariff:g}/kWh (all-in average; your tariff may differ).")
    else:
        skipped.append("electricity")
        return None, 0.0
    ren = float(inp.get("renewable_pct") or 0)
    kg = kwh * (1 - ren / 100) * grid["g_per_kwh"] / 1000
    return _item("electricity", f"Electricity ({kwh:,.0f} kWh)", "electricity", kg, rel, basis,
                 note + f" Grid intensity {grid['g_per_kwh']:.0f} g CO₂e/kWh"
                 + (f" ({grid['year']})" if grid["year"] else "") + (f"; {ren:g}% from own renewables." if ren else ".")), kwh


def evaluate_household(inp: dict, grid: dict) -> dict:
    """Simple mode. `inp` is the validated HouseholdIn payload (as a dict)."""
    items, assumptions, skipped = [], [], []
    size = int(inp.get("household_size") or 1)
    el_item, kwh = _electricity(inp.get("electricity") or {}, grid, assumptions, skipped)
    if el_item:
        items.append(el_item)
    # cooking fuel
    ck = inp.get("cooking") or {}
    t, qty = ck.get("type"), float(ck.get("per_month") or 0)
    if t in ("lpg_14kg", "lpg_5kg") and qty > 0:
        kg_per = 14.2 if t == "lpg_14kg" else 5.0
        items.append(_item("lpg", f"LPG ({qty:g} × {kg_per:g} kg cylinder/month)", "cooking_heating", qty * kg_per * F["lpg_kg"], 0.15,
                           "estimated", f"{qty:g} cylinder(s) × {kg_per:g} kg × {F['lpg_kg']} kg CO₂/kg."))
    elif t == "piped" and qty > 0:
        items.append(_item("png", f"Piped gas ({qty:g} m³/month)", "cooking_heating", qty * F["png_m3"], 0.15,
                           "actual" if ck.get("exact") else "estimated", f"{qty:g} m³ × {F['png_m3']} kg CO₂/m³."))
    elif t in (None, "", "none"):
        if t is None:
            skipped.append("cooking fuel")
    # vehicles
    for i, v in enumerate(inp.get("vehicles") or []):
        vt, km = v.get("type"), float(v.get("km_per_month") or 0)
        if vt in (None, "none") or km <= 0 or vt not in VEHICLES:
            continue
        label, kmpl, fuel, ev = VEHICLES[vt]
        if ev is not None:
            kg, note = km * ev * grid["g_per_kwh"] / 1000, f"{km:g} km × {ev} kWh/km × grid {grid['g_per_kwh']:.0f} g/kWh."
            rel = 0.20
        elif vt == "cng_car":
            kg, note, rel = km * F["cng_car_km"], f"{km:g} km × {F['cng_car_km']} kg/km (≈22 km/kg CNG).", 0.25
        else:
            kg = km / kmpl * F[fuel]
            note, rel = f"{km:g} km ÷ {kmpl:g} km/L × {F[fuel]} kg CO₂/L.", 0.30
            assumptions.append(f"{label}: assumed {kmpl:g} km per litre (typical real-world mileage).")
        items.append(_item(f"vehicle{i}", f"{label}, {km:g} km/month", "vehicles", kg, rel, "estimated", note))
    # public transport & cabs
    tr = inp.get("transit") or {}
    metro_f = F["metro_kwh_per_pkm"] * grid["g_per_kwh"] / 1000
    for key, label, f in (("bus_km", "Bus", F["bus_pkm"]), ("train_km", "Train", F["train_pkm"]),
                          ("metro_km", "Metro", metro_f), ("cab_km", "Taxi / auto-rickshaw", F["cab_km"])):
        km = float(tr.get(key) or 0)
        if km > 0:
            items.append(_item(key, f"{label}, {km:g} km/month", "public_transport", km * f, 0.40, "estimated",
                               f"{km:g} km × {f:.3f} kg CO₂e per {'vehicle-km' if key == 'cab_km' else 'passenger-km'}."))
    # flights
    fl = inp.get("flights")
    if fl is not None:
        if isinstance(fl, dict) and fl.get("pkm_per_year"):
            annual, rel, note = float(fl["pkm_per_year"]), 0.15, "Your stated passenger-km per year."
            basis = "actual"
        else:
            band = fl if isinstance(fl, str) else (fl or {}).get("frequency")
            if band not in FLIGHT_BANDS:
                band = "never"
            annual, rel = FLIGHT_BANDS[band]
            basis, note = "estimated", f"'{band}' assumed to be {annual:,.0f} passenger-km per year for the whole household."
            if annual:
                assumptions.append(f"Flights '{band}' ≈ {annual:,.0f} passenger-km/year for the household (±50%).")
            if not annual:
                rel = 0.0
        if annual:
            items.append(_item("flights", f"Flights ({annual:,.0f} km/yr ÷ 12)", "flights", annual / 12 * F["flight_pkm"], rel, basis,
                               note + f" × {F['flight_pkm']} kg/pkm, averaged per month."))
    else:
        skipped.append("flights")
    # other
    ot = inp.get("other") or {}
    dg = float(ot.get("generator_hours") or 0)
    if dg > 0:
        items.append(_item("generator", f"Diesel generator, {dg:g} h/month", "other", dg * F["dg_kg_per_hour"], 0.40, "estimated",
                           f"{dg:g} h × {F['dg_kg_per_hour']} kg CO₂/h (≈1 L diesel/h)."))
    if not items:
        raise ValueError("Answer at least one question so there is something to calculate.")
    return _finish(items, size, grid, "simple", assumptions, skipped,
                   {"derived_kwh": round(kwh, 1) if kwh is not None else None})


def evaluate_advanced(inp: dict, grid: dict) -> dict:
    """Advanced mode: exact physical quantities. Gas = natural gas m3, vehicle = petrol-car km (0.17 kg/km), flights = pkm."""
    items, assumptions, skipped = [], [], []
    size = int(inp.get("household_size") or 1)
    el, kwh = _electricity({"kwh": inp.get("electricity_kwh") or None, "renewable_pct": inp.get("renewable_pct", 0)}, grid, assumptions, skipped)
    if el:
        items.append(el)
    if (inp.get("gas_m3") or 0) > 0:
        items.append(_item("gas", f"Natural gas ({inp['gas_m3']:g} m³)", "cooking_heating", inp["gas_m3"] * F["png_m3"], 0.05, "actual",
                           f"{inp['gas_m3']:g} m³ × {F['png_m3']} kg CO₂/m³."))
    if (inp.get("lpg_kg") or 0) > 0:
        items.append(_item("lpg", f"LPG ({inp['lpg_kg']:g} kg)", "cooking_heating", inp["lpg_kg"] * F["lpg_kg"], 0.05, "actual",
                           f"{inp['lpg_kg']:g} kg × {F['lpg_kg']} kg CO₂/kg."))
    if (inp.get("car_km") or 0) > 0:
        items.append(_item("car", f"Car ({inp['car_km']:g} km)", "vehicles", inp["car_km"] * 0.17, 0.20, "actual",
                           f"{inp['car_km']:g} km × 0.17 kg/km (average petrol car, tailpipe + fuel chain)."))
    if (inp.get("flight_km") or 0) > 0:
        items.append(_item("flights", f"Flights ({inp['flight_km']:g} pkm)", "flights", inp["flight_km"] * F["flight_pkm"], 0.15, "actual",
                           f"{inp['flight_km']:g} pkm × {F['flight_pkm']} kg/pkm."))
    if not items:
        raise ValueError("Enter at least one non-zero activity.")
    return _finish(items, size, grid, "advanced", assumptions, skipped, {"derived_kwh": kwh})


def evaluate(mode: str, inp: dict, grid: dict) -> dict:
    return evaluate_household(inp, grid) if mode == "simple" else evaluate_advanced(inp, grid)


def benchmark(data, country: str, size: int, total_kg: float) -> dict | None:
    """National territorial CO2 per person (all sectors) vs the world average, as monthly kg for context only."""
    lat = data.latest(country, "co2_per_capita_t")
    world = data.world_average("co2_per_capita_t")
    if not lat:
        return None
    nat_m = lat[1] * 1000 / 12
    out = {"country": country, "national_year": lat[0], "national_kg_per_person_month": round(nat_m, 1),
           "you_kg_per_person_month": round(total_kg / size, 1),
           "vs_national_pct": round((total_kg / size / nat_m - 1) * 100, 0) if nat_m else None,
           "caveat": ("National CO₂ per person covers ALL territorial fossil emissions (industry, power for businesses, etc.), "
                      "while your estimate covers household operations only, so this is context, not a like-for-like score.")}
    if world:
        w = world[-1]
        out["world_kg_per_person_month"] = round(w["value"] * 1000 / 12, 1)
        out["world_year"] = w["year"]
    return out


def recommendations(res: dict, limit: int = 5) -> list[dict]:
    """Actions ranked by kg CO2e avoided per month, each computed from THIS household's own line items."""
    g = res["grid"]["g_per_kwh"] / 1000
    by = {i["key"]: i for i in res["items"]}
    out = []

    def add(title, detail, kg, cat):
        if kg > 0.4:
            out.append({"title": title, "detail": detail, "saving_kg_month": round(kg, 1), "category": cat})
    el = by.get("electricity")
    if el:
        add("Cut electricity use by 15%", "LED lighting, a 5-star AC/fridge, fans over AC and no standby draw typically trim 10–20%.", el["kg"] * 0.15, "electricity")
        add("Shift half your grid power to solar or a green tariff", "Rooftop solar or a renewable tariff covering half of the grid electricity you buy.", el["kg"] * 0.5, "electricity")
    for k, i in by.items():
        if i["category"] == "vehicles" and not k.startswith("ev"):
            add(f"Replace a quarter of '{i['label'].split(',')[0]}' kilometres with bus, metro, train or carpooling",
                "Combining errands and using public transport for regular commutes.", i["kg"] * 0.25 * 0.8, "vehicles")
    if "lpg" in by:
        add("Use a pressure cooker and keep lids on", "Efficient cooking habits typically cut cooking-gas use by 10–20%.", by["lpg"]["kg"] * 0.12, "cooking_heating")
    if "png" in by or "gas" in by:
        i = by.get("png") or by["gas"]
        add("Trim gas use by 10%", "Efficient burners, lids and pressure cooking.", i["kg"] * 0.10, "cooking_heating")
    if "flights" in by:
        add("Swap one in four flight-kilometres for rail or a video call", "Rail is roughly a fifth of the CO₂ per passenger-km.", by["flights"]["kg"] * 0.25 * 0.8, "flights")
    if "generator" in by:
        add("Use an inverter/battery instead of a diesel generator for short outages", "Diesel generators burn ~1 L per hour.", by["generator"]["kg"] * 0.5, "other")
    out = [o for o in out if o["saving_kg_month"] > 0]
    out.sort(key=lambda x: -x["saving_kg_month"])
    return out[:limit]
