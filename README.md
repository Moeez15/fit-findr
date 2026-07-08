# FitFindr

FitFindr is a multi-tool AI agent that helps users find secondhand clothing pieces and figure out how to style them. Given a natural-language request, it searches a mock listings dataset, suggests an outfit that pairs the find with the user's existing wardrobe, and generates a shareable "fit card" caption — all in one pass, with graceful handling at every step where things can go wrong.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root:

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Run the tests:

```bash
pytest tests/
```

Run the CLI demo (happy path + no-results path):

```bash
python agent.py
```

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) -> list[dict]`

Searches the 40-item mock listings dataset (`data/listings.json`, loaded via `utils.data_loader.load_listings()`) for items matching the given keywords, filtered by size (case-insensitive substring match, so `"M"` matches `"S/M"`) and an inclusive price ceiling. Each listing is scored by keyword overlap between `description` and the listing's title/description/style_tags; results are sorted best-match-first. Listings scoring 0 are dropped. Returns a list of full listing dicts (`id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`), or `[]` if nothing matches.

### `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

Given a candidate listing and the user's wardrobe (`{"items": [...]}`), asks Groq's `llama-3.3-70b-versatile` to suggest 1–2 outfit combinations that pair the new item with specific named pieces from the wardrobe, including a short styling note. If `wardrobe["items"]` is empty, it switches to a different prompt asking for general styling advice about the item alone (what pairs well with it, what vibe it suits) instead of failing or returning nothing. Always returns a non-empty string.

### `create_fit_card(outfit: str, new_item: dict) -> str`

Given an outfit suggestion string and the listing dict, asks the LLM (temperature 1.0, to guarantee varied phrasing across calls) to write a 2–4 sentence, casual, OOTD-style social caption that naturally mentions the item name, price, and platform once each. If `outfit` is empty or whitespace-only, the function short-circuits before calling the LLM and returns a descriptive message telling the caller to run `suggest_outfit` first.

## Planning Loop

The planning loop lives in `agent.py`'s `run_agent(query, wardrobe)` and is intentionally a simple, linear pipeline with **one real decision point** — because that's where the agent's behavior actually needs to change based on what a tool returns:

1. **Parse** the query into `description`, `size`, and `max_price` using regex (a `"size X"` / bare-size-token pattern, and an `"under $N"` / `"$N"` price pattern). This is deterministic and fast — no LLM call needed just to extract structured fields from a short query.
2. **Call `search_listings`.**
   - If it returns `[]` → set `session["error"]` to a message that names the exact query and filters used, and **return immediately**. `suggest_outfit` and `create_fit_card` are never invoked with a missing item — this is the loop's one conditional branch, and it's the difference between an agent that reacts to its tools and one that runs a fixed script.
   - If it returns results → take the top-ranked match as `selected_item` and continue.
3. **Call `suggest_outfit(selected_item, wardrobe)`** — always reached once step 2 succeeds. The wardrobe-empty vs. wardrobe-populated branching happens *inside* the tool (it's a difference in prompt, not a difference in whether the planning loop calls the tool).
4. **Call `create_fit_card(outfit_suggestion, selected_item)`** — always reached after step 3, since `suggest_outfit` is guaranteed to return a non-empty string.
5. **Return the session.**

The loop "knows it's done" when either the early-return in step 2 fires, or all three of `selected_item`, `outfit_suggestion`, and `fit_card` are populated. This is deliberately simple rather than architecturally elaborate — see `planning.md`'s Planning Loop section for the full branch-by-branch spec and the ASCII architecture diagram.

## State Management

All state for one interaction lives in a single `session` dict (created by `_new_session()`) that's threaded through `run_agent()` by reference — no globals, no re-prompting the user mid-flow:

```python
{
    "query": ...,              # original user query
    "parsed": {...},           # description / size / max_price
    "search_results": [...],   # full ranked list from search_listings
    "selected_item": {...},    # search_results[0] — the exact dict passed to both later tools
    "wardrobe": {...},         # passed in by the caller
    "outfit_suggestion": "...",# passed as `outfit` into create_fit_card
    "fit_card": "...",         # final output
    "error": None,             # set only on early-exit
}
```

The same `selected_item` object flows unchanged into both `suggest_outfit` and `create_fit_card` — nothing is re-derived or re-entered between calls. `app.py`'s `handle_query()` and the CLI demo in `agent.py` both just read fields off the returned session dict to build their output.

## Error Handling

| Tool | Failure mode | Agent response |
|---|---|---|
| `search_listings` | No listings match the filters | Returns `[]`, never raises. The planning loop detects the empty list, builds a message naming the query and any size/price filters applied, and stops before calling the other two tools. Example (captured in `failure_modes_demo.txt`): `"No listings matched 'designer ballgound' (size XXS, under $5). Try removing the size filter, raising your budget, or using broader keywords."` |
| `suggest_outfit` | Wardrobe has no items | Detected *before* prompting the LLM; the tool swaps to a general-styling-advice prompt instead of asking the LLM to reference wardrobe pieces that don't exist. Still returns a normal non-empty string, so the planning loop proceeds exactly as it would with a full wardrobe. |
| `suggest_outfit` / `create_fit_card` | Groq API call raises (network/auth error) | Both tools wrap their API call in `try/except` and return a plain fallback string instead of propagating the exception. |
| `create_fit_card` | `outfit` is empty or whitespace-only | Checked before any LLM call; returns `"Can't create a fit card without an outfit suggestion — try running suggest_outfit first."` instead of raising. In the normal planning-loop flow this is unreachable (since `suggest_outfit` always returns non-empty), but it's exercised directly in `tests/test_tools.py` and in `failure_modes_demo.txt`. |

All three failure modes were triggered deliberately and their output captured in `failure_modes_demo.txt` (Milestone 5). None of them raise an unhandled exception or silently return nothing.

## Spec Reflection

Writing the tool specs in `planning.md` before touching `tools.py` made the failure-mode design decisions upfront rather than as afterthoughts caught by a crash — e.g., deciding that an empty wardrobe should change *which prompt* `suggest_outfit` sends (rather than returning a canned string) came out of writing the spec, not out of debugging a bad output later. The one place the implementation diverged slightly from the original plan was query parsing: the plan allowed for either regex or an LLM call, and regex proved sufficient and faster once the actual query formats (from `EXAMPLE_QUERIES` in `app.py`) were in hand — no ambiguity that needed LLM judgment.
