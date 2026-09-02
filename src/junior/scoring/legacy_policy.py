"""Junior 1.x-compatible keyword, title, and location policy signals."""

from __future__ import annotations

from dataclasses import dataclass

from junior.domain.lifecycle import JobPosting

TITLE_WEIGHT = 3
POSITIVE_KEYWORDS = {
    "linux": 10,
    "infrastructure": 10,
    "sre": 10,
    "site reliability": 10,
    "reliability": 8,
    "kubernetes": 8,
    "k8s": 8,
    "cluster": 8,
    "hpc": 10,
    "slurm": 10,
    "gpu": 8,
    "datacenter": 8,
    "data center": 8,
    "hardware": 7,
    "systems": 6,
    "observability": 6,
    "incident": 5,
    "automation": 5,
    "python": 4,
    "networking": 4,
    "storage": 4,
}
NEGATIVE_TITLE_KEYWORDS = {
    "account executive": -20,
    "sourcing": -30,
    "procurement": -30,
    "supply chain": -30,
    "vendor": -20,
    "vendor management": -25,
    "business operations": -20,
    "sales": -15,
    "marketing": -15,
    "legal": -12,
    "finance": -12,
    "recruiter": -12,
    "recruiting": -12,
    "people operations": -12,
    "hr": -12,
    "customer success": -10,
    "product marketing": -10,
    "communications": -10,
}
ALLOWED_LOCATIONS = {
    "remote",
    "northern colorado",
    "fort collins",
    "loveland",
    "greeley",
    "cheyenne",
    "cheyenne wy",
    "cheyenne wyoming",
}
CONDITIONAL_LOCATIONS = {"denver": -25, "boulder": -25}
SKIPPED_LOCATIONS = {
    "san francisco",
    "new york",
    "new york city",
    "seattle",
    "london",
    "dublin",
    "sydney",
    "australia",
    "uk",
    "united kingdom",
    "ireland",
    "canada",
    "toronto",
    "vancouver",
    "europe",
    "germany",
    "france",
    "singapore",
}
EXCLUDED_TITLE_KEYWORDS = {
    "account executive",
    "business",
    "communications",
    "customer success",
    "finance",
    "fx",
    "gtm",
    "investments",
    "legal",
    "liquidity",
    "marketing",
    "people",
    "product manager",
    "recruiter",
    "recruiting",
    "sales",
    "sourcing",
    "design execution",
}


@dataclass(frozen=True, slots=True)
class LegacyPolicyResult:
    score: int
    location_status: str
    top_match_eligible: bool
    review_eligible: bool
    reasons: tuple[str, ...]


def evaluate_legacy_policy(posting: JobPosting) -> LegacyPolicyResult:
    title = _clean(posting.title)
    body = _clean(" ".join(filter(None, (posting.description, posting.remote_status))))
    location = _clean(posting.location or "")
    score = 0
    reasons: list[str] = []
    for keyword, points in POSITIVE_KEYWORDS.items():
        if keyword in title:
            weighted = points * TITLE_WEIGHT
            score += weighted
            reasons.append(f"+{weighted} title:{keyword}")
        elif keyword in body:
            score += points
            reasons.append(f"+{points} body:{keyword}")
    for keyword, points in NEGATIVE_TITLE_KEYWORDS.items():
        if keyword in title:
            weighted = points * TITLE_WEIGHT
            score += weighted
            reasons.append(f"{weighted} title:{keyword}")
    for keyword, points in CONDITIONAL_LOCATIONS.items():
        if keyword in location:
            score += points
            reasons.append(f"{points} location_conditional:{keyword}")
    for keyword in SKIPPED_LOCATIONS:
        if keyword in location:
            score -= 100
            reasons.append(f"-100 location_skipped:{keyword}")
    for keyword in ALLOWED_LOCATIONS:
        if keyword in location:
            reasons.append(f"+0 location_allowed:{keyword}")
    location_status = classify_location(location)
    negative_title = any(
        reason.startswith("-") and " title:" in reason for reason in reasons
    )
    excluded = next((item for item in EXCLUDED_TITLE_KEYWORDS if item in title), None)
    strong_title = any(
        reason.startswith("+") and " title:" in reason for reason in reasons
    )
    kubernetes_risk = _production_kubernetes_primary_risk(title, body)
    top = (
        location_status in {"allowed", "allowed_with_travel"}
        and score >= 120
        and not negative_title
        and excluded is None
        and strong_title
        and not kubernetes_risk
    )
    review = (
        location_status not in {"skipped", "unknown"}
        and score >= 100
        and strong_title
        and excluded is None
    )
    if excluded:
        reasons.append(f"excluded_title_keyword:{excluded}")
    if kubernetes_risk:
        reasons.append("production_kubernetes_primary_risk")
    return LegacyPolicyResult(score, location_status, top, review, tuple(reasons))


def classify_location(location: str) -> str:
    if not location:
        return "unknown"
    allowed = any(item in location for item in ALLOWED_LOCATIONS)
    conditional = any(item in location for item in CONDITIONAL_LOCATIONS)
    skipped = any(item in location for item in SKIPPED_LOCATIONS)
    if allowed and _limited_travel(location):
        return "allowed_with_travel"
    if allowed and (skipped or conditional or _travel_required(location)):
        return "mixed"
    if allowed:
        return "allowed"
    if conditional:
        return "conditional"
    if skipped:
        return "skipped"
    return "unknown"


def _travel_required(value: str) -> bool:
    return any(
        marker in value
        for marker in (
            "travel required",
            "requires travel",
            "travel:",
            "travel -",
            "travel up to",
        )
    )


def _limited_travel(value: str) -> bool:
    return any(
        marker in value
        for marker in (
            "travel required 10-20%",
            "travel 10-20%",
            "10-20% travel",
            "up to 20% travel",
            "travel up to 20%",
        )
    )


def _production_kubernetes_primary_risk(title: str, body: str) -> bool:
    combined = f"{title} {body}"
    primary = any(
        marker in combined
        for marker in (
            "production kubernetes",
            "production k8s",
            "kubernetes platform",
            "k8s platform",
            "kubernetes clusters",
            "k8s clusters",
            "kubernetes control plane",
            "own kubernetes",
            "operate kubernetes",
            "manage kubernetes",
            "administer kubernetes",
        )
    ) or any(marker in title for marker in ("kubernetes", "k8s"))
    counterevidence = sum(
        marker in combined
        for marker in (
            "hpc",
            "slurm",
            "gpu",
            "datacenter",
            "data center",
            "bare metal",
            "hardware",
            "cluster systems",
            "linux systems",
            "research computing",
            "scientific computing",
            "storage",
        )
    )
    return primary and counterevidence < 2


def _clean(value: str) -> str:
    return " ".join(value.casefold().split())
