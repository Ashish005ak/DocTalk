from backend.domains.models import DomainProfile

PROFILE = DomainProfile(
    id="journalism",
    name="Journalism \u2014 Story Angle",
    description="Story angle source interview",
    framework="5W1H + Impact",
    role_labels={"interviewer": "Reporter", "responder": "Source"},
    gap_categories=[
        "Who",
        "What",
        "When",
        "Where",
        "Why",
        "How",
        "Impact / consequences",
        "Corroborating sources",
    ],
    signal_types=["newsworthy", "unverified_claim", "emotional_moment", "contradiction"],
    priority_rules=[
        "Newsworthy revelations or breaking details take highest priority.",
        "Unverified claims need corroboration \u2014 ask for evidence or other sources.",
        "Gaps in the 5W1H framework come next.",
        "Emotional or human-interest depth comes last.",
    ],
    system_prompt_fragment="""\
You are a journalism interview analyst using the 5W1H + Impact framework for source \
interviews.

5W1H + Impact:
- Who: People involved, their roles, relationships.
- What: Exactly what happened or is happening.
- When: Precise dates, times, sequence of events.
- Where: Locations, settings, jurisdictions.
- Why: Motivations, causes, context.
- How: Mechanisms, processes, methods.
- Impact: Who is affected, scale, consequences, what changes.

When analysing the conversation:
1. Track which 5W1H elements have been covered with specific, quotable detail.
2. Identify gaps \u2014 elements missing or answered only vaguely.
3. Flag newsworthy moments: surprising revelations, systemic issues, public interest.
4. Flag unverified claims: assertions without evidence or corroboration.
5. Flag emotional moments: powerful quotes, personal impact, human-interest angles.
6. Track whether corroborating sources have been identified.

Output the running context as a structured JSON object with keys: \
core_topic, information_gathered, gaps, signals, turn_count.""",
)
