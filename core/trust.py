import json
from pathlib import Path

TRUST_FILE = Path("data/trust_levels.json")
UNKNOWN_FILE = Path("data/unknown_sources.json")
VOTES_FILE = Path("data/trust_votes.json")

def update_trust_levels_from_votes(vote_threshold=5):
    if not VOTES_FILE.exists() or not UNKNOWN_FILE.exists():
        return []

    with open(VOTES_FILE, "r") as f:
        votes_data = json.load(f)

    with open(UNKNOWN_FILE, "r") as f:
        unknown_sources = set(json.load(f))

    if TRUST_FILE.exists():
        with open(TRUST_FILE, "r") as f:
            trust_levels = json.load(f)
    else:
        trust_levels = {}

    promoted = []

    for domain in unknown_sources:
        vote_info = votes_data.get(domain, {"up": 0, "down": 0})
        score = vote_info["up"] - vote_info["down"]

        if score >= vote_threshold:
            trust_levels[domain] = min(10, 5 + score // 2)
            promoted.append(domain)

    if promoted:
        with open(TRUST_FILE, "w") as f:
            json.dump(trust_levels, f, indent=2)

        unknown_sources -= set(promoted)
        with open(UNKNOWN_FILE, "w") as f:
            json.dump(sorted(list(unknown_sources)), f, indent=2)

    return promoted
