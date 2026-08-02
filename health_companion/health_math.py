"""Nutrition/energy maths and the personalised plan text.

Pure functions only — no network, no I/O — so this module is fully unit-testable
(see tests/test_health_math.py). Everything is derived from the Profile, nothing
is a magic number buried in the bot.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import Profile


def bmr_mifflin_st_jeor(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Basal Metabolic Rate (kcal/day), Mifflin-St Jeor equation.

    men:   10*kg + 6.25*cm - 5*age + 5
    women: 10*kg + 6.25*cm - 5*age - 161
    """
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    return base + (5.0 if sex == "male" else -161.0)


def tdee(bmr: float, activity_factor: float) -> float:
    """Total Daily Energy Expenditure = maintenance calories."""
    return bmr * activity_factor


def bmi(weight_kg: float, height_cm: float) -> float:
    h = height_cm / 100.0
    return weight_kg / (h * h)


def protein_target_g(goal_weight_kg: float) -> int:
    """Protein target in grams/day.

    For fat loss we anchor protein to *goal* body weight at ~1.6 g/kg to protect
    muscle while in a deficit — using current (obese) weight would over-shoot.
    """
    return round(1.6 * goal_weight_kg)


@dataclass
class Targets:
    weight_kg: float
    bmi: float
    bmr: int
    tdee: int
    calorie_target: int
    protein_g: int
    fiber_g: int
    water_ml: int
    est_weekly_loss_kg: float


def compute_targets(profile: Profile, current_weight_kg: float | None = None) -> Targets:
    """Compute daily targets. Uses current weight if provided, else start weight."""
    weight = current_weight_kg if current_weight_kg else profile.start_weight_kg
    _bmr = bmr_mifflin_st_jeor(profile.sex, weight, profile.height_cm, profile.age)
    _tdee = tdee(_bmr, profile.activity_factor)

    # Never prescribe below a safe floor (1500 kcal for men, 1200 for women).
    floor = 1500 if profile.sex == "male" else 1200
    calorie_target = max(round(_tdee - profile.daily_deficit), floor)
    actual_deficit = _tdee - calorie_target
    # ~7700 kcal per kg of fat.
    weekly_loss = (actual_deficit * 7) / 7700.0

    return Targets(
        weight_kg=round(weight, 1),
        bmi=round(bmi(weight, profile.height_cm), 1),
        bmr=round(_bmr),
        tdee=round(_tdee),
        calorie_target=calorie_target,
        protein_g=protein_target_g(profile.goal_weight_kg),
        fiber_g=35,
        water_ml=3000,
        est_weekly_loss_kg=round(weekly_loss, 2),
    )


def bmi_category(value: float) -> str:
    # WHO Asian cut-offs (relevant for a Filipino user) are lower than the global ones.
    if value < 18.5:
        return "underweight"
    if value < 23:
        return "healthy (Asian scale)"
    if value < 27.5:
        return "overweight (Asian scale)"
    return "obese (Asian scale)"


def targets_summary(t: Targets) -> str:
    """Short human-readable block, used by the /plan and /progress commands."""
    return (
        f"Weight: {t.weight_kg} kg  |  BMI: {t.bmi} ({bmi_category(t.bmi)})\n"
        f"BMR (at rest): ~{t.bmr} kcal/day\n"
        f"Maintenance (TDEE): ~{t.tdee} kcal/day\n"
        f"\U0001f3af Daily target: ~{t.calorie_target} kcal\n"
        f"\U0001f356 Protein: ~{t.protein_g} g/day\n"
        f"\U0001f33e Fiber: ~{t.fiber_g} g/day   \U0001f4a7 Water: ~{t.water_ml/1000:.1f} L/day\n"
        f"\U0001f4c9 Expected loss at this intake: ~{t.est_weekly_loss_kg} kg/week"
    )


def build_plan(profile: Profile, current_weight_kg: float | None = None) -> str:
    """The full personalised plan (Filipino diet, Singapore context, quit-smoking)."""
    t = compute_targets(profile, current_weight_kg)
    return f"""\U0001f4cb *Your Health Plan*

{targets_summary(t)}

*How to eat (Filipino, in Singapore)*
Your cuisine is easy to make lean — the trick is method and portion, not giving up
the food you love.
• Rice: this is the biggest lever. Cut to ~1 cup cooked per meal (not 2-3). Try
  brown/red rice or mix half-and-half. In SG hawker centres ask for "less rice".
• Protein at every meal: grilled/boiled over fried. Bangus (milkfish), tilapia,
  chicken breast/thigh (skin off), lean pork, eggs, tofu/tokwa, monggo (mung beans).
• Rebuild favourites lighter: sinigang, tinola, nilaga, pinakbet, ginisang gulay,
  inihaw na isda — these are already lean. Go easy on sisig, lechon kawali, crispy
  pata, and sweet longganisa/tocino.
• Watch the liquids: soft drinks, kopi/teh with condensed milk, sago drinks, beer.
  Switch to kopi-o kosong / teh-o kosong (no sugar), water, or calamansi juice
  unsweetened. This alone can be 300-600 kcal/day.
• Hawker picks in SG: yong tau foo (soup, more veg + tofu, less fried, no noodles),
  soup-based dishes, thunder tea rice, grilled fish, chicken breast with less rice.
  Limit char kway teow, fried carrot cake, laksa, nasi lemak to occasional treats.
• Veg: aim for half the plate. Kangkong, sitaw, talong, upo, malunggay, pechay.

*How to move (starting from where you are, ~{t.weight_kg} kg)*
Joints first — low-impact until the weight comes down.
• Walking is your #1 tool: 20-30 min daily to start (SG is walkable but hot — go
  early morning or evening, or use mall/MRT-linked walkways in the heat). Build to
  8-10k steps/day.
• Swimming / aqua-walking 1-2x/week — excellent at your weight, easy on knees, and
  pools are everywhere in SG (ActiveSG).
• Strength 2x/week: bodyweight + bands to keep muscle while losing fat — sit-to-stand
  from a chair, wall push-ups, banded rows, glute bridges. Progress slowly.
• Rule of thumb: you can't out-exercise a bad diet. Food controls weight, exercise
  controls fitness, mood, and blood sugar. Do both, but win the food battle first.

*Quitting smoking (you said you plan to — this is the single biggest win)*
• Quitting + losing weight together is hard; if you must sequence, many people do
  better quitting first, because nicotine suppresses appetite and quitting can raise
  hunger. Plan for that: keep high-protein/high-fiber snacks and water ready.
• In Singapore: HPB's "I Quit" programme (free, WhatsApp/hotline support) and NRT
  (patches/gum) from polyclinics/pharmacies genuinely raise your odds. Ask your GP.
• Expect a small temporary weight bump when you quit — it is worth it and reverses.

*"Metabolism is not great"*
Most of what feels like a slow metabolism is (a) muscle loss over the years and
(b) under-counting food/drinks. Two fixes: hit the protein target to rebuild muscle,
and log honestly (that's what this bot + Sparky are for). Your BMR above (~{t.bmr})
is already accounted for.

*This week's 3 tiny wins* (don't overhaul everything at once)
1. Halve your rice and drop sugary drinks.
2. Walk 20-30 min every day.
3. Log every meal + your weight so we can see the trend.

_Not medical advice. With your weight, age, smoking history and plan to quit, please
run this past your GP — especially before intense exercise or if you have high blood
pressure, diabetes, or heart concerns._"""
