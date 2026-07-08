# FitFindr 🛍️

An AI agent that helps you find secondhand clothing and figure out how to actually wear it. Describe what you're looking for, and FitFindr searches a listings dataset, suggests outfit pairings from your existing wardrobe, and writes a shareable "fit card" caption for the look — all through a simple Gradio UI.

## How it works

FitFindr runs a straight-line planning loop (`agent.py::run_agent`) over three tools:

1. **`search_listings`** — searches a 40-item mock listings dataset by keyword overlap, filtered by size and price ceiling. Returns the best matches ranked by relevance.
2. **`suggest_outfit`** — takes the top listing and your wardrobe, and asks an LLM to propose 1–2 outfit pairings using pieces you already own (or general styling advice if your wardrobe is empty).
3. **`create_fit_card`** — turns the outfit suggestion into a short, casual OOTD-style caption mentioning the item, price, and platform.

If a search returns no results, the loop short-circuits and surfaces a helpful error instead of calling the other tools. State flows through a single `session` dict so every intermediate result (parsed query, search results, selected item, outfit suggestion, fit card) is inspectable.

## Tech stack

- **Python 3.13**
- **Gradio** — web UI
- **Groq** (`llama-3.3-70b-versatile`) — LLM calls for outfit suggestions and captions
- **pytest** — tool-level tests

## Getting started

### Prerequisites

- Python 3.13+
- A [Groq API key](https://console.groq.com/keys)

### Setup

```bash
# Clone and enter the project
cd fit_findr

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key:

```
GROQ_API_KEY=your_key_here
```

### Run it

```bash
python app.py
```

Then open the local URL printed in your terminal (usually `http://localhost:7860`).

Try a query like:

- `vintage graphic tee under $30`
- `90s track jacket in size M`
- `flowy midi skirt under $40`

You can also run the agent from the command line without the UI:

```bash
python agent.py
```

This prints a happy-path run and a deliberate no-results run so you can see both branches of the planning loop.

### Run the tests

```bash
pytest
```

## Project structure

```
fit_findr/
├── agent.py              # Planning loop — orchestrates the three tools
├── app.py                # Gradio UI
├── tools.py              # search_listings, suggest_outfit, create_fit_card
├── data/
│   ├── listings.json         # Mock secondhand listings dataset
│   └── wardrobe_schema.json  # Example + empty wardrobe templates
├── utils/
│   └── data_loader.py     # Loads listings and wardrobe data
└── tests/
    └── test_tools.py      # Tool-level tests
```

## Notes

- The listings dataset is mocked (`data/listings.json`) — there's no live scraping or API integration with Depop/thredUp/Poshmark.
- Both LLM-backed tools fall back to a plain, non-LLM string if the Groq API call fails, so the agent never crashes on a network or auth error.
