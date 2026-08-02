"""Health Companion — Telegram bot entry point.

Run with:  python bot.py   (uses long-polling, so no inbound ports/webhook needed —
ideal for a home server like srv-02 behind NAT).

Commands:
  /start, /help        show help
  /plan                your personalised targets + Filipino/Singapore/quit-smoking plan
  /weight 118          log today's weight (kg); syncs to Sparky if configured
  /food <what you ate> look up calories/macros, log it, show today's total vs target
  /progress            weight trend + today's calories vs target
  /advice <question>   ask the AI consultant (or just send any message)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import consultant
import nutrition
import store
from config import profile, settings
from health_math import build_plan, compute_targets, targets_summary
from sparky import sparky

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s | %(message)s", level=logging.INFO
)
log = logging.getLogger("health_companion")

# Very small per-user rolling chat memory for the consultant.
_history: Dict[int, List[dict]] = defaultdict(list)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
async def _reply(update: Update, text: str) -> None:
    """Send Markdown, falling back to plain text if Telegram rejects the markup."""
    msg = update.effective_message
    try:
        await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except Exception:
        await msg.reply_text(text, disable_web_page_preview=True)


def _authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user) and settings.is_user_allowed(user.id)


async def _deny(update: Update) -> None:
    uid = update.effective_user.id if update.effective_user else "?"
    await update.effective_message.reply_text(
        f"Sorry, you're not authorised to use this bot.\nYour Telegram ID is `{uid}` — "
        "add it to TELEGRAM_ALLOWED_USER_IDS to enable access.",
        parse_mode=ParseMode.MARKDOWN,
    )


def _sparkline(values: List[float]) -> str:
    if len(values) < 2:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    if hi == lo:
        return blocks[0] * len(values)
    return "".join(blocks[int((v - lo) / (hi - lo) * (len(blocks) - 1))] for v in values)


# --------------------------------------------------------------------------- #
# command handlers
# --------------------------------------------------------------------------- #
HELP = (
    "\U0001f34f *Health Companion*\n"
    "Your Sparky-connected coach. Commands:\n\n"
    "• `/plan` — your targets + food/exercise/quit-smoking plan\n"
    "• `/weight 118` — log today's weight (kg)\n"
    "• `/food 1 cup rice, grilled chicken thigh` — calories + macros, logged\n"
    "• `/progress` — weight trend + today's calories vs target\n"
    "• `/advice <question>` — ask me anything (or just send a message)\n\n"
    "_Not medical advice — see your GP for medical concerns._"
)


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return await _deny(update)
    await _reply(update, HELP)


async def cmd_plan(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return await _deny(update)
    current = store.latest_weight(update.effective_user.id)
    await _reply(update, build_plan(profile, current))


async def cmd_weight(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return await _deny(update)
    if not ctx.args:
        return await _reply(update, "Usage: `/weight 118`  (kilograms)")
    raw = ctx.args[0].replace("kg", "").replace(",", ".").strip()
    try:
        kg = float(raw)
    except ValueError:
        return await _reply(update, "That doesn't look like a number. Try `/weight 118`.")
    if not (30 <= kg <= 400):
        return await _reply(update, "That weight looks out of range. Enter kilograms, e.g. `/weight 118`.")

    uid = update.effective_user.id
    store.add_weight(uid, kg)
    status = await sparky.push_weight(kg)

    t = compute_targets(profile, kg)
    delta_line = ""
    hist = store.weight_history(uid, limit=2)
    if len(hist) >= 2:
        diff = round(hist[-1][1] - hist[-2][1], 1)
        if diff != 0:
            arrow = "\U0001f4c9" if diff < 0 else "\U0001f4c8"
            delta_line = f"\n{arrow} {diff:+.1f} kg vs last entry."
    to_goal = round(kg - profile.goal_weight_kg, 1)
    sync = f"\n_({status.detail})_" if sparky.configured else ""
    await _reply(
        update,
        f"✅ Logged *{kg:.1f} kg* today.{delta_line}\n"
        f"BMI now {t.bmi}. {to_goal:+.1f} kg to your {profile.goal_weight_kg:.0f} kg goal.{sync}",
    )


async def cmd_food(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return await _deny(update)
    query = " ".join(ctx.args).strip()
    if not query:
        return await _reply(update, "Usage: `/food 1 cup rice, grilled chicken thigh`")

    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    result = await nutrition.lookup_food(query)
    if result.error:
        return await _reply(update, nutrition.format_result(result))

    uid = update.effective_user.id
    store.add_food(uid, query, result.total_calories, result.total_protein)
    await sparky.push_food(query, result.total_calories, result.total_protein)

    total_cals, total_protein = store.calories_on(uid)
    t = compute_targets(profile, store.latest_weight(uid))
    remaining = t.calorie_target - total_cals
    budget = (
        f"\n\n\U0001f4ca Today: *{total_cals:.0f}/{t.calorie_target} kcal* "
        f"({remaining:+.0f} left), protein {total_protein:.0f}/{t.protein_g} g"
    )
    await _reply(update, nutrition.format_result(result) + budget)


async def cmd_progress(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return await _deny(update)
    uid = update.effective_user.id
    hist = store.weight_history(uid, limit=30)
    if not hist:
        return await _reply(update, "No weigh-ins yet. Log one with `/weight 118`.")

    weights = [w for _, w in hist]
    first, last = weights[0], weights[-1]
    change = round(last - first, 1)
    spark = _sparkline(weights)
    t = compute_targets(profile, last)
    cals, protein = store.calories_on(uid)

    lines = [
        f"\U0001f4c8 *Progress* (last {len(hist)} weigh-ins)",
        f"{first:.1f} → {last:.1f} kg  ({change:+.1f} kg)",
    ]
    if spark:
        lines.append(f"`{spark}`")
    lines.append("")
    lines.append(targets_summary(t))
    lines.append("")
    lines.append(
        f"\U0001f37d Today so far: {cals:.0f}/{t.calorie_target} kcal, "
        f"protein {protein:.0f}/{t.protein_g} g"
    )
    lines.append("\n_Full charts live in your Sparky Fitness portal._")
    await _reply(update, "\n".join(lines))


async def cmd_advice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return await _deny(update)
    question = " ".join(ctx.args).strip()
    if not question:
        return await _reply(update, "Ask me something, e.g. `/advice best hawker lunch under 600 kcal?`")
    await _handle_question(update, ctx, question)


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return await _deny(update)
    text = (update.effective_message.text or "").strip()
    if text:
        await _handle_question(update, ctx, text)


async def _handle_question(update: Update, ctx: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    uid = update.effective_user.id
    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    answer = await consultant.ask(settings, profile, question, history=_history[uid])
    # update rolling memory
    _history[uid].append({"role": "user", "content": question})
    _history[uid].append({"role": "assistant", "content": answer})
    _history[uid] = _history[uid][-8:]
    await _reply(update, answer)


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #
def main() -> None:
    if not settings.telegram_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
        )
    store.init_db()

    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("weight", cmd_weight))
    app.add_handler(CommandHandler("food", cmd_food))
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(CommandHandler("advice", cmd_advice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Health Companion starting (Sparky sync: %s)…",
             "on" if sparky.configured else "off")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
