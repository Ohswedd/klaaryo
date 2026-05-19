import re


# regex over LLM: deterministic, testable; see PRD section 3.1
ROLES = [
    "pizzaiolo", "cameriere", "cassiere", "scaffalista",
    "cuoco", "lavapiatti", "barista",
]

CITIES = [
    "milano", "roma", "torino", "napoli", "bologna", "firenze",
    "genova", "verona", "padova", "bari", "palermo",
]


def _first_match(text, keywords):
    pattern = r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(1).lower() if m else None


def extract_fields(raw_message):
    role = _first_match(raw_message, ROLES)
    city = _first_match(raw_message, CITIES)
    return {
        "role": role,
        "city": city.capitalize() if city else None,
    }
