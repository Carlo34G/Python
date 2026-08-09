"""Calorie / macro lookup for foods.

Primary: Nutritionix natural-language endpoint — understands things like
"2 cups rice and grilled chicken thigh" and returns per-item calories/macros.
This is the piece that fixes the "no good calorie service" problem, and it is the
same provider you should also enable inside Sparky itself.

Fallback: OpenFoodFacts (free, no key). Good for branded/packaged items, weaker for
generic whole foods, so it's only used when Nutritionix isn't configured.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import httpx

from config import settings

NUTRITIONIX_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"
OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"


@dataclass
class FoodItem:
    name: str
    calories: float
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    serving: str = ""


@dataclass
class NutritionResult:
    items: List[FoodItem] = field(default_factory=list)
    source: str = ""
    error: str = ""

    @property
    def total_calories(self) -> float:
        return round(sum(i.calories for i in self.items), 1)

    @property
    def total_protein(self) -> float:
        return round(sum(i.protein_g for i in self.items), 1)


async def _lookup_nutritionix(query: str) -> NutritionResult:
    headers = {
        "x-app-id": settings.nutritionix_app_id,
        "x-app-key": settings.nutritionix_app_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(NUTRITIONIX_URL, headers=headers, json={"query": query})
        resp.raise_for_status()
        data = resp.json()

    items: List[FoodItem] = []
    for f in data.get("foods", []):
        qty = f.get("serving_qty", "")
        unit = f.get("serving_unit", "")
        items.append(
            FoodItem(
                name=str(f.get("food_name", "food")).title(),
                calories=round(float(f.get("nf_calories") or 0), 1),
                protein_g=round(float(f.get("nf_protein") or 0), 1),
                carbs_g=round(float(f.get("nf_total_carbohydrate") or 0), 1),
                fat_g=round(float(f.get("nf_total_fat") or 0), 1),
                serving=f"{qty} {unit}".strip(),
            )
        )
    return NutritionResult(items=items, source="Nutritionix")


async def _lookup_openfoodfacts(query: str) -> NutritionResult:
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 1,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(OFF_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    products = data.get("products", [])
    if not products:
        return NutritionResult(source="OpenFoodFacts", error="No match found.")

    p = products[0]
    n = p.get("nutriments", {})
    name = p.get("product_name") or query
    # OFF gives per-100g; report that serving explicitly so the number isn't misread.
    item = FoodItem(
        name=str(name).title(),
        calories=round(float(n.get("energy-kcal_100g") or 0), 1),
        protein_g=round(float(n.get("proteins_100g") or 0), 1),
        carbs_g=round(float(n.get("carbohydrates_100g") or 0), 1),
        fat_g=round(float(n.get("fat_100g") or 0), 1),
        serving="per 100 g",
    )
    return NutritionResult(items=[item], source="OpenFoodFacts")


async def lookup_food(query: str) -> NutritionResult:
    """Look up a free-text food description. Nutritionix first, then OpenFoodFacts."""
    query = query.strip()
    if not query:
        return NutritionResult(error="Tell me what you ate, e.g. `/food 1 cup rice, grilled chicken`.")

    if settings.nutritionix_app_id and settings.nutritionix_app_key:
        try:
            result = await _lookup_nutritionix(query)
            if result.items:
                return result
        except Exception as exc:  # fall through to OFF on any failure
            fallback = await _safe_off(query)
            if fallback.items:
                return fallback
            return NutritionResult(error=f"Nutritionix lookup failed: {exc}")

    return await _safe_off(query)


async def _safe_off(query: str) -> NutritionResult:
    try:
        return await _lookup_openfoodfacts(query)
    except Exception as exc:
        return NutritionResult(error=f"Nutrition lookup failed: {exc}")


def format_result(result: NutritionResult) -> str:
    if result.error:
        return f"⚠️ {result.error}"
    lines = []
    for i in result.items:
        serving = f" ({i.serving})" if i.serving else ""
        lines.append(
            f"• {i.name}{serving}: {i.calories:.0f} kcal, "
            f"P{i.protein_g:.0f}/C{i.carbs_g:.0f}/F{i.fat_g:.0f} g"
        )
    header = f"\U0001f37d Total: *{result.total_calories:.0f} kcal*, {result.total_protein:.0f} g protein"
    footer = f"_source: {result.source}_"
    return "\n".join([header, *lines, "", footer])
