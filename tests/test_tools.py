import os

import tools
from tools import (
	check_price,
	create_fit_card,
	search_listings,
	style_profile_memory,
	suggest_outfit,
)
from utils.data_loader import get_empty_wardrobe, load_listings


def test_search_returns_results():
	results = search_listings("vintage graphic tee", size=None, max_price=50)
	assert isinstance(results, list)
	assert len(results) > 0


def test_search_empty_results():
	results = search_listings("designer ballgown", size="XXS", max_price=5)
	assert results == []


def test_search_price_filter():
	results = search_listings("jacket", size=None, max_price=10)
	assert all(item["price"] <= 10 for item in results)


def test_suggest_outfit_empty_wardrobe_falls_back(monkeypatch):
	def raise_error():
		raise ValueError("GROQ_API_KEY not set")

	monkeypatch.setattr(tools, "_get_groq_client", raise_error)

	new_item = {
		"title": "Striped tee",
		"category": "tops",
		"style_tags": ["vintage", "graphic"],
		"colors": ["blue", "white"],
		"price": 18,
	}
	result = suggest_outfit(new_item, get_empty_wardrobe())

	assert isinstance(result, str)
	assert len(result) > 0


def test_suggest_outfit_uses_wardrobe(monkeypatch):
	class FakeMessage:
		content = "Pair it with your black jeans and tan boots."

	class FakeChoice:
		message = FakeMessage()

	class FakeResponse:
		choices = [FakeChoice()]

	class FakeCompletions:
		@staticmethod
		def create(*args, **kwargs):
			return FakeResponse()

	class FakeChat:
		completions = FakeCompletions()

	class FakeClient:
		chat = FakeChat()

	monkeypatch.setattr(tools, "_get_groq_client", lambda: FakeClient())

	wardrobe = {
		"items": [
			{
				"name": "Black straight jeans",
				"category": "bottoms",
				"colors": ["black"],
				"style_tags": ["classic", "minimal"],
				"notes": "Everyday staple",
			}
		]
	}
	new_item = {
		"title": "Vintage striped tee",
		"category": "tops",
		"style_tags": ["vintage", "graphic"],
		"colors": ["blue", "white"],
		"price": 22,
	}

	result = suggest_outfit(new_item, wardrobe)
	assert "black jeans" in result.lower()


def test_create_fit_card_rejects_blank_outfit():
	item = {
		"title": "Vintage tee",
		"price": 12,
		"platform": "depop",
		"colors": ["white"],
		"style_tags": ["vintage"],
	}
	result = create_fit_card("   ", item)
	assert result == "I need an outfit suggestion before I can write a fit card."


def test_create_fit_card_falls_back_when_llm_unavailable(monkeypatch):
	def raise_error():
		raise ValueError("GROQ_API_KEY not set")

	monkeypatch.setattr(tools, "_get_groq_client", raise_error)

	item = {
		"title": "Butterfly shirt",
		"price": 18,
		"platform": "thredUp",
		"colors": ["pink", "purple"],
		"style_tags": ["y2k", "cute"],
	}
	result = create_fit_card("Pair it with loose denim and chunky sneakers.", item)

	assert isinstance(result, str)
	assert len(result) > 0
	assert "Found this" in result


def test_check_price_not_enough_data():
	item = {
		"category": "tops",
		"style_tags": ["ultra-niche-not-in-data"],
		"price": 15,
	}
	result = check_price(item, min_comps=99)

	assert result["verdict"] == "not enough data"
	assert result["comp_count"] < 99


def test_check_price_returns_valid_verdict_for_real_listing():
	listings = load_listings()
	item = listings[0]
	result = check_price(item, min_comps=1)

	assert result["verdict"] in {"good deal", "about right", "overpriced"}
	assert result["comp_count"] >= 1


def test_style_profile_memory_round_trip():
	user_id = "pytest_roundtrip_profile"
	profile_path = os.path.join(os.path.dirname(tools.__file__), "profiles", f"{user_id}.json")

	if os.path.exists(profile_path):
		os.remove(profile_path)

	wardrobe = {
		"items": [
			{
				"name": "Black denim jacket",
				"category": "outerwear",
				"colors": ["black"],
				"style_tags": ["streetwear", "minimal"],
			}
		]
	}

	save_result = style_profile_memory(user_id, wardrobe=wardrobe, style_notes="Minimal vintage")
	assert "Saved profile" in save_result

	loaded = style_profile_memory(user_id)
	assert loaded["wardrobe"]["items"][0]["name"] == "Black denim jacket"
	assert loaded["style_notes"] == "Minimal vintage"

	if os.path.exists(profile_path):
		os.remove(profile_path)


def test_style_profile_memory_handles_corrupt_profile_file():
	user_id = "pytest_corrupt_profile"
	profile_path = os.path.join(os.path.dirname(tools.__file__), "profiles", f"{user_id}.json")

	os.makedirs(os.path.dirname(profile_path), exist_ok=True)
	with open(profile_path, "w", encoding="utf-8") as f:
		f.write("{not valid json")

	loaded = style_profile_memory(user_id)
	assert loaded["wardrobe"] == get_empty_wardrobe()
	assert loaded["style_notes"] == ""

	if os.path.exists(profile_path):
		os.remove(profile_path)
