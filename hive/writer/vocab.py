"""Claim-type vocabulary for security-company competitive intelligence. Shared with the swarm prompts."""
from __future__ import annotations

CLAIM_TYPES: dict[str, str] = {
    "product_launch": "Product launches",
    "acquisition": "Acquisitions",
    "funding": "Funding",
    "breach_incident": "Breaches and incidents",
    "vulnerability_disclosure": "Vulnerability disclosures",
    "partnership": "Partnerships",
    "personnel": "People",
    "pricing": "Pricing",
    "earnings": "Earnings",
    "certification": "Certifications and compliance",
    "other": "Other",
}

PROFILE_SECTIONS: dict[str, tuple[str, ...]] = {
    "Positioning": ("product_launch", "pricing", "earnings", "certification", "other"),
    "Recent moves": ("product_launch", "acquisition", "funding", "partnership"),
    "Risks": ("breach_incident", "vulnerability_disclosure", "certification"),
    "People": ("personnel",),
}

PROFILE_GUIDANCE: dict[str, str] = {
    "Positioning": "what the company sells, to whom, and how it is positioned (products, pricing, earnings, certifications)",
    "Recent moves": "product launches, acquisitions, funding rounds and partnerships",
    "Risks": "breaches, security incidents, vulnerability disclosures, regulatory or compliance issues",
    "People": "executive hires, departures and leadership changes",
}


def label(claim_type: str) -> str:
    return CLAIM_TYPES.get(claim_type, CLAIM_TYPES["other"])
