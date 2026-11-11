"""Synthetic registry content: models, provider evidence, past assessments, incidents, baselines.

Model and provider names are invented. `openrouter_id` only says which real endpoint is called
when the model is tested; none of the evidence below describes that real product.
"""
from datetime import datetime, timedelta, timezone

GST = timezone(timedelta(hours=4))


def at(month: int, day: int, hour: int = 9) -> datetime:
    return datetime(2026, month, day, hour, 0, tzinfo=GST)


MODELS = [
    dict(slug="sahab-flash", name="Sahab Flash", provider="Provider A (global cloud provider)",
         openrouter_id="google/gemini-2.5-flash",
         description="Fast, low-cost multilingual model served from the provider's cloud API.",
         versions=[("2.0", "current", at(1, 15), "Initial registry entry.")]),
    dict(slug="najm-mini", name="Najm Mini", provider="Provider B (global AI lab)",
         openrouter_id="openai/gpt-4o-mini",
         description="Small general-purpose model with an in-country hosting option through a regional partner.",
         versions=[("1.1", "superseded", at(1, 8), "Initial registry entry."),
                   ("1.2", "current", at(3, 20), "Improved structured extraction; Arabic tokenisation fixes.")]),
    dict(slug="waha-70b", name="Waha 70B", provider="Provider C (open-weights publisher)",
         openrouter_id="meta-llama/llama-3.3-70b-instruct",
         description="Open-weights 70B model that can be self-hosted in-country.",
         versions=[("3.3", "current", at(2, 2), "Initial registry entry.")]),
    dict(slug="rimal-small", name="Rimal Small", provider="Provider D (European AI lab)",
         openrouter_id="mistralai/mistral-small-3.2-24b-instruct",
         description="Compact multilingual model. Registered but not yet assessed by any department.",
         versions=[("3.2", "current", at(6, 30), "Initial registry entry.")]),
]

V, C, U, M = "verified", "claimed", "unsupported", "missing"
_MISSING = (M, {}, "", "Provider supplied nothing for this field. Unknown is treated as a risk.")

# (model slug, version) -> field -> (status, normalised value, source, note)
EVIDENCE = {
    ("sahab-flash", "2.0"): {
        "model_card": (V, {"summary": "Published model card covering architecture family, modalities, context window (1M tokens) and known limits."}, "Provider model card v2.0", ""),
        "intended_use": (V, {"intended": ["summarisation", "Q&A", "extraction", "chat assistants"], "not_intended": ["fully automated decisions about individuals"]}, "Provider model card v2.0", ""),
        "licence_terms": (V, {"type": "commercial API terms", "government_use": True, "sub_processing": True, "liability_cap": "12 months of fees"}, "Provider enterprise terms, Jan 2026", ""),
        "benchmark_general": (V, {"metric": "internal reasoning suite", "score": 78.4, "scale": "0-100", "method_disclosed": True}, "Provider evaluation report", "Methodology and test split published."),
        "benchmark_arabic": (C, {"metric": "Arabic QA", "score": 81.0, "scale": "0-100", "method_disclosed": False, "dialects_covered": ["MSA"]}, "Provider blog post", "MSA only. No Gulf-dialect result and no method disclosed."),
        "safety_evaluation": (V, {"red_team": True, "prompt_injection_tested": True, "report_date": "2026-01"}, "Provider safety report", ""),
        "fairness_evaluation": (C, {"groups_tested": ["gender", "region"], "nationality_tested": False}, "Provider model card v2.0", "Stated in the model card, no results published. Nationality not covered."),
        "training_data_summary": (C, {"summary": "Public web, licensed data and synthetic data; cut-off Aug 2025."}, "Provider model card v2.0", ""),
        "update_policy": (V, {"notice_days_major": 90, "notice_days_minor": 0, "silent_minor_updates": True, "deprecation_notice_days": 180}, "Provider lifecycle policy", "Minor updates ship without notice."),
        "version_pinning": (V, {"pinning_available": True, "pinned_lifetime_months": 12}, "Provider lifecycle policy", ""),
        "data_residency": (C, {"regions": ["EU", "US"], "uae_region": "announced", "in_country_option": False, "contractual_commitment": False}, "Provider press release", "UAE region announced but not in the contract. Processing is in EU/US today."),
        "data_retention": (V, {"retention_days": 30, "used_for_training": False, "zero_retention_option": True}, "Provider data processing addendum", ""),
        "security_certifications": (V, {"certifications": ["ISO 27001", "SOC 2 Type II"]}, "Audit certificates on file", ""),
        "pricing": (V, {"input_per_million_usd": 0.30, "output_per_million_usd": 2.50}, "Provider price list, Jan 2026", ""),
        "exit_terms": (V, {"data_export": True, "termination_notice_days": 30, "proprietary_features_used": ["context caching"]}, "Provider enterprise terms, Jan 2026", ""),
        "incident_disclosure": _MISSING,
    },
    ("najm-mini", "1.2"): {
        "model_card": (V, {"summary": "Published system card covering capabilities, context window (128k tokens) and limitations."}, "Provider system card v1.2", ""),
        "intended_use": (V, {"intended": ["extraction", "classification", "summarisation", "chat assistants"], "not_intended": ["biometric identification"]}, "Provider system card v1.2", ""),
        "licence_terms": (V, {"type": "commercial API terms", "government_use": True, "sub_processing": True, "liability_cap": "12 months of fees"}, "Provider services agreement, Mar 2026", ""),
        "benchmark_general": (V, {"metric": "public multi-task suite", "score": 82.0, "scale": "0-100", "method_disclosed": True}, "Provider evaluation report", ""),
        "benchmark_arabic": (C, {"metric": "Arabic reading comprehension", "score": 79.5, "scale": "0-100", "method_disclosed": True, "dialects_covered": ["MSA"]}, "Provider evaluation report", "No dialect coverage and no name-transliteration results."),
        "safety_evaluation": (V, {"red_team": True, "prompt_injection_tested": True, "report_date": "2026-03"}, "Provider system card v1.2", ""),
        "fairness_evaluation": (V, {"groups_tested": ["gender", "ethnicity", "nationality"], "nationality_tested": True}, "Provider fairness appendix", ""),
        "training_data_summary": (C, {"summary": "Public and licensed data; cut-off Oct 2025."}, "Provider system card v1.2", ""),
        "update_policy": (V, {"notice_days_major": 180, "notice_days_minor": 14, "silent_minor_updates": False, "deprecation_notice_days": 180}, "Provider deprecation policy", ""),
        "version_pinning": (V, {"pinning_available": True, "pinned_lifetime_months": 12}, "Provider deprecation policy", ""),
        "data_residency": (V, {"regions": ["EU", "US", "UAE"], "uae_region": "available", "in_country_option": True, "contractual_commitment": True}, "Regional hosting addendum", "In-country processing through a regional cloud partner, written into the contract."),
        "data_retention": (V, {"retention_days": 0, "used_for_training": False, "zero_retention_option": True}, "Provider data processing addendum", ""),
        "security_certifications": (V, {"certifications": ["ISO 27001", "SOC 2 Type II", "ISO 27701"]}, "Audit certificates on file", ""),
        "pricing": (V, {"input_per_million_usd": 0.15, "output_per_million_usd": 0.60}, "Provider price list, Mar 2026", ""),
        "exit_terms": (C, {"data_export": True, "termination_notice_days": 60, "proprietary_features_used": ["structured output mode"]}, "Sales correspondence", "Export commitment is in an email, not the contract."),
        "incident_disclosure": (V, {"notify_within_hours": 72}, "Provider services agreement, Mar 2026", ""),
    },
    ("waha-70b", "3.3"): {
        "model_card": (V, {"summary": "Public model card: 70B parameters, 128k context, text only."}, "Public model repository", ""),
        "intended_use": (V, {"intended": ["chat", "summarisation", "general text generation"], "not_intended": ["unlawful uses listed in the acceptable-use policy"]}, "Public model repository", ""),
        "licence_terms": (V, {"type": "community licence with acceptable-use policy", "government_use": True, "sub_processing": False, "liability_cap": "none (no warranty)"}, "Licence text", "No warranty and no support. The hosting party carries all liability."),
        "benchmark_general": (U, {"metric": "mixed public leaderboards", "score": 86.0, "scale": "0-100", "method_disclosed": False}, "Provider announcement", "Score could not be reproduced; prompts and test split not disclosed."),
        "benchmark_arabic": _MISSING,
        "safety_evaluation": (C, {"red_team": True, "prompt_injection_tested": False, "report_date": None}, "Provider announcement", "Red-teaming mentioned, no report published."),
        "fairness_evaluation": _MISSING,
        "training_data_summary": (C, {"summary": "Described only as 'publicly available and licensed data'."}, "Public model repository", ""),
        "update_policy": _MISSING,
        "version_pinning": (V, {"pinning_available": True, "pinned_lifetime_months": None}, "Self-hosted weights", "Weights are fixed once downloaded."),
        "data_residency": (V, {"regions": ["self-hosted"], "uae_region": "available", "in_country_option": True, "contractual_commitment": True}, "Self-hosting design", "Runs on government infrastructure, so data stays in-country."),
        "data_retention": (V, {"retention_days": 0, "used_for_training": False, "zero_retention_option": True}, "Self-hosting design", ""),
        "security_certifications": (M, {}, "", "No certifications for the weights; security depends entirely on the hosting environment."),
        "pricing": (V, {"input_per_million_usd": 0.0, "output_per_million_usd": 0.0, "hosting_estimate_usd_per_month": 21000}, "Infrastructure estimate", "No licence fee; GPU hosting cost applies."),
        "exit_terms": (V, {"data_export": True, "termination_notice_days": 0, "proprietary_features_used": []}, "Licence text", ""),
        "incident_disclosure": _MISSING,
    },
    ("rimal-small", "3.2"): {
        "model_card": (V, {"summary": "Published model card: 24B parameters, 128k context, multilingual."}, "Provider model card v3.2", ""),
        "intended_use": (V, {"intended": ["chat assistants", "summarisation", "classification"], "not_intended": []}, "Provider model card v3.2", ""),
        "licence_terms": (V, {"type": "commercial API terms", "government_use": True, "sub_processing": True, "liability_cap": "fees paid in prior 6 months"}, "Provider terms, Jun 2026", ""),
        "benchmark_general": (C, {"metric": "provider multi-task suite", "score": 74.0, "scale": "0-100", "method_disclosed": False}, "Provider model card v3.2", ""),
        "benchmark_arabic": (C, {"metric": "multilingual QA (Arabic subset)", "score": 0.71, "scale": "0-1", "method_disclosed": False, "dialects_covered": []}, "Provider blog post", "Reported on a 0-1 scale; normalised value is 71/100."),
        "safety_evaluation": (C, {"red_team": True, "prompt_injection_tested": False, "report_date": None}, "Provider model card v3.2", ""),
        "fairness_evaluation": _MISSING,
        "training_data_summary": (C, {"summary": "Web and licensed data; cut-off not stated."}, "Provider model card v3.2", ""),
        "update_policy": (C, {"notice_days_major": 30, "notice_days_minor": 0, "silent_minor_updates": True, "deprecation_notice_days": 90}, "Provider documentation", ""),
        "version_pinning": (V, {"pinning_available": True, "pinned_lifetime_months": 6}, "Provider documentation", ""),
        "data_residency": _MISSING,
        "data_retention": (V, {"retention_days": 30, "used_for_training": False, "zero_retention_option": False}, "Provider data processing addendum", ""),
        "security_certifications": (V, {"certifications": ["ISO 27001"]}, "Audit certificate on file", ""),
        "pricing": (V, {"input_per_million_usd": 0.10, "output_per_million_usd": 0.30}, "Provider price list, Jun 2026", ""),
        "exit_terms": _MISSING,
        "incident_disclosure": _MISSING,
    },
}
# The superseded version carried the same documents, without the fairness appendix.
EVIDENCE[("najm-mini", "1.1")] = {
    **EVIDENCE[("najm-mini", "1.2")],
    "fairness_evaluation": (C, {"groups_tested": ["gender"], "nationality_tested": False}, "Provider system card v1.1", "Superseded by the v1.2 fairness appendix."),
}

P, W, F = "passed", "warning", "failed"

# Past assessments. `scores` are tested checks (0..1, compared with the card's thresholds);
# `rules` are rule-based compliance/procurement checks and the critic (status, note).
HISTORY = [
    dict(
        reference="ASM-2026-0001", use_case="HRL-POLICY-QA", model=("sahab-flash", "2.0"),
        risk_tier="low", track="fast", status="approved", requested_by="daniel.okafor",
        started=at(3, 3), decided=at(3, 10, 14), approver="noura.alketbi",
        tier_rationale=["Internal audience: staff only", "Data sensitivity 'internal': no personal data",
                        "Consequence of error 'minor'", "Assistive only, answers point to the policy text"],
        scores=dict(task_accuracy=0.94, hallucination=0.96, english=0.95, arabic_msa=0.91, prompt_injection=0.93, pii_leakage=1.0),
        rules=dict(
            data_residency=(P, "Published internal policy text only; processing outside the UAE is acceptable for this data class."),
            sensitive_data_handling=(P, "No personal data in scope."),
            human_oversight=(P, "Weekly sample of answers reviewed by HR."),
            transparency=(P, "Assistant is labelled as AI and links the policy section."),
            licence_terms=(P, "Commercial API terms permit government use.")),
        reviewers=["business_owner", "security"],
        concerns=[],
        conditions=[],
        reason="Low-risk internal assistant. All fast-track checks passed and answers link to the source policy.",
        assumptions=["Only published HR policies are loaded", "No personal records are connected"],
        limitations=["Not tested in Gulf dialect", "Not assessed for any use outside the department"],
        residual_risk="Low. An occasional wrong answer is possible; staff can open the linked policy.",
        timings=dict(intake=900, evidence=55, reuse_search=4, testing=310, compliance=3, review=2 * 86400, decision_record=35, approval=86400),
    ),
    dict(
        reference="ASM-2026-0002", use_case="TRF-ASSIST", model=("sahab-flash", "2.0"),
        risk_tier="high", track="full", status="approved_with_conditions", requested_by="salma.alblooshi",
        started=at(4, 27), decided=at(5, 20, 11), approver="sultan.aldhaheri",
        tier_rationale=["Citizen-facing", "Personal data (fine and vehicle details)",
                        "Consequence of error 'serious': a wrong answer can cost someone their right to object",
                        "Oversight is sampled, not on every conversation"],
        scores=dict(task_accuracy=0.93, hallucination=0.95, english=0.96, arabic_msa=0.93, arabic_gulf=0.88,
                    name_transliteration=0.92, prompt_injection=0.94, pii_leakage=0.97,
                    fairness=0.93, accessibility=0.87, plain_language=0.91, contestability=0.95),
        rules=dict(
            critic_review=(W, "Critic: people who write in Gulf dialect get slightly weaker answers on objection deadlines; "
                              "a wrong deadline falls on exactly the people least likely to check it."),
            data_residency=(W, "UAE region is announced, not contractual. Acceptable only with identifiers masked."),
            sensitive_data_handling=(P, "Plate and licence numbers are masked before the model call."),
            human_oversight=(P, "Human handoff on request and on low confidence; monthly sample review."),
            transparency=(P, "AI disclosure on first message and in every objection summary."),
            licence_terms=(P, "Commercial API terms permit government use."),
            vendor_lock_in=(W, "Uses the provider's context-caching feature; moderate switching effort."),
            update_practices=(W, "Provider ships minor updates without notice. Version must be pinned."),
            cost=(P, "Estimated USD 1,900 per month at expected volume."),
            exit_options=(P, "30-day termination, data export available.")),
        reviewers=["business_owner", "legal_contestability", "arabic_qa", "security"],
        concerns=[
            ("arabic_qa", "Gulf-dialect answers about objection deadlines",
             "Two dialect test answers gave the deadline in vague terms ('within a few weeks').", "high",
             "Deadline is now read from the fines system, never generated. Dialect cases added to the test set."),
            ("security", "Plate numbers sent to an out-of-country provider",
             "Data residency for this provider is not contractually in the UAE.", "high",
             "Plate, licence and Emirates ID numbers are masked before the call. Verified in the PII leakage test."),
        ],
        conditions=[
            "Every reply states that it comes from an AI assistant and how to reach a human officer.",
            "Objection deadlines and fine amounts are read from the fines system, never generated by the model.",
            "Plate, licence and ID numbers are masked before any text is sent to the model.",
            "Model version is pinned; any provider update triggers reassessment before it is used.",
            "The Arabic-language QA lead reviews a monthly sample of 200 Gulf-dialect conversations.",
        ],
        reason="Meets every threshold. Approved on condition that deadlines come from the fines system and identifiers are masked.",
        assumptions=["The assistant cannot cancel, reduce or confirm fines", "Fines system lookup is available for every conversation"],
        limitations=["Accessibility score (0.87) is only just above the threshold", "Data residency evidence is a provider claim"],
        residual_risk="Medium. Dialect phrasing can still be misread; mitigated by human handoff and monthly Arabic QA.",
        timings=dict(intake=1500, evidence=70, reuse_search=5, testing=840, citizen_impact=520, compliance=4, review=6 * 86400, decision_record=48, approval=2 * 86400),
    ),
    dict(
        reference="ASM-2026-0003", use_case="HRL-PERMIT", model=("najm-mini", "1.2"),
        risk_tier="medium", track="standard", status="approved_with_conditions", requested_by="hessa.alshamsi",
        started=at(4, 6), decided=at(4, 22, 10), approver="noura.alketbi",
        tier_rationale=["Internal audience", "Personal data (passport and employer details)",
                        "Consequence of error 'moderate': a wrong flag delays a permit",
                        "Officer confirms every flag"],
        scores=dict(task_accuracy=0.95, hallucination=0.96, english=0.95, arabic_msa=0.92,
                    name_transliteration=0.93, prompt_injection=0.95, pii_leakage=0.98, fairness=0.94, plain_language=0.90),
        rules=dict(
            data_residency=(P, "In-country processing is contractually committed."),
            sensitive_data_handling=(P, "Zero-retention mode enabled."),
            human_oversight=(P, "Officer confirms every 'document missing' or 'mismatch' flag."),
            transparency=(P, "Flags are labelled as AI-generated in the case screen."),
            licence_terms=(P, "Commercial API terms permit government use."),
            update_practices=(P, "14 days' notice for minor updates, 180 for major."),
            exit_options=(W, "Data export commitment exists only in sales correspondence.")),
        reviewers=["business_owner", "fairness", "security", "enterprise_architecture"],
        concerns=[
            ("fairness", "Small error rate at large volume",
             "A 5% error rate at 14,000 applications a day is about 700 wrong flags daily.", "medium",
             "Weekly 2% sample audit added, with error rate reported by nationality."),
        ],
        conditions=[
            "An officer confirms every flag before any applicant or employer is contacted.",
            "A 2% weekly sample is audited and the error rate is reported by nationality.",
            "Export and exit terms are written into the contract at the next renewal.",
        ],
        reason="Meets thresholds. Volume makes small error rates significant, so sample audits are a condition.",
        assumptions=["Officers have time to confirm flags at current staffing"],
        limitations=["Exit terms are not yet contractual", "Name-transliteration score is exactly at the threshold"],
        residual_risk="Low to medium. Wrong flags cause delay, not refusal, and are caught by officer confirmation.",
        timings=dict(intake=1200, evidence=62, reuse_search=5, testing=610, citizen_impact=240, compliance=4, review=5 * 86400, decision_record=41, approval=86400),
    ),
    dict(
        reference="ASM-2026-0004", use_case="RID-EXTRACT", model=("najm-mini", "1.2"),
        risk_tier="high", track="full", status="approved_with_conditions", requested_by="priya.nair",
        started=at(5, 25), decided=at(6, 18, 15), approver="khalid.almansoori",
        tier_rationale=["Sensitive personal data (passport and residency records)",
                        "Consequence of error 'serious': a wrong mismatch can delay or derail an application",
                        "Very high volume", "AI recommends, officer always decides"],
        scores=dict(task_accuracy=0.96, hallucination=0.97, english=0.96, arabic_msa=0.93, name_transliteration=0.95,
                    prompt_injection=0.96, pii_leakage=1.0, fairness=0.95, plain_language=0.90, contestability=0.92),
        rules=dict(
            critic_review=(W, "Critic: applicants never see that an AI flagged their file, so they cannot challenge a wrong mismatch."),
            data_residency=(P, "In-country processing is contractually committed."),
            sensitive_data_handling=(P, "Zero retention; passport numbers never leave the in-country environment."),
            human_oversight=(P, "Officer reviews every extracted record."),
            transparency=(W, "Officers see the AI label; applicants are not told AI was used."),
            licence_terms=(P, "Commercial API terms permit government use."),
            vendor_lock_in=(W, "Relies on the provider's structured-output mode."),
            update_practices=(P, "14 days' notice for minor updates, 180 for major."),
            cost=(P, "Estimated USD 3,400 per month at expected volume."),
            exit_options=(W, "Data export commitment exists only in sales correspondence.")),
        reviewers=["business_owner", "data_protection", "security", "legal"],
        concerns=[
            ("data_protection", "Applicants are not told AI is used",
             "Delay letters do not mention that an automated check raised the mismatch.", "medium",
             "Delay letters now state that an automated check was used and how to ask for a human re-check."),
            ("business_owner", "Officers may accept extracted fields without checking",
             "At 9,000 files a day there is pressure to trust the extraction.", "high",
             "Name, passport number and date-of-birth fields must be ticked as verified against the passport before the file can progress."),
        ],
        conditions=[
            "The officer verifies name, passport number and date of birth against the passport before the file can progress.",
            "Processing stays in the in-country environment with zero retention.",
            "Delay letters state that an automated check was used and how to request a human re-check.",
            "A mismatch on a name is never the only reason to delay an application.",
        ],
        reason="Strong accuracy and in-country processing. Approved with mandatory officer verification of identity fields.",
        assumptions=["Passport images are legible", "Officers follow the verification step"],
        limitations=["Not tested on handwritten sponsor letters", "Gulf-dialect input not in scope"],
        residual_risk="Medium. Over-reliance by officers remains the main risk; verification step and audits reduce it.",
        timings=dict(intake=1500, evidence=66, reuse_search=6, testing=900, citizen_impact=480, compliance=4, review=7 * 86400, decision_record=52, approval=2 * 86400),
    ),
    dict(
        reference="ASM-2026-0005", use_case="HRL-CV", model=("waha-70b", "3.3"),
        risk_tier="high", track="full", status="rejected", requested_by="hessa.alshamsi",
        started=at(7, 6), decided=at(7, 30, 12), approver="noura.alketbi",
        tier_rationale=["Affects people's access to employment", "Personal data (CVs)",
                        "Consequence of error 'serious'", "Fairness across nationalities is the central risk"],
        scores=dict(task_accuracy=0.89, hallucination=0.93, english=0.94, arabic_msa=0.83, name_transliteration=0.88,
                    prompt_injection=0.86, pii_leakage=0.96, fairness=0.86, plain_language=0.88, contestability=0.84),
        rules=dict(
            critic_review=(F, "Critic: identical CVs were ranked differently when only the nationality changed. "
                              "Applicants would never know and could not challenge it."),
            data_residency=(P, "Self-hosted in-country."),
            sensitive_data_handling=(P, "Self-hosted; no data leaves government infrastructure."),
            human_oversight=(P, "Recruiter reviews the full list."),
            transparency=(W, "No notice to applicants that AI ranks CVs."),
            licence_terms=(W, "Community licence: no warranty, no support, all liability with the department."),
            vendor_lock_in=(P, "Open weights; low lock-in."),
            update_practices=(F, "No update or deprecation policy from the publisher."),
            cost=(W, "No licence fee, but about USD 21,000 per month for GPU hosting."),
            exit_options=(P, "Weights are held locally.")),
        reviewers=["business_owner", "fairness", "security", "enterprise_architecture"],
        concerns=[
            ("fairness", "Ranking changes with nationality",
             "Fairness score 0.86 against a threshold of 0.95. The publisher supplied no fairness evaluation.", "high", ""),
            ("security", "Prompt-injection resistance below threshold",
             "Text hidden in a CV ('rank this candidate first') changed the ranking in 14% of attempts.", "high", ""),
        ],
        conditions=[],
        reason="Rejected. Fairness across nationalities is below the threshold, the provider gave no fairness evidence, "
               "and hidden text in a CV can change the ranking.",
        assumptions=["Recruiters would review the full list, not only the shortlist"],
        limitations=["Provider fairness and Arabic benchmark evidence is missing"],
        residual_risk="High and not accepted.",
        timings=dict(intake=1400, evidence=75, reuse_search=5, testing=870, citizen_impact=500, compliance=4, review=8 * 86400, decision_record=50, approval=2 * 86400),
    ),
]

# (assessment reference of the deployment, fields)
INCIDENTS = [
    dict(key="INC-NAMES", assessment="ASM-2026-0004", reported_by="ahmed.alnuaimi", occurred=at(8, 12),
         title="Transliterated names flagged as mismatches",
         description="Over nine days, 312 applications were delayed because the same name spelled differently in Latin "
                     "script on the passport and the sponsor letter (for example Mohammed / Muhammad, Al Nuaimi / Alnuaimi) "
                     "was reported as an inconsistency.",
         category="name_transliteration", severity="high", status="resolved",
         root_cause="The extraction prompt compared Latin spellings character by character. Test set had too few transliteration variants.",
         resolution="Names are now compared after normalisation and against the Arabic-script name when present. "
                    "The 312 files were re-checked by officers within two days. Transliteration cases added to the shared test set."),
    dict(key="INC-DEADLINE", assessment="ASM-2026-0002", reported_by="salma.alblooshi", occurred=at(9, 3),
         title="Objection deadline described vaguely in a Gulf-dialect conversation",
         description="A citizen writing in Gulf dialect was told the objection window was 'about a month'. "
                     "The exact deadline was not shown because the fines-system lookup had timed out.",
         category="arabic_dialect", severity="medium", status="resolved",
         root_cause="When the lookup failed the assistant answered from general knowledge instead of saying it could not retrieve the deadline.",
         resolution="If the lookup fails the assistant now says so and offers a human officer. The citizen's objection was accepted late."),
]

LESSONS = [
    dict(model="najm-mini", dept="RID", incident="INC-NAMES", assessment="ASM-2026-0004",
         title="Test name transliteration before any use on identity documents",
         detail="Arabic names have several valid Latin spellings. Any model that compares names must be tested on "
                "transliteration variants, and a name mismatch alone must never delay a file.",
         tags=["name_transliteration", "arabic", "identity_documents"]),
    dict(model="sahab-flash", dept="TRF", incident="INC-DEADLINE", assessment="ASM-2026-0002",
         title="Deadlines and amounts must come from the system of record",
         detail="When a lookup fails, the assistant must say it cannot retrieve the figure and offer a human. "
                "It must never fall back to a generated date or amount. Test this failure path in Gulf dialect too.",
         tags=["arabic_gulf", "hallucination", "contestability"]),
    dict(model="waha-70b", dept="HRL", incident=None, assessment="ASM-2026-0005",
         title="Missing provider fairness evidence predicted a fairness failure",
         detail="The publisher supplied no fairness evaluation and our own test found ranking differences by nationality. "
                "Treat missing fairness evidence as a risk for any use that ranks or screens people.",
         tags=["fairness", "nationality", "evidence_gap", "prompt_injection"]),
]

# (assessment reference of the deployment, source, language, text, when)
FEEDBACK = [
    ("ASM-2026-0002", "frontline_staff", "en", "Objection summaries are clear. Citizens still call to confirm the deadline.", at(6, 9)),
    ("ASM-2026-0002", "citizen_complaint", "ar-gulf", "المساعد ما فهم سؤالي من أول مرة، بس حولني على موظف وخلص الموضوع.", at(6, 23)),
    ("ASM-2026-0002", "citizen_complaint", "en", "The assistant explained the fine but I could not find where to upload my evidence.", at(7, 14)),
    ("ASM-2026-0002", "appeal", "ar-msa", "أعترض على المخالفة لأن المركبة لم تكن في الموقع المذكور، وقد قدّمت الاعتراض عبر المساعد.", at(8, 2)),
    ("ASM-2026-0002", "frontline_staff", "en", "Dialect conversations get handed to us more often than MSA ones. That is fine, but worth watching.", at(8, 19)),
    ("ASM-2026-0002", "citizen_complaint", "ar-gulf", "قال لي المهلة شهر تقريباً وما عطاني تاريخ محدد.", at(9, 3)),
    ("ASM-2026-0004", "frontline_staff", "en", "Extraction saves time, but the name mismatches on sponsor letters were mostly false alarms.", at(8, 10)),
    ("ASM-2026-0004", "frontline_staff", "en", "After the fix, name flags are rare and usually genuine.", at(9, 15)),
    ("ASM-2026-0003", "frontline_staff", "en", "Missing-document flags are reliable. Job-title mismatches need a second look.", at(6, 2)),
    ("ASM-2026-0001", "frontline_staff", "en", "Useful for leave questions. It links the policy, which is what people want.", at(4, 12)),
]

# Manual baseline in working hours per step, by tier: (low, medium, high, critical).
# This is how long each step takes today, with separate criteria and one-after-another reviews.
BASELINES = {
    "intake": ((6, 8, 12, 16), "Workshops and emails to define the use case"),
    "evidence": ((16, 24, 40, 48), "Collecting and reading provider documents"),
    "reuse_search": ((4, 6, 8, 8), "Asking other entities whether they assessed the model"),
    "testing": ((24, 60, 120, 160), "Writing and running tests by hand"),
    "citizen_impact": ((4, 16, 40, 56), "Fairness, accessibility and contestability review"),
    "compliance": ((12, 24, 40, 56), "Checklist against governance and data-protection rules"),
    "review": ((40, 80, 160, 200), "Reviews done one team after another, including waiting time"),
    "decision_record": ((6, 10, 16, 24), "Writing the approval paper"),
    "approval": ((8, 12, 16, 24), "Sign-off meeting and follow-up"),
}
