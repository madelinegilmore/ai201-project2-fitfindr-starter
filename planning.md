# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
This tool finds items on a thrift website that fit a user's search criteria. It searches the mock listings in data/listings.json and hands back the ones that actually match what the user asked for, best match first. 

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): the keywords for what the user wants, like "vintage graphic tee" or "chunky black boots". This gets matched against each listing's title, description, style_tags, colors, and brand.
- `size` (str): the size they wear, like "M". 
- `max_price` (float): the most they want to spend. Optional — if it's None I skip the price filter. Inclusive, so max_price=30 keeps a $30 item.

**What it returns:**
A list of listing dicts. Each one has `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, and `platform` (depop, thredUp, or poshmark). The list is sorted so the listing with the most keyword overlap is first, and anything that matched zero keywords gets dropped.

Not every field is worth the same, though. I found this out tracing the example query at the bottom of this doc — plain keyword counting gave me a three-way tie for first place, and it also matched a pair of cargo pants because the seller's description said "great for layering with a long tee." So each keyword scores once, on the best field it hits: 3 if it's in the `title`, 2 if it's in `style_tags`, 1 if it's only in the free-text `description`, `colors`, or `brand`. That pushes the pants down (they only ever hit the description) and breaks most ties on its own. If there's still a tie, better `condition` wins (excellent > good > fair), then the lower price.

**What happens if it fails or returns nothing:**
It returns an empty list, it never raises. (It does not call suggest_outfit, because there's no item to style)

The tool itself just returns `[]` — working out *why* is the loop's job, and it does that by calling this tool again with one filter dropped at a time. See the Planning Loop step 4 and the Error Handling table for what the user actually gets told.

---

### Tool 2: suggest_outfit

**What it does:**
This tool takes one thrifted item and the user's closet and writes out 1–2 full outfits built around that item, naming the actual pieces the user already owns. 

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): one listing dict, straight out of search_listings — normally the top result. The tool pulls the title, category, colors, and style_tags out of it to know what it's styling.
- `wardrobe` (dict): the user's closet in the format from `data/wardrobe_schema.json` — a dict with an `items` key holding a list, where each item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`. I'll use `get_example_wardrobe()` from the data loader for testing.

**What it returns:**
A string with the outfit ideas in it like "pair this with your baggy dark-wash jeans and chunky white sneakers." 

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, it doesn't fail or return an empty string. It switches to general advice instead (what kinds of pieces go with the item, what vibe it fits, what colors work). If the LLM call itself errors out, the tool returns a plain fallback string describing the item's style tags so the chain doesn't break.

---

### Tool 3: create_fit_card

**What it does:**
This tool turns the outfit suggestion into a short caption the user could post. 

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): the string that came back from `suggest_outfit`
- `new_item` (dict): the same listing dict from Tool 1,

**What it returns:**
A 2–4 sentence string. It mentions the item, the price, and the platform once each, and it captures the vibe of the outfit in specific terms. I'll run it at a higher temperature so two different finds don't come back with the same caption.

**What happens if it fails or returns nothing:**
First thing it does is check whether `outfit` is empty or just whitespace. If it is, it returns an error message string explaining that it needs an outfit suggestion first, it does not raise, and it does not make something up from just the item. Same if `new_item` is missing the fields it needs: it says so in the returned string.

---

### Additional Tools (if any)

### Tool 4: check_price (price comparison)
(Add a fourth tool that, given an item, estimates whether the price is fair based on comparable listings in the dataset.)

**What it does:**
This tool tells the user whether the price on a find is actually decent. It pulls the comparable listings out of the dataset — same category, and at least two overlapping style tags — and compares the item's price against what those are going for.

The two-tag rule matters. When I traced the example query I tried it with just one overlapping tag and got 12 comps for a graphic tee, including a silk button-down and an argyle knit vest, because everything in this dataset is tagged "vintage." Averaging those together says nothing about what a tee should cost. Requiring two tags cut it to 4 comps that are actually the same kind of thing.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): the listing dict being checked. The tool uses its `category`, `style_tags`, `brand`, and `condition` to decide what counts as comparable.
- `min_comps` (int): the fewest comparable listings I'll accept before I trust the average. Defaults to 3 — below that the sample is too small to say anything.

**What it returns:**
A dict with `verdict` ("good deal", "about right", or "overpriced"), `avg_comp_price` (the average of the comps), `comp_count` (how many it found), and `reason` (a short sentence like "$22 for a good-condition vintage tee, comps average $31"). The verdict comes from where the price falls against that average — meaningfully under is a good deal, meaningfully over is overpriced.

**What happens if it fails or returns nothing:**
If it finds fewer than `min_comps` comparable listings, it doesn't guess. It returns the dict with `verdict` set to "not enough data" and `comp_count` set to what it actually found, and the agent just skips the price note in its final answer instead of treating a missing verdict as a failure. This tool is optional in the loop — if it errors, the run keeps going.

### Tool 5: style_profile_memory
(Allow the agent to remember a user's style preferences across sessions, so they don't have to re-describe their wardrobe every time.)

**What it does:**
This tool saves and loads a user's wardrobe and style notes to a JSON file on disk, so a returning user doesn't have to type out their whole closet again. One function that does both — pass it a wardrobe to save it, leave that out to load what's already stored.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `user_id` (str): who this profile belongs to. This is the filename it reads and writes, so it has to be there.
- `wardrobe` (dict): the wardrobe to save, in the same schema Tool 2 uses. Optional — if it's None the tool is in load mode and just returns whatever's on file.
- `style_notes` (str): anything extra about how the user dresses that isn't a specific item, like "leans grunge, hates cropped stuff." Optional, saved alongside the wardrobe.

**What it returns:**
In load mode, a dict with `wardrobe` and `style_notes` for that user. In save mode, a confirmation string saying what got saved and how many items are in it.

**What happens if it fails or returns nothing:**
If there's no saved profile for that `user_id`, load mode doesn't crash — it returns `get_empty_wardrobe()` with empty notes, which is a shape Tool 2 already knows how to deal with (it falls back to general advice). If the file exists but is corrupted or unreadable, it does the same thing and logs that it couldn't read the profile, so a bad file can't take down the run.

---

## Planning Loop

**How does your agent decide which tool to call next?**

It's not a free choice, the tools run in order because each one needs what the last one made. At every step it looks at the session dict and checks whether it has what the next tool needs, or whether it should stop:

1. Start the session with `_new_session(query, wardrobe)`.

2. Call `style_profile_memory(user_id)` in load mode.
   - If it comes back with a wardrobe that has items in it, set `session["wardrobe"]` to that and set `session["style_notes"]` to the saved notes.
   - If it comes back empty (new user, or no file), leave `session["wardrobe"]` as whatever the caller passed in.

3. Parse the query into `description`, `size`, and `max_price` and store all three in `session["parsed"]`. Regex, not an LLM call — the query patterns are predictable and I don't want to spend a round trip on it.
   - Price: match `under \$?(\d+)` or `\$(\d+)` and take it as a float. If nothing matches, `max_price = None`.
   - Size: match a standalone size token (S, M, L, XL) or `size (\w+)`. If nothing matches, `size = None`.
   - Description: only the first sentence, minus the price phrase and the size token. Not the whole query — people write two or three sentences and only the first one is the thing they want me to find. In the example query at the bottom of this doc, the second sentence is "I mostly wear baggy jeans and chunky sneakers," and if I let that into the description then "jeans" and "sneakers" become search keywords and I start scoring shoes against a request for a tee.
   - Any sentence after the first goes into `session["style_notes"]` instead, which is what Tool 5 saves and Tool 2 can read. That's where "I mostly wear baggy jeans" actually belongs — it's context for styling, not a search term.
   - If `description` comes out empty or whitespace, set `session["error"]` to "I couldn't tell what you're looking for — try naming the item" and return. There's nothing to search on.

4. Call `search_listings(description, size, max_price)` and store the list in `session["search_results"]`.
   - If it's empty, don't error out yet — first figure out *which* filter killed it, by re-running the search with one filter dropped at a time. This is cheap (it's a list comprehension over 40 dicts, no LLM call) and it's the difference between a useless "no results" and a message the user can act on:
     - Retry with `max_price=None`. If that returns something, price was the blocker → set `session["error"]` naming the actual cheapest match and its price, and offer to search up to a bit above it.
     - Otherwise retry with `size=None`. If that returns something, size was the blocker → name the sizes that do exist for this item.
     - Otherwise the keywords are the problem → set the error to a message listing a few `style_tags` that do appear in the dataset, as suggestions to try instead.
   - Store whichever retry succeeded in `session["relaxed_results"]` so the final message can name a real item instead of just describing one.
   - Then return. Do NOT call `suggest_outfit`. Handing it nothing just makes the LLM invent an item that isn't for sale — and note the retries are only for diagnosing the message, the run still ends here rather than quietly styling something the user didn't ask for.

5. If `search_results` isn't empty, set `session["selected_item"] = search_results[0]` (the top keyword match) and keep going.

6. Call `check_price(selected_item)` and store the dict in `session["price_check"]`.
   - If `verdict` is "not enough data", or the call raises, leave `price_check` as None and keep going. This step can't end the run — it's an extra note on the final answer, not something anything downstream depends on.

7. Call `suggest_outfit(selected_item, session["wardrobe"])` and store the string in `session["outfit_suggestion"]`. No branch on the wardrobe being empty here, because the tool handles that itself by switching to general advice.
   - If `outfit_suggestion` comes back empty or whitespace anyway, set `session["error"]` to "couldn't put an outfit together for this one" and return early. Tool 3 has nothing to work from.

8. Call `create_fit_card(session["outfit_suggestion"], selected_item)` and store the string in `session["fit_card"]`.

9. Call `style_profile_memory(user_id, wardrobe=session["wardrobe"], style_notes=session["style_notes"])` in save mode so the closet is there next time. If the save fails, don't error the run — the user already has their answer.

10. Return the session.

How it knows it's done: there are only two ways a run ends — `session["fit_card"]` is set (success) or `session["error"]` is set (stopped early). The caller checks `error` first, and if it's not None then `outfit_suggestion` and `fit_card` are still None and there's nothing else to read.

---

## State Management

**How does information from one tool get passed to the next?**

Everything lives in one session dict, built by `_new_session()` at the top of the run. 

What's tracked in it:
- `query` — what the user actually typed, kept unchanged so I can quote it back in an error message.
- `parsed` — the `description`, `size`, and `max_price` that step 3 pulled out.
- `search_results` — the whole list from Tool 1, not just the winner, so I could offer a second option later without searching again.
- `selected_item` — the one listing everything downstream is built around.
- `wardrobe` — either loaded from Tool 5 or passed in by the caller.
- `style_notes` — the extra style info from Tool 5, saved back at the end.
- `price_check` — Tool 4's dict, or None if it couldn't say.
- `outfit_suggestion` — Tool 2's string.
- `fit_card` — Tool 3's string.
- `error` — None unless the run stopped early.

The handoff is just reads and writes on that dict:
- Tool 5 writes → `wardrobe` and `style_notes` at the start, and reads them back out at the end to save.
- Tool 1 writes → `search_results`, and the loop picks `selected_item = search_results[0]` out of it.
- That same `selected_item` dict object gets passed into Tools 4, 2, and 3, so every tool is talking about the exact same item and nothing drifts between steps.
- Tool 2 writes → `outfit_suggestion`, which gets read straight back out as Tool 3's `outfit` argument.

The tools themselves are stateless and don't know the session exists — the loop does all the storing. At the end the whole dict comes back, so I can see not just the final caption but every value that led to it, which is what makes it debuggable when a caption comes out weird.

Within a run, state is just that dict. Across runs, the only thing that persists is what Tool 5 wrote to disk — the wardrobe and the style notes. Search results, the selected item, and the fit card all get thrown away when the run ends.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

The rule I'm holding myself to here: a dead end has to come back with a number or a name in it, and something the user can do next. "No results found" is useless — it doesn't tell them whether their budget was $2 short or $40 short.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Returns `[]`, never raises. Before giving up the loop **re-runs the search once with the filters dropped one at a time** to find out which one was actually the blocker, then names it with a real number and offers the nearest thing that does exist. For "vintage graphic tee under $10" the retry with no price cap comes back with matches, so price was the blocker, and the user gets: *"Nothing matching 'vintage graphic tee' under $10. The cheapest one I've got is a Y2K Baby Tee — Butterfly Print, $18 on Depop, excellent condition. Want me to search up to $20?"* If dropping the size is what unblocks it: *"Nothing in size M, but there's a Graphic Tee — 2003 Tour Bootleg in size L for $24. Want to see it?"* If nothing matches even with every filter off, the keywords are the problem, so it lists the closest style tags that do exist in the data — *"'graphic tee' isn't turning anything up. I do have vintage, grunge, y2k, and streetwear pieces — want to try one of those?"* Either way it returns right there and never calls `suggest_outfit` with nothing. |
| suggest_outfit | Wardrobe is empty | Checks `wardrobe["items"]` first and switches to general advice rather than returning `""`, so the run keeps going and Tool 3 still gets real input. But it also says why the advice is generic and asks for the one thing that would fix it: *"I don't have your closet saved yet, so here's the general version — this one's boxy and grunge-leaning, so it wants a wide or baggy bottom and a chunky shoe, and the faded black goes with basically any denim. Tell me 3–4 things you actually wear (a bottom, a shoe, a jacket) and I'll save them so next time I can name your own pieces."* That last sentence is the offer, and it hands off to Tool 5. |
| suggest_outfit | LLM call fails or returns blank | Falls back to a string built from the item's own `style_tags` and `colors` — no model needed: *"Couldn't reach the styling model, so here's the short version: this one's tagged grunge, streetwear, and vintage in black, which pairs with baggy denim and boots. Try again in a sec for the full styling."* The run continues with that string, so the user still gets an item and a caption instead of a hard stop. |
| create_fit_card | Outfit input is missing or incomplete | Guards `outfit` for empty/whitespace as the first thing in the function and returns an explanatory string instead of raising — it will not invent a caption from just the item, because a caption about an outfit nobody suggested is worse than no caption. In the loop this case is already caught upstream, so what the user sees is the item and the price check with the caption section simply absent, plus *"Couldn't get a caption together for this one — want me to retry it?"* The find is never thrown away over a failed caption. Same handling if `new_item` is missing `price` or `platform`: it says which field is missing rather than writing "$None". |
| check_price | Fewer than `min_comps` comparable listings in the dataset | Won't average 1–2 items into a verdict. Returns `verdict: "not enough data"` with the real `comp_count`, and the loop leaves `session["price_check"]` as None. Rather than silently dropping the price line, it says so and shows what little it has: *"Only found 1 comparable piece in the data, so I won't call this price fair or not — for what it's worth, the one match is $19 vs. this at $24."* It also offers the looser comparison as an explicit choice: *"Want me to compare against all tops instead of just similar ones? It'd be a rougher number."* The run finishes normally either way — a missing verdict is never treated as a failure. |
| style_profile_memory | No saved profile (new user) | Not really an error, so it doesn't say anything up front — it returns the `get_empty_wardrobe()` shape, which Tool 2 already handles, and the run proceeds on whatever wardrobe the caller passed. The user only hears about it at the end, as a win: *"Saved your closet and your style notes — next time you can skip straight to searching."* |
| style_profile_memory | Saved file is corrupted or unreadable | Same empty-wardrobe shape so nothing crashes, but this one the user does get told, because their data is involved: *"Couldn't read your saved profile — it looks corrupted, so I've set it aside as `user_001.json.bak` and started fresh."* Renaming rather than overwriting matters; if I just clobber it, a bad parse silently destroys a closet they spent time entering. |
| style_profile_memory | Save at the end fails | Doesn't error the run, since the user already has their answer, but it doesn't swallow it either — they need to know the memory didn't stick or they'll be surprised next session: *"Heads up, I couldn't save your profile this time, so you'll need to re-enter your closet next run."* |

---

## Architecture

```
User query + user_id
    │
    ▼
Planning Loop ────────────────────────────────────────────────────┐
    │                                                             │
    ├─► style_profile_memory(user_id)              [load mode]    │
    │       │ saved profile on disk                               │
    │       ├──► Session: wardrobe, style_notes = saved           │
    │       │ no profile / unreadable file                        │
    │       └──► Session: wardrobe = get_empty_wardrobe()         │
    │                                                             │
    ├─► parse query with regex                                    │
    │       │ description == ""                                   │
    │       ├──► [ERROR] "Couldn't tell what you're looking       ┤
    │       │              for" and returns                       │
    │       │ description ok                                      │
    │       ▼                                                     │
    │   Session: parsed = {description, size, max_price}          │
    │                                                             │
    ├─► search_listings(description, size, max_price)             │
    │       │ results == []                                       │
    │       ├──► retry: max_price=None                            │
    │       │      hits? price was the blocker                    │
    │       ├──► retry: size=None                                 │
    │       │      hits? size was the blocker                     │
    │       │      neither? keywords were the blocker             │
    │       ├──► [ERROR] names the blocker + the cheapest         ┤
    │       │              real alternative, returns              │
    │       │ results == [item, ...]                              │
    │       ▼                                                     │
    │   Session: search_results = results                         │
    │   Session: selected_item  = results[0]                      │
    │                                                             │
    ├─► check_price(selected_item)                                │
    │       │ < min_comps comps, or raises                        │
    │       ├──► Session: price_check = None                      │
    │       │    (drop the price note, run keeps going)           │
    │       │ enough comps                                        │
    │       ▼                                                     │
    │   Session: price_check = {verdict, avg_comp_price, reason}  │
    │                                                             │
    ├─► suggest_outfit(selected_item, wardrobe)                   │
    │       │ wardrobe["items"] == []                             │
    │       ├──► general styling advice instead                   │
    │       │    (not an error, run keeps going)                  │
    │       │ outfit == "" (LLM call failed)                      │
    │       ├──► [ERROR] "Couldn't put an outfit together"        ┤
    │       │              and returns                            │
    │       ▼                                                     │
    │   Session: outfit_suggestion = "..."                        │
    │                                                             │
    ├─► create_fit_card(outfit_suggestion, selected_item)         │
    │       │                                                     │
    │   Session: fit_card = "..."                                 │
    │                                                             │
    └─► style_profile_memory(user_id, wardrobe, style_notes)      │
            │            [save mode — a failed save is ignored]   │
            ▼                                                     │
        Return session  ◄─────────────────────────────────────────┘
                          every error path returns here too
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**


**search_listings** — I'll give Claude the Tool 1 section (all three params, the return fields, and the empty-list failure mode) plus the `load_listings()` docstring from `utils/data_loader.py`, and ask it to implement the function. I expect a function that loads once, filters by price and size, scores by keyword overlap, drops zero-score listings, and returns sorted dicts. Before I run anything I'm reading the code for four things: that it calls `load_listings()` instead of opening the JSON itself, that `size=None` and `max_price=None` actually skip those filters instead of filtering on None, that the price check is `<=` and not `<`, and that it returns `[]` rather than raising when nothing matches. Then I test with:
- `search_listings("vintage graphic tee", max_price=30)` — should surface lst_006, lst_033, and lst_002, all of which have "graphic tee" in their style_tags.
- `search_listings("vintage graphic tee", size="M", max_price=30)` — should still include lst_002 even though its size is "S/M", which is the messy-size case.
- `search_listings("vintage band tee", max_price=19)` — should include lst_033 at exactly $19, to catch an off-by-one on the price filter.
- `search_listings("designer ballgown", size="XXS", max_price=5)` — should come back `[]`, not an exception.

**suggest_outfit** — I'll give Claude the Tool 2 section plus the `schema` block from `data/wardrobe_schema.json` so it knows the item fields, and ask for the two-branch version described in the spec. I expect it to check `wardrobe["items"]` first and take a different prompt path for empty vs. populated. What I'm checking before trusting it: that the empty-wardrobe branch returns advice instead of `""`, that the populated branch actually formats the wardrobe items into the prompt (if the prompt only mentions the new item, the LLM can't name real pieces and the whole tool is pointless), and that it references items by their `name` field. Then I run it twice on lst_033 — once with `get_example_wardrobe()`, once with `get_empty_wardrobe()`. The first has to name specific pieces I can find in the schema file; the second has to be non-empty and generic.

**create_fit_card** — I'll give Claude the Tool 3 section including the four caption style rules, and the guard requirement. I expect a function that early-returns an error string on blank input, then makes one higher-temperature call. Verification: I check the empty-outfit guard is the first thing in the function body and returns a string rather than raising, then run it on the same item twice to confirm the temperature is actually high enough that I get two different captions. I also check it doesn't repeat the price or platform twice in one caption, which is the thing LLMs do when you tell them to mention details.

**check_price** — I'll give Claude the Tool 4 section and ask it to implement the comps logic. The part I don't trust AI on here is the "comparable" definition, so I'll read that filter closely and confirm it's matching on category plus style_tag overlap like I specced, not just doing a dataset-wide average, which would make every verdict meaningless. I'll also verify the `min_comps` guard returns "not enough data" instead of dividing by a tiny sample. Test: run it on lst_033 (vintage band tee, $19) and hand-check the average against the tops in the dataset myself before believing the verdict.

**style_profile_memory** — I'll give Claude the Tool 5 section and ask for the load/save function. I expect the `wardrobe=None` check to be what switches modes. Verification: I save a wardrobe, load it back, and confirm it round-trips with the same item count. Then I load a `user_id` that doesn't exist and confirm I get the empty-wardrobe shape rather than a `FileNotFoundError`, and I hand-corrupt the JSON file and confirm it still returns the empty shape instead of blowing up.

**Milestone 4 — Planning loop and state management:**

Also Claude, but this time I'm giving it the Planning Loop section, the State Management section, and the ASCII diagram from the Architecture section together, plus the `run_agent` and `_new_session` docstrings from `agent.py`. 

What I expect back: `_new_session()` extended with the `style_notes` and `price_check` keys my loop uses (the starter dict doesn't have them), the regex parsing for description/size/max_price, and the ten steps in order with each early return writing to `session["error"]`.


1. Read it against the diagram branch by branch. Every `[ERROR]` box in the diagram has to be an early `return session`, and the two non-error branches — empty wardrobe on `suggest_outfit`, "not enough data" on `check_price` — have to fall through and keep going. If the generated code errors out on an empty wardrobe, it's wrong and I'd rather catch that by reading than by debugging output.
2. Check that no tool gets called with input the previous step didn't produce. Specifically: `suggest_outfit` must not be reachable when `search_results == []`, and `create_fit_card` must not be reachable when `outfit_suggestion` is blank. This is the one bug I most expect, because generating straight-line code is easier than generating guarded code.
3. Check the state actually goes through the session dict — no module-level variables, no tool re-reading `listings.json` to figure out what got selected, and the same `selected_item` object passed to Tools 4, 2, and 3 rather than re-looked-up by id.
4. Then run the two cases already sitting in the `__main__` block of `agent.py`: "looking for a vintage graphic tee under $30" should come back with `error` as None and all three of `selected_item`, `outfit_suggestion`, and `fit_card` filled in. "designer ballgown size XXS under $5" should come back with an `error` string that names the price or the size, and `outfit_suggestion` and `fit_card` both still None — if either one is populated on the error path, an early return is missing.
5. Last, the parsing specifically, since regex is where AI output tends to be confidently wrong: I'll run the parse step on "vintage graphic tee under $30", "graphic tee size M", and "band tee" and confirm I get the right `max_price`/`size`/`None` combination out of each, with the price phrase and size token stripped out of the description instead of left in to pollute the keyword scoring.


---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr needs to do:**
FitFindr takes whatever a user says they're looking for and searches a thrift site for items that actually fit their criteria — the right size, under their price, matching the style they're going for. Once it finds something, that listing triggers the outfit step, where it looks at the user's wardrobe and style and puts together a look around the new item, and then that outfit gets turned into a little caption the user could actually post. If the search comes back with nothing, it stops there and tells the user what to change about their search instead of trying to style an item that doesn't exist.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

I assume a first-time user, so there's no saved profile yet and the caller passed in `get_example_wardrobe()`.

**Step 1:** `run_agent()` builds the session with `_new_session(query, wardrobe)`, then calls `style_profile_memory("user_001")` in load mode. There's no file for this user yet, so it returns `{"wardrobe": {"items": []}, "style_notes": ""}` — the empty shape, not an exception. Since the loaded wardrobe has no items in it, the loop leaves `session["wardrobe"]` as the example wardrobe the caller passed in. Nothing errors, and the run keeps going.

**Step 2:** The parse step runs the regex over the query.
- `under \$?(\d+)` hits "under $30" → `max_price = 30.0`
- No standalone size token anywhere in the query → `size = None`, so the search won't filter on size at all
- First sentence minus the price phrase → `description = "vintage graphic tee"`
- The remaining sentences go to `session["style_notes"] = "I mostly wear baggy jeans and chunky sneakers."`

So `session["parsed"] = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}`. The description isn't blank, so no early return.

**Step 3:** `search_listings("vintage graphic tee", size=None, max_price=30.0)`.

It drops everything over $30, then scores the rest on the keywords `vintage`, `graphic`, `tee`. Plain keyword counting gives a three-way tie at 3 hits each — lst_002, lst_006, lst_033 — so the field weighting from the Tool 1 spec breaks it:
- **lst_006** "Graphic Tee — 2003 Tour Bootleg Style", $24, size L, good condition, depop → `graphic` and `tee` both in the title (3+3), `vintage` in style_tags (2) = **8**
- **lst_033** "Vintage Band Tee — Faded Grey", $19, size L, fair condition, depop → `vintage` and `tee` in the title (3+3), `graphic` in style_tags (2) = **8**
- **lst_002** "Y2K Baby Tee — Butterfly Print", $18, size S/M, depop → `tee` in title (3), `vintage` and `graphic` in tags (2+2) = **7**

lst_006 and lst_033 are still tied at 8, so the condition tiebreak decides it: lst_006 is "good" and lst_033 is "fair", so **lst_006 wins**. The weighting also correctly buries lst_011 (a pair of cargo pants whose description happens to say "great for layering with a long tee") and lst_017 (a mesh top described as good "under a graphic tee") — both only ever hit the free-text description, so they score 1–2 and sort to the bottom instead of competing for the top slot.

The list isn't empty, so no error. `session["search_results"]` holds all the matches and `session["selected_item"] = search_results[0]`, the lst_006 dict.

**Step 4:** `check_price(<lst_006 dict>)`. It pulls comps — same category (`tops`) with at least two overlapping style tags — and finds 4: lst_002 at $18, lst_003 at $22, lst_015 at $26, lst_033 at $19. That's ≥ `min_comps` of 3, so it doesn't bail. Average is $21.25, and the item is $24, which is +12.9% — inside the ±15% band, so it returns `{"verdict": "about right", "avg_comp_price": 21.25, "comp_count": 4, "reason": "$24 for a good-condition vintage graphic tee, comparable tees average $21.25"}`. Stored in `session["price_check"]`.

**Step 5:** `suggest_outfit(<lst_006 dict>, <example wardrobe>)`. The wardrobe has 10 items, so it takes the populated branch, not the general-advice one. The tee's tags are grunge/streetwear/vintage, and the closest matches in the closet are w_001 (baggy straight-leg jeans, dark wash), w_007 (chunky white sneakers), w_008 (black combat boots), and w_006 (vintage black denim jacket). It returns something like: *"Wear it with your baggy dark-wash straight-legs and the chunky white sneakers — the boxy fit of the tee balances the volume in the leg. Half-tuck the front so the high waist still reads. If you want it grungier, swap to the combat boots and throw the vintage black denim jacket over it."* Saved to `session["outfit_suggestion"]`.

(the user's own sentence about baggy jeans and chunky sneakers matches what's already in the example wardrobe, so the advice lines up with what they said either way.)

**Step 6:** `create_fit_card(<that outfit string>, <lst_006 dict>)`. The outfit string isn't blank, so the guard passes. It pulls the title, `price` ($24), and `platform` (depop) off the item and makes one higher-temperature call, returning something like: *"found a 2003 bootleg tour tee on depop for $24 and it was made for my baggy dark wash straight legs 🖤 half-tucked with the chunky sneakers, full look loading"* → `session["fit_card"]`.

**Step 7:** `style_profile_memory("user_001", wardrobe=session["wardrobe"], style_notes=session["style_notes"])` in save mode, so next time this user doesn't have to re-enter their closet or re-explain that they wear baggy jeans. If the save fails it's swallowed — the user already has their answer.

**Step 8:** Return the session. `error` is None and `fit_card` is set, so this is the success path.

**Final output to user:**

> **Found it — Graphic Tee, 2003 Tour Bootleg Style**
> $24 on Depop, size L, good condition. Price check: about right — comparable vintage tees in this size range average $21.25.
>
> **How to style it:** Wear it with your baggy dark-wash straight-legs and the chunky white sneakers — the boxy fit of the tee balances the volume in the leg. Half-tuck the front so the high waist still reads. If you want it grungier, swap to the combat boots and throw the vintage black denim jacket over it.
>
> **Caption if you post it:** "found a 2003 bootleg tour tee on depop for $24 and it was made for my baggy dark wash straight legs 🖤 half-tucked with the chunky sneakers, full look loading"


**search had come back empty** — say they'd asked for a vintage graphic tee under $10 — the run would stop at Step 3. `session["error"]` gets set to something like "Couldn't find a vintage graphic tee under $10 — nothing in the dataset is under $12 at all, and the cheapest actual tees start around $15, so try raising your budget," the loop returns immediately, and `price_check`, `outfit_suggestion`, and `fit_card` all stay None. No outfit gets suggested for an item that doesn't exist.

## Error Handling and Fail Points

<!-- For each tool, describe the specific failure mode and what your agent does in response.
     This maps to the error handling section of the rubric (F5-C1). -->

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | Returns `[]` — nothing matched | Re-runs the search with one filter dropped at a time to identify the actual blocker, then names it with a real number and offers the nearest existing item ("cheapest one I've got is $18 on Depop — want me to search up to $20?"). Sets `session["error"]` and returns. Never calls `suggest_outfit` with an empty list. |
| `suggest_outfit` | Wardrobe is empty, or the LLM call fails | Empty wardrobe → general styling advice plus a request for 3–4 pieces to save via Tool 5, so next run can name real items. Failed LLM call → a fallback string built from the item's own `style_tags` and `colors`, no model needed. Either way it returns a usable non-empty string, so the run continues and Tool 3 still has input. |
| `create_fit_card` | `outfit` is blank, or `new_item` is missing fields | Guards blank input first and returns an explanatory string — never invents a caption for an outfit nobody suggested, and never raises. The user still sees the item and the price check with the caption section absent, plus an offer to retry it. A missing `price`/`platform` is named explicitly rather than rendered as "$None". |

---

## Spec Reflection

<!-- Answer both questions with at least 2–3 sentences each. -->

**One way planning.md helped during implementation:**

**One divergence from your spec, and why:**

---

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.
