HIGH_FIT_CATEGORIES = {
    "personal trainer": 30,
    "online coach": 30,
    "gym": 25,
    "boutique gym": 30,
    "recovery studio": 30,
    "wellness clinic": 28,
    "med spa": 24,
    "physical therapy": 24,
    "chiropractor": 22,
    "nutrition coach": 22,
    "massage therapist": 18,
}


def calculate_score(data: dict) -> int:
    score = 0
    category = (data.get("category") or "").strip().lower()
    score += HIGH_FIT_CATEGORIES.get(category, 10)

    if data.get("owner_name"):
        score += 15
    if data.get("public_phone"):
        score += 15
    if data.get("public_email"):
        score += 15
    if data.get("website"):
        score += 10
    if data.get("instagram_url"):
        score += 8
    if data.get("linkedin_url"):
        score += 5
    if data.get("partnership_angle"):
        score += 2

    return min(score, 100)
