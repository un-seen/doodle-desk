#!/usr/bin/env python3
"""Latest headlines from RSS/Atom channels, cached on disk. Standard library only.

    python news.py                 # print every channel in cast.toml
    python news.py bbc_world npr   # just these
"""
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import time
import tomllib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/.cache/doodle-news")
UA = "doodle-scenes/0.1 (+rss reader)"


def load_config(path=os.path.join(HERE, "cast.toml")):
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _text(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None:
            v = x.text or x.get("href") or ""
            if v.strip():
                return v.strip()
    return ""


def _clean(s, n=280):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]


def _when(s):
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for el in root.iter():           # drop namespaces so rss and atom read alike
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    items = []
    for it in list(root.iter("item")) + list(root.iter("entry")):
        title = _clean(_text(it, "title"), 200)
        if not title:
            continue
        link = _text(it, "link")
        if not link:
            le = it.find("link")
            link = le.get("href", "") if le is not None else ""
        when = _when(_text(it, "pubDate", "published", "updated", "date"))
        items.append({"title": title, "summary": _clean(_text(it, "description", "summary", "content")),
                      "link": link, "when": when.isoformat() if when else None})
    return items


def fetch(url, cache_minutes=30, timeout=15):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < cache_minutes * 60:
        return json.load(open(path))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        items = parse(r.read())
    json.dump(items, open(path, "w"))
    return items


NOT_NAMES = {"The", "A", "An", "US", "UK", "EU", "UN", "New", "North", "South", "East", "West", "Prime",
             "President", "Minister", "CEO", "National", "Office", "Senate", "House", "Supreme", "Court",
             "Federal", "State", "States", "United", "Republic", "Democrat", "Democratic", "Republican"}


def names_a_person(title):
    """Rough guess: two capitalised words in a row past the first word, neither a common title word
    (Jensen Huang, Scott Colom). Over-cautious on purpose: places like 'Clark County' trip it too."""
    words = re.findall(r"[A-Za-z][\w'’.-]*", title)[1:]
    for a, b in zip(words, words[1:]):
        if a[:1].isupper() and b[:1].isupper() and a not in NOT_NAMES and b not in NOT_NAMES \
                and not a.isupper() and not b.isupper():
            return True
    return False


def headlines(channels, cfg):
    """{channel: [items]} for the named channels: newest first, recent only, avoided topics out."""
    st = cfg.get("settings", {})
    per, max_age = st.get("headlines_per_channel", 6), st.get("max_age_hours", 48)
    avoid = [w.lower() for w in st.get("avoid", [])]
    now = datetime.now(timezone.utc)
    out = {}
    for ch in channels:
        url = cfg["channels"].get(ch)
        if not url:
            print(f"unknown channel {ch!r}", file=sys.stderr)
            continue
        try:
            items = fetch(url, st.get("cache_minutes", 30))
        except Exception as e:
            print(f"{ch}: {e}", file=sys.stderr)
            continue
        keep = []
        for it in items:
            text = (it["title"] + " " + it["summary"]).lower()
            if any(re.search(r"\b" + re.escape(w.rstrip("*")) + ("" if w.endswith("*") else r"\b"), text)
                   for w in avoid):
                continue
            if it["when"] and (now - datetime.fromisoformat(it["when"])).total_seconds() > max_age * 3600:
                continue
            if st.get("skip_named_people", True) and names_a_person(it["title"]):
                continue
            if len(it["title"].split()) < st.get("min_words", 0):
                continue
            keep.append(it | {"channel": ch})
        keep.sort(key=lambda it: it["when"] or "", reverse=True)
        out[ch] = keep[:per]
    return out


if __name__ == "__main__":
    cfg = load_config()
    for ch, items in headlines(sys.argv[1:] or list(cfg["channels"]), cfg).items():
        print(f"== {ch}")
        for it in items:
            print(f"  {(it['when'] or '')[:16]}  {it['title']}")
