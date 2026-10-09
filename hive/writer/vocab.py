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
    "Positioning": (
        "what the company sells, to whom, and how it is positioned (products, pricing, analyst recognition, certifications). "
        "Financial results only with each figure labelled (e.g. revenue, ARR, guidance); skip any number whose meaning the passage does not state"
    ),
    "Recent moves": "product launches, acquisitions, funding rounds and partnerships by the company itself",
    "Risks": (
        "breaches, incidents, vulnerabilities or regulatory problems AFFECTING THE COMPANY'S OWN products, customers or operations. "
        "Exclude the company's threat research or advisories about other vendors, attackers or campaigns: that is its work, not its risk"
    ),
    "People": (
        "executive hires, departures and promotions with a date or 'effective' wording. "
        "Exclude standing titles from filing signature blocks (e.g. 'X serves as CEO') and routine board policy approvals"
    ),
}


def label(claim_type: str) -> str:
    return CLAIM_TYPES.get(claim_type, CLAIM_TYPES["other"])
