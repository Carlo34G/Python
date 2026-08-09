"""Unit tests for the energy/nutrition maths — no network required.

Run:  cd health_companion && python -m pytest -q
  or:  python tests/test_health_math.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Profile
from health_math import (
    bmi,
    bmi_category,
    bmr_mifflin_st_jeor,
    compute_targets,
    protein_target_g,
    tdee,
)

PROFILE = Profile(
    sex="male", age=50, height_cm=175.0,
    start_weight_kg=120.0, goal_weight_kg=95.0,
    activity_factor=1.35, daily_deficit=700,
)


def approx(a, b, tol=0.5):
    return abs(a - b) <= tol


def test_bmr_male():
    # 10*120 + 6.25*175 - 5*50 + 5 = 2048.75
    assert approx(bmr_mifflin_st_jeor("male", 120, 175, 50), 2048.75)


def test_bmr_female_is_lower_by_166():
    male = bmr_mifflin_st_jeor("male", 120, 175, 50)
    female = bmr_mifflin_st_jeor("female", 120, 175, 50)
    assert approx(male - female, 166.0)  # +5 vs -161


def test_tdee():
    assert approx(tdee(2048.75, 1.35), 2765.81)


def test_bmi():
    assert approx(bmi(120, 175), 39.18, tol=0.05)


def test_bmi_category_asian_scale():
    assert bmi_category(39.2) == "obese (Asian scale)"
    assert bmi_category(22.0) == "healthy (Asian scale)"


def test_protein_anchored_to_goal_weight():
    # 1.6 g/kg * 95 kg goal = 152 g (not anchored to 120 kg current weight)
    assert protein_target_g(95) == 152


def test_compute_targets_full():
    t = compute_targets(PROFILE)
    assert t.bmr == 2049
    assert t.tdee == 2766
    assert t.calorie_target == 2066  # 2766 - 700
    assert t.protein_g == 152
    assert t.est_weekly_loss_kg > 0


def test_calorie_floor_respected():
    # Absurd deficit must not push a man below the 1500 kcal floor.
    p = Profile(sex="male", age=50, height_cm=175.0, start_weight_kg=120.0,
                goal_weight_kg=95.0, activity_factor=1.2, daily_deficit=5000)
    assert compute_targets(p).calorie_target == 1500


def test_lower_weight_lowers_target():
    heavy = compute_targets(PROFILE, current_weight_kg=120)
    light = compute_targets(PROFILE, current_weight_kg=100)
    assert light.calorie_target < heavy.calorie_target


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
