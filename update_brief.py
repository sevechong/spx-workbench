#!/usr/bin/env python3
"""
update_brief.py — regenerates brief.html, which index.html loads at runtime.

Calls the Anthropic API with web search enabled, asks for the brief as HTML,
and writes it to brief.html. index.html is never touched, so editing the tool
can never clobber the generated brief.

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
MAX_TOKENS = 20000
MAX_TURNS = 12
OUT = "brief.html"

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
    <div class="row" data-date="YYYY-MM-DD"><span class="when">DATE</span><span class="what">EVENT</span><span class="imp">IMPACT</span></div>
    ... one row per event, 5 to 7 rows
  </div>

  Every row MUST carry data-date with the ISO date of the event. For a week-long
  window use the Monday. The page computes "today", "tomorrow" and so on from that
  attribute at render time.

  Never write relative words into the visible text. No "(today)", no "tomorrow",
  no "this week". The brief may sit unchanged for days and those would go stale;
  the data-date attribute handles it instead. Write only the plain date, e.g.
  "Sep 4" or "Week of Sep 7".

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


def _post(payload: dict, key: str) -> dict:
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
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"API error {e.code}: {e.read().decode()[:800]}")


def call_api(prompt: str) -> str:
    """
    Server-side web search can return stop_reason='pause_turn' when the model is
    mid-research. The response has to be handed back so it can carry on. Without
    this loop you get search results and no prose.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set.")

    messages = [{"role": "user", "content": prompt}]
    collected = []

    for turn in range(1, MAX_TURNS + 1):
        data = _post({
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": messages,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        }, key)

        stop = data.get("stop_reason")
        blocks = data.get("content", [])
        kinds = {}
        for b in blocks:
            kinds[b.get("type")] = kinds.get(b.get("type"), 0) + 1
        text_now = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        collected.append(text_now)

        print(f"  turn {turn}: stop_reason={stop} blocks={kinds} "
              f"text={len(text_now)} chars")

        if stop == "pause_turn":
            # hand the whole assistant turn back so research continues
            messages = messages + [{"role": "assistant", "content": blocks}]
            continue

        if stop == "max_tokens":
            print("  ! hit max_tokens - output truncated; raise MAX_TOKENS "
                  "or ask for a shorter brief")
        break
    else:
        print(f"  ! gave up after {MAX_TURNS} turns")

    return "".join(collected).strip()


def clean(fragment: str) -> str:
    """Strip fences, drop any preamble, and close tags left open by truncation."""
    f = fragment.strip()
    for fence in ("```html", "```HTML", "```"):
        f = f.replace(fence, "")
    i = f.find("<div")
    if i > 0:
        f = f[i:]
    f = f.strip()

    # a truncated run can end mid-tag; cut back to the last complete one
    if f.rfind(">") < f.rfind("<"):
        f = f[:f.rfind("<")].rstrip()

    # drop a trailing partial element that never got its closing tag
    open_divs = f.count("<div") - f.count("</div>")
    if 0 < open_divs <= 6:
        f = f + ("\n</div>" * open_divs)
        print(f"  repaired {open_divs} unclosed <div> from truncation")

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

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(fragment + "\n")

    print(f"{OUT} written — {len(fragment):,} chars.")


if __name__ == "__main__":
    main()
