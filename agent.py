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

from tools import (
    check_price,
    create_fit_card,
    search_listings,
    style_profile_memory,
    suggest_outfit,
)


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
        "style_notes": "",           # saved or query-provided style context
        "relaxed_results": [],       # results used to diagnose a failed search
        "price_check": None,         # optional comparison result
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

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    session = _new_session(query, wardrobe)

    user_id = "user_001"
    try:
        saved_profile = style_profile_memory(user_id)
    except Exception:
        saved_profile = None
    if isinstance(saved_profile, dict):
        saved_wardrobe = saved_profile.get("wardrobe", {})
        saved_items = saved_wardrobe.get("items", []) if isinstance(saved_wardrobe, dict) else []
        if saved_items:
            session["wardrobe"] = saved_wardrobe
        session["style_notes"] = saved_profile.get("style_notes", "") or ""

    sentence_parts = re.split(r"([.!?])", str(query), maxsplit=1)
    first_sentence = sentence_parts[0]
    separator = sentence_parts[1] if len(sentence_parts) > 1 else ""
    remaining = sentence_parts[2] if len(sentence_parts) > 2 else ""
    if separator:
        style_context = remaining.strip()
    else:
        first_sentence = str(query)
        style_context = ""

    price_match = re.search(r"\bunder\s+\$?(\d+(?:\.\d+)?)\b|\$(\d+(?:\.\d+)?)", first_sentence, re.IGNORECASE)
    max_price = float(next(group for group in price_match.groups() if group)) if price_match else None

    size_match = re.search(r"\bsize\s+([A-Za-z0-9/]+)\b", first_sentence, re.IGNORECASE)
    if size_match:
        size = size_match.group(1)
    else:
        size_match = re.search(r"(?<![A-Za-z0-9])(?:S|M|L|XL)(?![A-Za-z0-9])", first_sentence, re.IGNORECASE)
        size = size_match.group(0) if size_match else None

    description = first_sentence
    description = re.sub(r"\bunder\s+\$?\d+(?:\.\d+)?\b", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\$\d+(?:\.\d+)?\b", "", description)
    if size_match:
        description = re.sub(
            rf"\bsize\s+{re.escape(size)}\b|(?<![A-Za-z0-9]){re.escape(size)}(?![A-Za-z0-9])",
            "",
            description,
            count=1,
            flags=re.IGNORECASE,
        )
    description = re.sub(r"\s+", " ", description).strip(" ,;:-")
    session["parsed"] = {"description": description, "size": size, "max_price": max_price}
    if style_context:
        session["style_notes"] = "; ".join(
            part for part in (session["style_notes"], style_context) if part
        )

    if not description:
        session["error"] = "I couldn't tell what you're looking for -- try naming the item."
        return session

    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results
    if not results:
        relaxed_price = (
            search_listings(description, size=size, max_price=None)
            if max_price is not None
            else []
        )
        if relaxed_price and max_price is not None:
            session["relaxed_results"] = relaxed_price
            cheapest = min(relaxed_price, key=lambda item: float(item.get("price", 0)))
            session["error"] = (
                f"Nothing matching '{description}' was found under ${max_price:g}. "
                f"The cheapest match is {cheapest.get('title', 'an item')} for "
                f"${float(cheapest.get('price', 0)):g} on {cheapest.get('platform', 'the marketplace')}."
            )
            return session

        relaxed_size = search_listings(description, size=None, max_price=max_price)
        if relaxed_size:
            session["relaxed_results"] = relaxed_size
            sizes = sorted({str(item.get("size", "unknown")) for item in relaxed_size})
            session["error"] = (
                f"Nothing matching '{description}' was found in size {size}. "
                f"Available sizes include {', '.join(sizes[:5])}."
            )
            return session

        all_keyword_matches = search_listings(description, size=None, max_price=None)
        if all_keyword_matches:
            session["relaxed_results"] = all_keyword_matches
        tags = sorted({tag for item in all_keyword_matches for tag in item.get("style_tags", [])})
        if not tags:
            tags = sorted({tag for item in search_listings("vintage", None, None) for tag in item.get("style_tags", [])})
        session["error"] = (
            f"I couldn't find a match for '{description}'. Try one of these styles: "
            f"{', '.join(tags[:5]) or 'vintage, grunge, y2k, or streetwear'}."
        )
        return session

    session["selected_item"] = results[0]

    try:
        price_result = check_price(session["selected_item"])
        if isinstance(price_result, dict) and price_result.get("verdict") != "not enough data":
            session["price_check"] = price_result
    except Exception:
        session["price_check"] = None

    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )
    if not isinstance(session["outfit_suggestion"], str) or not session["outfit_suggestion"].strip():
        session["error"] = "I couldn't put an outfit together for this one."
        return session

    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )
    try:
        style_profile_memory(
            user_id,
            wardrobe=session["wardrobe"],
            style_notes=session["style_notes"],
        )
    except Exception:
        pass
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
