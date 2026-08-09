# Health Companion 🍏

A personal, self-hosted **Telegram health coach** that sits *around* your existing
[SparkyFitness](https://github.com/CodeWithCJ/SparkyFitness) instance. Log your
weight and food from Telegram, get calorie/macro lookups, ask an AI consultant that
searches the live web for grounded answers, and get a plan tailored to **you** —
Filipino, based in Singapore, ~120 kg, 5′9″, quitting smoking.

It does **not** duplicate Sparky's web portal — Sparky already gives you the charts,
goals, and food database. This bot is the quick-input + advice layer you were missing.

---

## What it does

| Command | What happens |
|---|---|
| `/plan` | Your BMR/TDEE, daily calorie + protein targets, and a Filipino/Singapore food + low-impact exercise + quit-smoking plan |
| `/weight 118` | Logs today's weight, shows BMI + distance to goal, syncs to Sparky (best-effort) |
| `/food 1 cup rice, grilled chicken thigh` | Looks up calories/macros, logs it, shows today's total vs your target |
| `/progress` | Weight trend (with a sparkline) + today's calories vs target |
| `/advice <question>` *(or just send any message)* | AI consultant answers, grounded with a live web search |

Local **SQLite is the source of truth**, so nothing is lost even if Sparky is down.
Sparky sync is layered on top and fails silently if unreachable.

---

## ⚠️ Two things to know first (from your setup)

### 1. Your "wrong server" issue in Sparky is a config fix, not a rebuild
When you renamed the host, the thing that breaks is the **trusted origin / frontend
URL**, not the internal wiring. In your Sparky `docker/.env`:

- **`SPARKY_FITNESS_FRONTEND_URL`** → set to the URL you actually browse to now
  (e.g. `http://srv-02:3004` or your new hostname/domain). Wrong value = login/CORS fails.
- **`SPARKY_FITNESS_EXTRA_TRUSTED_ORIGINS`** → add any other hostnames/IPs you use
  (comma-separated).
- **`SPARKY_FITNESS_SERVER_HOST=sparkyfitness-server`** → **leave this alone.** It's the
  internal Docker service name, *not* your machine's hostname. Don't "correct" it.
- Using OIDC login? Update the callback/redirect URLs too.
- Then: `docker compose down && docker compose up -d`.

### 2. Your "no good calorie service" problem — enable a provider *in Sparky*
Sparky already ships **Nutritionix, OpenFoodFacts, USDA, FatSecret** as food providers.
**Nutritionix** is the one that fixes your complaint (fast, great for whole foods like
rice/chicken, does barcodes). Enable it inside Sparky's settings. This bot uses the
**same Nutritionix key** for its `/food` lookups, so the two stay consistent.

---

## Setup

### Prerequisites (get these keys)
1. **Telegram bot token** — message [@BotFather](https://t.me/BotFather) → `/newbot`.
2. **Your Telegram user ID** — message [@userinfobot](https://t.me/userinfobot).
3. **OpenRouter API key** — <https://openrouter.ai/keys> (for the AI consultant).
4. **Firecrawl API key** *(optional)* — <https://firecrawl.dev> (for web-grounded answers).
5. **Nutritionix App ID + Key** *(optional but recommended)* — <https://developer.nutritionix.com>.

### Configure
```bash
cd health_companion
cp .env.example .env
# edit .env — at minimum set TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, OPENROUTER_API_KEY
```
Check the profile block in `.env` — especially **`USER_SEX`** (the default `male` is an
assumption you should confirm), age, height, and goal weight. These drive your targets.

### Run it — Docker (recommended for srv-02)
```bash
docker compose up -d --build
docker compose logs -f health-companion
```

### Run it — plain Python
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```
It uses **long-polling**, so no inbound ports or webhooks are needed — perfect for a
home server behind NAT.

Then open Telegram, find your bot, and send `/start`.

---

## Sparky sync details

`sparky.py` logs weight and food to Sparky using JWT login (email/password) or an API
key with `health_data_write`. Because Sparky's REST API is still **beta**, the exact
routes can vary between versions. If sync isn't landing, adjust the
**CONFIGURABLE ENDPOINTS** block at the top of `sparky.py`:

```python
LOGIN_PATH  = "/api/auth/login"
WEIGHT_PATH = "/api/measurements/weight"
FOOD_PATH   = "/api/food/diary"
```

Sync failures never break the bot — your data is always safe in the local SQLite DB,
and Sparky's own portal remains your dashboard for charts and trends.

---

## Tests
```bash
python -m pytest -q          # or: python tests/test_health_math.py
```
The energy/target maths (Mifflin-St Jeor BMR, TDEE, calorie floor, protein anchoring)
are fully unit-tested with no network needed.

---

## A note on the health advice
This bot gives general wellness guidance, not medical advice. Given your weight, age,
smoking history, and plan to quit, please run the plan past your GP or a Singapore
polyclinic — especially before intense exercise, or if you have high blood pressure,
diabetes, or heart concerns. Singapore's HPB **"I Quit"** programme (free) is a strong
support for the smoking side.

## Files
```
health_companion/
├── bot.py            # Telegram entry point + command handlers
├── config.py         # env-driven settings + your profile
├── health_math.py    # BMR/TDEE/targets + the personalised plan (pure, tested)
├── nutrition.py      # calorie lookup: Nutritionix → OpenFoodFacts fallback
├── consultant.py     # OpenRouter chat + Firecrawl web grounding
├── store.py          # local SQLite (source of truth)
├── sparky.py         # best-effort SparkyFitness sync
├── tests/            # unit tests for the maths
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
