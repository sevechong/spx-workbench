#!/usr/bin/env python3
"""
update_brief.py — regenerates the Market Brief section of index.html.

Calls the Anthropic API with web search enabled, asks for the brief as HTML,
and swaps it into index.html between the BRIEF:START / BRIEF:END markers.

Run locally:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 update_brief.py

In CI the key comes from the ANTHROPIC_API_KEY repo secret.
"""

import os
import sys
import json
import html
import datetime as dt
import zoneinfo
import urllib.request
import urllib.error

MODEL = "claude-sonnet-5"
MAX_TOKENS = 8000
INDEX = "index.html"
START = "<!-- BRIEF:START -->"
END = "<!-- BRIEF:END -->"

ET = zoneinfo.ZoneInfo("America/New_York")


def now_et():
    return dt.datetime.now(ET)


PROMPT = """You are writing the "Market Brief" tab of a private options-trading \
tool. The reader sells 7-day SPX put credit spreads. Some readers are friends and \
family with no market background.

Today is {today}. Research what is currently moving the S&P 500. Use web search \
extensively — at least six searches covering:
  1. S&P 500 today: level, percent change, what drove it
  2. Geopolitics: conflicts, trade, anything with market impact
  3. The Fed, rates, bond yields, current FOMC odds
  4. AI / data centres / tech sector, including the political dimension
  5. Market internals: leading and lagging sectors and large caps
  6. The economic calendar for the next two weeks

Then output ONLY an HTML fragment. No markdown, no code fences, no preamble.

Required structure, in this order:

<div class="stale">
  AUTO-GENERATED {stamp} ET. Researched by Claude from public reporting and not \
reviewed by a human before publishing. Verify anything you intend to act on.
</div>

<div class="tldr">
  <h3>The short version</h3>
  <ul>
    6 to 8 <li> items. One sentence each. Plain language, no jargon. Lead with the
    single most important thing. Wrap the key phrase of each bullet in <b>.
  </ul>
</div>

<div class="snap">
  Exactly six <div class="sn"> blocks, each:
    <div class="k">LABEL</div><div class="v">VALUE</div><div class="c CLASS">CHANGE</div>
  Use: S&P 500, Nasdaq, VIX, 10Y yield, Crude, and the nearest FOMC decision odds.
  CLASS is "pos" for green, "neg" for red, or omit for neutral.
  Put class="acc" on the .v div for VIX and the FOMC odds.
</div>

Then one <div class="blk"> per theme — geopolitics, the Fed and rates, AI and tech,
market internals, and a calendar. Each contains:
  <h3> heading, optionally with class="neg" / "acc" / "pos"
  <div class="tag">a three-to-five word subtitle</div>
  two or three <p> paragraphs, 13-14 words minimum each, <b> for emphasis and
  <span class="num"> for figures

The calendar block uses this markup instead of paragraphs:
  <div class="cal">
    <div class="row"><span class="when">DATE</span><span class="what">EVENT</span><span class="imp">IMPACT</span></div>
    ... one row per event, 5 to 7 rows
  </div>

Finish with a <div class="blk"> titled "If you're selling premium" that covers:
  - whether VIX is pricing the known upcoming catalysts
  - which events fall inside a 7-day expiry window opened today
  - how the current regime compares to a low-volatility historical sample
Frame every point as a question to check, never as a recommendation.

Then a final <p class="foot"> naming the outlets you used, noting figures are
intraday, and stating this is a summary of reporting rather than advice.

Rules:
  - Never forecast or predict. Report what was reported.
  - Never tell the reader to buy, sell, or size a position.
  - Attribute claims to outlets by name.
  - If a figure is unavailable, write "n/a" rather than inventing one.
  - Output the fragment and nothing else.
"""


def call_api(prompt: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set.")

    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"API error {e.code}: {e.read().decode()[:600]}")

    # keep only text blocks; ignore tool_use / tool_result
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def clean(fragment: str) -> str:
    """Strip code fences and any stray preamble before the first div."""
    f = fragment.strip()
    for fence in ("```html", "```HTML", "```"):
        f = f.replace(fence, "")
    i = f.find("<div")
    if i > 0:
        f = f[i:]
    return f.strip()


def sanity_check(fragment: str) -> list:
    """Cheap guards so a malformed run can't silently deface the site."""
    problems = []
    if len(fragment) < 1200:
        problems.append(f"fragment too short ({len(fragment)} chars)")
    for needed in ('class="stale"', 'class="tldr"', 'class="snap"', 'class="blk"'):
        if needed not in fragment:
            problems.append(f"missing {needed}")
    if fragment.count("<div") - fragment.count("</div>") != 0:
        problems.append("unbalanced <div> tags")
    if "<script" in fragment.lower():
        problems.append("fragment contains a <script> tag")
    return problems


def main():
    stamp = now_et().strftime("%-d %b %Y, %-I:%M%p").replace("AM", "am").replace("PM", "pm")
    prompt = PROMPT.format(today=now_et().strftime("%A, %-d %B %Y"), stamp=stamp)

    print(f"Requesting brief for {stamp} ET ...")
    fragment = clean(call_api(prompt))

    problems = sanity_check(fragment)
    if problems:
        print("REFUSING TO PUBLISH — " + "; ".join(problems))
        print("---- first 800 chars returned ----")
        print(fragment[:800])
        sys.exit(1)

    with open(INDEX, encoding="utf-8") as f:
        page = f.read()

    if START not in page or END not in page:
        sys.exit("Markers not found in index.html — was the file overwritten?")

    a = page.index(START) + len(START)
    b = page.index(END)
    updated = page[:a] + "\n" + fragment + "\n  " + page[b:]

    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"index.html updated — brief is {len(fragment):,} chars.")


if __name__ == "__main__":
    main()
