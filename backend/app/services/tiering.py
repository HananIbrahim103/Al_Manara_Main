"""Agent 1, risk tiering. Plain rules, no LLM.

Each rule sets a floor. The tier is the highest floor any rule sets, so the answer to
"why is this high risk?" is always the list of rules that fired.
"""
from dataclasses import dataclass
from typing import Any

from app import catalog

_RANK = {tier: i for i, tier in enumerate(catalog.RISK_TIERS)}
_SERIOUS_OR_WORSE = ("serious", "severe")

# (rule id, floor, condition, reason)
RULES = [
    ("T1", "medium", lambda c: c.data_sensitivity == "personal",
     "Personal data is processed."),
    ("T2", "high", lambda c: c.data_sensitivity == "sensitive_personal",
     "Sensitive personal data is processed (for example identity documents, health, disability or income)."),
    ("T3", "medium", lambda c: c.consequence_of_error == "moderate",
     "An error has a moderate consequence for the person affected."),
    ("T4", "high", lambda c: c.consequence_of_error in _SERIOUS_OR_WORSE,
     "An error has a serious consequence for the person affected."),
    ("T5", "medium", lambda c: c.audience_type == "citizen_facing",
     "The public uses it directly."),
    ("T6", "high", lambda c: c.audience_type == "citizen_facing" and c.vulnerable_users,
     "The public uses it directly and vulnerable users are among them, who may not spot an AI error."),
    ("T7", "high", lambda c: c.autonomy_level == "decides_with_review",
     "The AI makes the decision and a human only reviews it afterwards."),
    ("T8", "critical", lambda c: c.autonomy_level == "autonomous",
     "The AI acts without a human decision."),
    ("T9", "high", lambda c: c.human_oversight == "exception_only" and c.consequence_of_error in _SERIOUS_OR_WORSE,
     "Humans only look at exceptions although errors are serious."),
    ("T10", "critical", lambda c: c.consequence_of_error == "severe" and c.vulnerable_users,
     "A severe consequence falls on vulnerable users."),
    ("T11", "critical", lambda c: c.consequence_of_error == "severe" and c.autonomy_level in ("decides_with_review", "autonomous"),
     "A severe consequence combined with the AI making the decision."),
]
NO_OVERSIGHT_RULE = ("T12", "No human oversight at all: the tier is raised one level.")


@dataclass
class TierResult:
    risk_tier: str
    track: str
    rationale: list[dict]  # every rule that fired: {rule, floor, reason, decisive}

    def as_dict(self) -> dict:
        return {"risk_tier": self.risk_tier, "track": self.track, "rationale": self.rationale,
                "checks_on_this_track": catalog.TRACK_CHECKS[self.track]}


def assess_tier(card: Any) -> TierResult:
    """`card` is anything with the Use-Case Card fields (database row or request body)."""
    fired = [{"rule": rule_id, "floor": floor, "reason": reason} for rule_id, floor, applies, reason in RULES if applies(card)]
    tier = max((f["floor"] for f in fired), key=_RANK.get, default="low")
    if card.human_oversight == "none" and tier != "critical":
        tier = catalog.RISK_TIERS[_RANK[tier] + 1]
        fired.append({"rule": NO_OVERSIGHT_RULE[0], "floor": tier, "reason": NO_OVERSIGHT_RULE[1]})
    if not fired:
        fired.append({"rule": "T0", "floor": "low",
                      "reason": "No rule raised the tier: internal use, no personal data, minor consequence, a human stays in control."})
    for entry in fired:
        entry["decisive"] = entry["floor"] == tier
    return TierResult(risk_tier=tier, track=catalog.TRACK_FOR_TIER[tier], rationale=fired)


def required_checks(card: Any, track: str) -> tuple[list[str], list[dict]]:
    """Checks this use case needs on this track, and the ones left out with the reason."""
    required, dropped = [], []
    arabic = any(lang.startswith("ar") for lang in card.languages)
    for check in catalog.TRACK_CHECKS[track]:
        reason = None
        if check == "english" and "en" not in card.languages:
            reason = "English is not a language of this service."
        elif check == "arabic_msa" and "ar-msa" not in card.languages:
            reason = "Modern Standard Arabic is not a language of this service."
        elif check == "arabic_gulf" and "ar-gulf" not in card.languages:
            reason = "Gulf dialect is not a language of this service."
        elif check == "name_transliteration" and not arabic:
            reason = "No Arabic input, so no Arabic/Latin name matching."
        elif check == "accessibility" and card.audience_type != "citizen_facing" and not card.vulnerable_users:
            reason = "Internal tool with no vulnerable users: accessibility of the public service is not in scope."
        if reason:
            dropped.append({"check": check, "reason": reason})
        else:
            required.append(check)
    # A language the service offers is always tested, even on the fast track.
    for language, check in (("ar-msa", "arabic_msa"), ("ar-gulf", "arabic_gulf"), ("en", "english")):
        if language in card.languages and check not in required:
            required.append(check)
    return required, dropped
