"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

_SIZE_PATTERN = re.compile(
    r"\bsize\s+([a-z0-9/]+)\b|\b(xxs|xs|s|m|l|xl|xxl)\b(?!\w)",
    re.IGNORECASE,
)
_PRICE_PATTERN = re.compile(
    r"under\s*\$?\s*(\d+(?:\.\d+)?)|\$\s*(\d+(?:\.\d+)?)\s*(?:or\s*less|max|budget)?",
    re.IGNORECASE,
)


def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex-based parsing (documented in planning.md's Planning Loop /
    state design — chosen for speed and determinism over an extra LLM call).

    Returns a dict: {"description": str, "size": str | None, "max_price": float | None}
    """
    size = None
    size_match = _SIZE_PATTERN.search(query)
    if size_match:
        size = size_match.group(1) or size_match.group(2)

    max_price = None
    price_match = _PRICE_PATTERN.search(query)
    if price_match:
        raw = price_match.group(1) or price_match.group(2)
        if raw:
            max_price = float(raw)

    # Strip out the matched size/price fragments so they don't pollute the
    # keyword-overlap scoring in search_listings.
    description = query
    if size_match:
        description = description[: size_match.start()] + description[size_match.end():]
    price_match2 = _PRICE_PATTERN.search(description)
    if price_match2:
        description = description[: price_match2.start()] + description[price_match2.end():]

    description = description.strip(" ,.")
    if not description:
        description = query

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into description / size / max_price.
    session["parsed"] = _parse_query(query)

    # Step 3: search listings.
    results = search_listings(
        session["parsed"]["description"],
        size=session["parsed"]["size"],
        max_price=session["parsed"]["max_price"],
    )
    session["search_results"] = results

    if not results:
        filters = []
        if session["parsed"]["size"]:
            filters.append(f"size {session['parsed']['size']}")
        if session["parsed"]["max_price"] is not None:
            filters.append(f"under ${session['parsed']['max_price']:.0f}")
        filter_str = f" ({', '.join(filters)})" if filters else ""
        session["error"] = (
            f"No listings matched '{session['parsed']['description']}'{filter_str}. "
            "Try removing the size filter, raising your budget, or using broader keywords."
        )
        return session  # early exit — do not call suggest_outfit / create_fit_card

    # Step 4: select the top result.
    session["selected_item"] = results[0]

    # Step 5: suggest an outfit using the selected item and wardrobe.
    session["outfit_suggestion"] = suggest_outfit(session["selected_item"], wardrobe)

    # Step 6: generate the shareable fit card.
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])

    # Step 7: return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
