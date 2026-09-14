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

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import get_empty_wardrobe, load_listings

load_dotenv()


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

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    if not description or not str(description).strip():
        return []

    listings = load_listings()

    normalized_size = str(size).strip().lower() if size is not None else None
    max_price_value = float(max_price) if max_price is not None else None

    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "with",
        "for",
        "in",
        "on",
        "of",
        "to",
        "at",
        "it",
        "is",
        "my",
        "me",
        "wear",
        "wearing",
        "look",
        "style",
        "outfit",
    }
    keywords = [
        token
        for token in re.findall(r"[a-z0-9]+", str(description).lower())
        if token not in stop_words and token.strip()
    ]

    if not keywords:
        return []

    scored_listings = []
    condition_rank = {"excellent": 3, "good": 2, "fair": 1}

    for listing in listings:
        price = listing.get("price")
        if max_price_value is not None and price is not None and float(price) > max_price_value:
            continue

        if normalized_size is not None:
            listing_size = str(listing.get("size", "")).lower()
            if normalized_size not in listing_size:
                continue

        title = " ".join(str(listing.get("title", "")).lower().split())
        listing_description = " ".join(
            str(listing.get("description", "")).lower().split()
        )
        style_tags = [
            " ".join(str(tag).lower().split()) for tag in listing.get("style_tags", [])
        ]
        colors = [
            " ".join(str(color).lower().split()) for color in listing.get("colors", [])
        ]
        brand = " ".join(str(listing.get("brand") or "").lower().split())

        score = 0
        for keyword in keywords:
            if keyword in title:
                score += 3
                continue

            if any(keyword in tag for tag in style_tags):
                score += 2
                continue

            combined_text = f"{listing_description} {' '.join(colors)} {brand}"
            if keyword in combined_text:
                score += 1

        if score == 0:
            continue

        condition = str(listing.get("condition", "")).lower()
        scored_listings.append(
            {
                "listing": listing,
                "score": score,
                "condition_rank": condition_rank.get(condition, 0),
            }
        )

    scored_listings.sort(
        key=lambda entry: (
            -entry["score"],
            -entry["condition_rank"],
            float(entry["listing"].get("price", 0) or 0),
        )
    )

    return [entry["listing"] for entry in scored_listings]


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

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    if not isinstance(new_item, dict):
        return "I need a valid thrift listing to suggest an outfit."

    wardrobe_items = []
    if isinstance(wardrobe, dict):
        wardrobe_items = wardrobe.get("items", []) or []

    item_title = str(new_item.get("title") or "this thrifted piece")
    item_category = str(new_item.get("category") or "piece")
    item_colors = ", ".join(str(color) for color in new_item.get("colors", [])[:3]) or "neutral"
    item_tags = ", ".join(str(tag) for tag in new_item.get("style_tags", [])[:4]) or "casual"
    item_price = new_item.get("price")
    item_price_text = f" for ${item_price}" if item_price is not None else ""

    fallback = (
        f"This {item_category} ({item_title}{item_price_text}) leans {item_tags} and works best "
        f"with a relaxed bottom, chunky shoes, and a simple layer in a complementary tone. "
        f"Its {item_colors} palette makes it easy to pair with denim, black basics, or earthy neutrals."
    )

    system_prompt = (
        "You are a fashion stylist helping someone build outfits around a thrifted find. "
        "Give 1-2 specific outfit ideas in plain English. Keep it concise but vivid. "
        "Mention the actual pieces the user owns when available. "
        "Do not mention AI or give generic filler."
    )

    if not wardrobe_items:
        system_prompt += (
            f"\nItem being styled: {item_title} ({item_category}), colors: {item_colors}, "
            f"style tags: {item_tags}. "
            "Suggest general outfit ideas for what kinds of bottoms, shoes, outerwear, and vibe would fit."
        )
    else:
        wardrobe_summary = []
        for item in wardrobe_items[:10]:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or "Unnamed piece"
            category = item.get("category") or "piece"
            colors = ", ".join(str(color) for color in item.get("colors", [])[:3]) or "neutral"
            tags = ", ".join(str(tag) for tag in item.get("style_tags", [])[:4]) or "everyday"
            notes = item.get("notes")
            entry = f"- {name} ({category}, colors: {colors}, tags: {tags})"
            if notes:
                entry += f" — {notes}"
            wardrobe_summary.append(entry)

        if wardrobe_summary:
            system_prompt += (
                f"\nItem being styled: {item_title} ({item_category}), colors: {item_colors}, "
                f"style tags: {item_tags}. "
                "User's wardrobe:\n" + "\n".join(wardrobe_summary) + "\n"
                "Suggest 1-2 outfit combinations using the item and the named wardrobe pieces."
            )
        else:
            system_prompt += (
                f"\nItem being styled: {item_title} ({item_category}), colors: {item_colors}, "
                f"style tags: {item_tags}. "
                "The wardrobe is empty, so suggest general outfit ideas for what kinds of bottoms, shoes, outerwear, and vibe would fit."
            )

    try:
        client = _get_groq_client()
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Give me the outfit suggestions."},
            ],
            temperature=0.7,
            max_tokens=220,
        )
        response = completion.choices[0].message.content
        if isinstance(response, str) and response.strip():
            return response.strip()
    except Exception:
        pass

    return fallback


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

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not isinstance(outfit, str) or not outfit.strip():
        return "I need an outfit suggestion before I can write a fit card."

    if not isinstance(new_item, dict):
        return "I need the thrifted item details to write a fit card."

    item_title = str(new_item.get("title") or "this piece")
    item_price = new_item.get("price")
    item_platform = str(new_item.get("platform") or "the platform")
    item_colors = ", ".join(str(color) for color in new_item.get("colors", [])[:3]) or "neutral"
    item_tags = ", ".join(str(tag) for tag in new_item.get("style_tags", [])[:4]) or "casual"

    if item_price is None:
        return "I need the item's price to write a fit card."

    if not item_platform or item_platform == "None":
        return "I need the platform name to write a fit card."

    prompt = (
        "Write a short, casual thrift-fit caption in 2-4 sentences. "
        "It should feel like a real OOTD/TikTok caption, not a product description. "
        "Use the item name, price, and platform naturally once each. "
        "Capture the outfit vibe in specific terms and make it feel authentic. "
        "Do not use emoji or hashtags. "
        "Keep it natural and a little personal."
    )
    prompt += (
        f"\nItem title: {item_title}\n"
        f"Price: ${item_price}\n"
        f"Platform: {item_platform}\n"
        f"Colors: {item_colors}\n"
        f"Style tags: {item_tags}\n"
        f"Outfit suggestion: {outfit.strip()}"
    )

    try:
        client = _get_groq_client()
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Write the fit card now."},
            ],
            temperature=1.0,
            max_tokens=180,
        )
        response = completion.choices[0].message.content.strip()
        if response:
            return response
    except Exception:
        pass

    return (
        f"Found this {item_title} for ${item_price} on {item_platform}, and the vibe is {item_tags}. "
        f"It feels like a {item_colors}-leaning, easy thrift win that makes the whole outfit feel a little more put together."
    )


# ── Tool 4: check_price ───────────────────────────────────────────────────────

def check_price(new_item: dict, min_comps: int = 3) -> dict:
    """
    Estimate whether a thrifted item is priced fairly relative to comparable
    listings in the dataset.

    Args:
        new_item: The listing dict being checked.
        min_comps: Minimum number of comparable listings required before the
                   tool will give a verdict. If fewer are found, it should
                   return a "not enough data" verdict instead of guessing.

    Returns:
        A dict with:
            - verdict: "good deal", "about right", "overpriced", or
                       "not enough data"
            - avg_comp_price: Average comparable price, or None if insufficient data
            - comp_count: Number of comparable listings found
            - reason: Short explanation of the verdict

    TODO:
        1. Filter comparable listings by category and at least two overlapping
           style_tags.
        2. Ensure enough matching comps exist for the requested threshold.
        3. Compare the item's price to the average comparable price.
        4. Return a verdict dict with clear, user-facing reasoning.

    Before writing code, fill in the Tool 4 section of planning.md.
    """
    if not isinstance(new_item, dict):
        return {
            "verdict": "not enough data",
            "avg_comp_price": None,
            "comp_count": 0,
            "reason": "I need a valid listing to compare prices.",
        }

    item_category = str(new_item.get("category") or "").strip().lower()
    item_style_tags = {
        str(tag).strip().lower()
        for tag in new_item.get("style_tags", [])
        if str(tag).strip()
    }
    item_price = new_item.get("price")

    if not item_category or not item_style_tags or item_price is None:
        return {
            "verdict": "not enough data",
            "avg_comp_price": None,
            "comp_count": 0,
            "reason": "This listing is missing category, style tags, or price.",
        }

    comparable = []
    for listing in load_listings():
        if listing.get("category") is None:
            continue
        if str(listing.get("category", "")).strip().lower() != item_category:
            continue

        listing_tags = {
            str(tag).strip().lower()
            for tag in listing.get("style_tags", [])
            if str(tag).strip()
        }
        overlap = item_style_tags & listing_tags
        if len(overlap) < 2:
            continue

        comparable.append(float(listing.get("price", 0) or 0))

    comp_count = len(comparable)
    if comp_count < max(1, min_comps):
        return {
            "verdict": "not enough data",
            "avg_comp_price": None if comp_count == 0 else round(sum(comparable) / comp_count, 2),
            "comp_count": comp_count,
            "reason": (
                f"Only found {comp_count} comparable listing(s), so I don't have enough data to judge this price confidently."
            ),
        }

    avg_comp_price = round(sum(comparable) / comp_count, 2)
    item_price_value = float(item_price)

    if item_price_value < avg_comp_price * 0.9:
        verdict = "good deal"
    elif item_price_value > avg_comp_price * 1.1:
        verdict = "overpriced"
    else:
        verdict = "about right"

    if item_price_value < avg_comp_price:
        price_note = "below"
    else:
        price_note = "above"

    reason = (
        f"${item_price_value:.2f} is {price_note} the comparable average of ${avg_comp_price:.2f} "
        f"across {comp_count} similar listings."
    )

    return {
        "verdict": verdict,
        "avg_comp_price": avg_comp_price,
        "comp_count": comp_count,
        "reason": reason,
    }


# ── Tool 5: style_profile_memory ────────────────────────────────────────────────

def style_profile_memory(
    user_id: str,
    wardrobe: dict | None = None,
    style_notes: str | None = None,
) -> dict | str:
    """
    Save a user's wardrobe/style profile to disk or load one back from disk.

    Args:
        user_id: Identifier for the user's profile file.
        wardrobe: Wardrobe dict to save. If None, the function loads a saved
                  profile instead.
        style_notes: Optional freeform notes describing the user's style.

    Returns:
        - In load mode: a dict shaped like {"wardrobe": ..., "style_notes": ...}
        - In save mode: a confirmation string describing the saved profile

    TODO:
        1. If wardrobe is None, try to load the profile for user_id.
        2. If no profile exists, return an empty wardrobe and empty notes.
        3. If wardrobe is provided, save it alongside style_notes to a JSON file.
        4. Handle corrupted or unreadable files by falling back safely.

    Before writing code, fill in the Tool 5 section of planning.md.
    """
    profile_dir = os.path.join(os.path.dirname(__file__), "profiles")
    os.makedirs(profile_dir, exist_ok=True)
    profile_path = os.path.join(profile_dir, f"{user_id}.json")
    empty_profile = {"wardrobe": get_empty_wardrobe(), "style_notes": ""}

    if wardrobe is None:
        try:
            if not os.path.exists(profile_path):
                return empty_profile

            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            wardrobe_data = data.get("wardrobe", get_empty_wardrobe())
            notes = data.get("style_notes", "")
            return {"wardrobe": wardrobe_data, "style_notes": notes}
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
            return empty_profile

    if not user_id or not str(user_id).strip():
        return "Profile save failed: user_id is required."

    payload = {
        "wardrobe": wardrobe if isinstance(wardrobe, dict) else get_empty_wardrobe(),
        "style_notes": style_notes if isinstance(style_notes, str) else "",
    }

    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        item_count = len(payload["wardrobe"].get("items", []))
        return f"Saved profile for {user_id} with {item_count} items."
    except (OSError, TypeError, ValueError):
        return f"Failed to save profile for {user_id}."
