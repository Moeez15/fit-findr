"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()

    # Filter by price and size first — cheap, exact filters.
    candidates = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and size.strip().lower() not in item["size"].lower():
            continue
        candidates.append(item)

    # Score remaining candidates by keyword overlap with `description`.
    keywords = {w for w in re.findall(r"[a-z0-9]+", description.lower()) if w}

    scored = []
    for item in candidates:
        haystack = " ".join(
            [item["title"], item["description"], " ".join(item["style_tags"])]
        ).lower()
        haystack_words = set(re.findall(r"[a-z0-9]+", haystack))
        score = len(keywords & haystack_words)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    item_desc = (
        f"{new_item.get('title', 'this item')} — {new_item.get('description', '')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', []))}, "
        f"style: {', '.join(new_item.get('style_tags', []))})"
    )

    items = wardrobe.get("items", [])

    if not items:
        prompt = (
            "A user is considering buying this secondhand item:\n"
            f"{item_desc}\n\n"
            "They don't have any wardrobe items on file yet. Give them 2-3 sentences "
            "of general styling advice: what kinds of pieces would pair well with this "
            "item, and what overall vibe/aesthetic it suits. Be specific and concrete, "
            "not generic."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {w['name']} (category: {w['category']}, colors: {', '.join(w.get('colors', []))}, "
            f"style: {', '.join(w.get('style_tags', []))}"
            + (f", notes: {w['notes']}" if w.get("notes") else "")
            + ")"
            for w in items
        )
        prompt = (
            "A user is considering buying this secondhand item:\n"
            f"{item_desc}\n\n"
            "Here is their current wardrobe:\n"
            f"{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfit combinations that pair the new item with "
            "specific named pieces from their wardrobe above. Reference the wardrobe "
            "items by name. Include a short styling note (how to wear it, what vibe it "
            "creates). Keep it to 2-4 sentences total."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return (
            "Couldn't generate a styling suggestion right now — here's the item on "
            "its own: consider pairing it with neutral basics you already own."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)
    """
    if not outfit or not outfit.strip():
        return (
            "Can't create a fit card without an outfit suggestion — "
            "try running suggest_outfit first."
        )

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "a resale platform")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "a great price"

    prompt = (
        f"Write a short, casual outfit caption (2-4 sentences) like a real Instagram or "
        f"TikTok OOTD post — not a product description. It should:\n"
        f"- Mention the item name (\"{title}\"), the price ({price_str}), and the "
        f"platform ({platform}) naturally, each once\n"
        f"- Capture the outfit vibe in specific terms\n"
        f"- Sound authentic and casual, like a real person captioning their post\n\n"
        f"Outfit details to draw from:\n{outfit}\n\n"
        f"Write only the caption, nothing else."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return (
            f"Thrifted the {title} for {price_str} on {platform} — "
            "full look in my stories."
        )
