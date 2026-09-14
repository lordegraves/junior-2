"""Read-only occupation and U.S. location lookups from packaged reference data."""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from importlib.resources import files
from typing import Any


def suggest_occupations(query: str, *, limit: int = 12) -> tuple[dict[str, str], ...]:
    terms = _terms(query)
    if not terms:
        return ()
    occupations, alternate_titles = _occupation_index()
    matches: list[tuple[int, str, dict[str, str]]] = []
    seen: set[str] = set()
    for occupation in occupations.values():
        label = str(occupation["title"])
        normalized = _normalize(label)
        if all(term in normalized for term in terms):
            seen.add(normalized)
            matches.append(
                (
                    _rank(normalized, terms),
                    label.casefold(),
                    {
                        "value": str(occupation["code"]),
                        "label": label,
                        "description": str(occupation["description"]),
                    },
                )
            )
    for normalized, item in alternate_titles.items():
        if normalized in seen or not all(term in normalized for term in terms):
            continue
        occupation = occupations[item["code"]]
        matches.append(
            (
                _rank(normalized, terms),
                item["label"].casefold(),
                {
                    "value": str(item["code"]),
                    "label": str(item["label"]),
                    "description": f"Related occupation: {occupation['title']}",
                },
            )
        )
    matches.sort(key=lambda match: (match[0], match[1]))
    return tuple(match[2] for match in matches[:limit])


def suggest_locations(query: str, *, limit: int = 12) -> tuple[dict[str, Any], ...]:
    cleaned = query.strip()
    if len(cleaned) < 2:
        return ()
    if cleaned.isdigit():
        matches = [area for area in _zip_areas() if area["zip"].startswith(cleaned)]
        return tuple(
            {
                "value": f"zip:{item['zip']}",
                "label": f"ZIP {item['zip']}",
                "latitude": float(item["latitude"]),
                "longitude": float(item["longitude"]),
            }
            for item in matches[:limit]
        )
    terms = _location_terms(cleaned)
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for place in _places():
        searchable = _normalize(
            f"{place['name']} {place['state']} {place['state_code']}"
        )
        if all(term in searchable for term in terms):
            label = f"{place['name']}, {place['state_code']}"
            matches.append(
                (
                    0 if searchable.startswith(" ".join(terms)) else 1,
                    label.casefold(),
                    {
                        "value": f"place:{place['state_code']}:{place['name']}",
                        "label": label,
                        "latitude": float(place["latitude"]),
                        "longitude": float(place["longitude"]),
                    },
                )
            )
    matches.sort(key=lambda match: (match[0], match[1]))
    return tuple(match[2] for match in matches[:limit])


def resolve_location(value: str) -> tuple[float, float] | None:
    cleaned = value.strip()
    zip_match = re.search(r"\b(\d{5})\b", cleaned)
    if zip_match:
        area = _zip_index().get(zip_match.group(1))
        if area:
            return float(area["latitude"]), float(area["longitude"])
    normalized = _normalize(cleaned)
    exact = _place_index().get(normalized)
    if exact:
        return float(exact["latitude"]), float(exact["longitude"])
    suggestions = suggest_locations(cleaned, limit=2)
    if len(suggestions) == 1:
        return float(suggestions[0]["latitude"]), float(suggestions[0]["longitude"])
    return None


def distance_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat_a, lon_a = map(math.radians, a)
    lat_b, lon_b = map(math.radians, b)
    lat_delta = lat_b - lat_a
    lon_delta = lon_b - lon_a
    haversine = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(lon_delta / 2) ** 2
    )
    return 3958.8 * 2 * math.asin(math.sqrt(haversine))


@lru_cache(maxsize=1)
def _occupation_index() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    occupations = {
        item["code"]: item for item in _load("occupations.json")["occupations"]
    }
    alternates: dict[str, dict[str, str]] = {}
    for item in _load("job_titles.json")["job_titles"]:
        if item["code"] in occupations:
            alternates.setdefault(
                _normalize(item["job_title"]),
                {"code": item["code"], "label": item["job_title"]},
            )
    return occupations, alternates


@lru_cache(maxsize=1)
def _places() -> tuple[dict[str, Any], ...]:
    return tuple(_load("us_places.json")["places"])


@lru_cache(maxsize=1)
def _zip_areas() -> tuple[dict[str, Any], ...]:
    return tuple(_load("us_zip_areas.json")["zip_areas"])


@lru_cache(maxsize=1)
def _place_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for place in _places():
        labels = (
            f"{place['name']}, {place['state_code']}",
            f"{place['name']}, {place['state']}",
            f"{place['name']} {place['state_code']}",
            f"{place['name']} {place['state']}",
        )
        for label in labels:
            index.setdefault(_normalize(label), place)
    return index


@lru_cache(maxsize=1)
def _zip_index() -> dict[str, dict[str, Any]]:
    return {item["zip"]: item for item in _zip_areas()}


@lru_cache(maxsize=4)
def _load(filename: str) -> dict[str, Any]:
    resource = files("junior.reference_data").joinpath(filename)
    return json.loads(resource.read_text(encoding="utf-8"))


def _rank(searchable: str, terms: list[str]) -> int:
    query = " ".join(terms)
    return 0 if searchable == query else 1 if searchable.startswith(query) else 2


def _terms(value: str) -> list[str]:
    return _normalize(value).split()


def _location_terms(value: str) -> list[str]:
    aliases = {
        "colorado": "co", "wyoming": "wy", "washington": "wa",
        "california": "ca", "new york": "ny", "texas": "tx",
    }
    normalized = _normalize(value)
    normalized = re.sub(r"^ft\s+", "fort ", normalized)
    for name, abbreviation in aliases.items():
        normalized = re.sub(rf"\b{re.escape(name)}\b", abbreviation, normalized)
    return normalized.split()


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
