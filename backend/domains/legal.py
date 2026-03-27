from backend.domains.models import DomainProfile

PROFILE = DomainProfile(
    id="legal",
    name="Legal \u2014 Evidence Chain",
    description="Evidence chain client intake",
    framework="Evidence Chain",
    role_labels={"interviewer": "Attorney", "responder": "Client"},
    gap_categories=[
        "Incident details",
        "Timeline / chronology",
        "Witnesses",
        "Damages (physical, financial, emotional)",
        "Prior incidents / history",
        "Insurance / coverage",
        "Documentation / evidence available",
        "Opposing party details",
    ],
    signal_types=["inconsistency", "missing_evidence", "liability_indicator", "emotional"],
    priority_rules=[
        "Evidence gaps that weaken the case take highest priority.",
        "Timeline inconsistencies or missing chronology come next.",
        "Witness identification and contact details follow.",
        "Depth on damages and emotional impact come last.",
    ],
    system_prompt_fragment="""\
You are a legal conversation analyst specialising in client intake for civil claims.

Your role is to track the evidence chain being built through the interview:
1. Incident details: What happened, where, when, how.
2. Timeline: Exact chronology of events leading up to, during, and after the incident.
3. Witnesses: Who was present, contact information, relationship to parties.
4. Damages: Physical injuries, medical treatment, financial losses, emotional distress.
5. Prior incidents: Any relevant history that affects the claim.
6. Insurance: Existing coverage, other party's insurance, policy details.
7. Documentation: Photos, police reports, medical records, correspondence.
8. Opposing party: Identity, contact info, known insurance.

When analysing the conversation:
1. Track which evidence categories have supporting facts from the client's answers.
2. Identify gaps \u2014 critical evidence areas not yet explored.
3. Flag inconsistencies where the client's statements conflict with each other or \
with common sense.
4. Flag missing evidence \u2014 claims made without supporting documentation.
5. Flag liability indicators \u2014 statements that strengthen or weaken the case.

Output the running context as a structured JSON object with keys: \
core_topic, information_gathered, gaps, signals, turn_count.""",
)
