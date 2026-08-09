"""The AI health consultant.

Answers free-text questions via OpenRouter (OpenAI-compatible chat API), grounded
with fresh web results from Firecrawl's search endpoint when a key is configured.
Personalised with the user's profile so advice fits a Filipino, Singapore-based,
120 kg, quitting-smoker context.
"""
from __future__ import annotations

from typing import List, Optional

import httpx

from config import Profile, Settings
from health_math import compute_targets, targets_summary


def _system_prompt(profile: Profile) -> str:
    t = compute_targets(profile)
    return (
        "You are a supportive, practical health and fitness coach. You give concrete, "
        "actionable advice and you are honest, never preachy. Keep answers concise and "
        "usable in a Telegram chat (short paragraphs, a few bullets, no walls of text). "
        "Always ground advice in the user's real context below.\n\n"
        "USER CONTEXT:\n"
        f"- {profile.ethnicity} man, based in {profile.location}, age {profile.age}.\n"
        f"- Height {profile.height_cm:.0f} cm, weight ~{profile.start_weight_kg:.0f} kg, "
        f"goal {profile.goal_weight_kg:.0f} kg.\n"
        f"- Eats large portions, feels his metabolism is slow, exercises occasionally.\n"
        f"- Smoker who plans to quit.\n"
        f"- Current daily targets: {targets_summary(t)}\n\n"
        "GUIDELINES:\n"
        "- Favour Filipino foods and Singapore hawker/grocery options in examples.\n"
        "- Be realistic about quitting smoking + weight loss happening together.\n"
        "- Prefer low-impact exercise given his current weight.\n"
        "- When web sources are provided, use them and cite the source titles.\n"
        "- You are not a doctor; for medical issues, symptoms, or medication, tell him "
        "to see his GP or Singapore polyclinic. Do not diagnose.\n"
    )


async def _firecrawl_search(settings: Settings, query: str, limit: int = 4) -> str:
    """Return a compact, cited context block from Firecrawl search, or '' if unavailable."""
    if not settings.firecrawl_api_key:
        return ""
    url = f"{settings.firecrawl_base_url.rstrip('/')}/v1/search"
    headers = {"Authorization": f"Bearer {settings.firecrawl_api_key}"}
    payload = {
        "query": query,
        "limit": limit,
        "scrapeOptions": {"formats": ["markdown"]},
    }
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return ""  # web grounding is best-effort; never block the answer on it

    results = data.get("data") or data.get("results") or []
    blocks: List[str] = []
    for r in results[:limit]:
        title = r.get("title") or r.get("url") or "source"
        content = (r.get("markdown") or r.get("description") or "").strip()
        if len(content) > 1200:  # keep the prompt lean
            content = content[:1200] + "…"
        url_ = r.get("url", "")
        blocks.append(f"### {title}\n({url_})\n{content}")
    if not blocks:
        return ""
    return "FRESH WEB RESULTS (cite these where relevant):\n\n" + "\n\n".join(blocks)


async def ask(
    settings: Settings,
    profile: Profile,
    question: str,
    history: Optional[List[dict]] = None,
    use_web: bool = True,
) -> str:
    """Answer a question. ``history`` is a list of {role, content} for short memory."""
    if not settings.openrouter_api_key:
        return (
            "The AI consultant isn't configured yet. Add OPENROUTER_API_KEY to your "
            ".env to enable advice. (Logging, calorie lookup and /plan still work.)"
        )

    web_context = await _firecrawl_search(settings, question) if use_web else ""

    messages: List[dict] = [{"role": "system", "content": _system_prompt(profile)}]
    if history:
        messages.extend(history[-6:])  # keep the last few turns only
    user_content = question
    if web_context:
        user_content = f"{question}\n\n---\n{web_context}"
    messages.append({"role": "user", "content": user_content})

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        # Optional attribution headers recommended by OpenRouter:
        "HTTP-Referer": "https://github.com/Carlo34G/Python",
        "X-Title": "Health Companion",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 700,
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        answer = data["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as exc:
        return f"⚠️ AI request failed ({exc.response.status_code}). Check your OpenRouter key/model."
    except Exception as exc:
        return f"⚠️ AI request failed: {exc}"

    if web_context:
        answer += "\n\n_Answer grounded with a live web search._"
    return answer
