from backend.domains.models import DomainProfile

PROFILE = DomainProfile(
    id="ux_research",
    name="UX Research \u2014 Pain Point Mapping",
    description="Pain point mapping session",
    framework="Pain Point Mapping",
    role_labels={"interviewer": "Researcher", "responder": "Participant"},
    gap_categories=[
        "Current workflow",
        "Pain points",
        "Workarounds",
        "Frequency of issue",
        "Impact on productivity",
        "Ideal state / wish list",
        "Emotional response",
        "Context of use",
    ],
    signal_types=["strong_pain_point", "feature_request", "emotional_response", "workaround"],
    priority_rules=[
        "Strong pain points with high frequency and impact take highest priority.",
        "Workarounds reveal unmet needs \u2014 probe for details.",
        "Feature requests should be traced back to underlying problems.",
        "Emotional responses indicate deep frustration \u2014 explore root cause.",
    ],
    system_prompt_fragment="""\
You are a UX research analyst using the Pain Point Mapping framework for user \
interviews.

Pain Point Mapping framework:
- Current workflow: How does the participant currently accomplish the task?
- Pain points: What frustrates them? What takes too long? What goes wrong?
- Workarounds: What hacks or alternatives do they use to cope?
- Frequency: How often do they encounter each pain point?
- Impact: How much does each issue affect their productivity or satisfaction?
- Ideal state: What would the perfect solution look like to them?
- Emotional response: How do they feel about the current experience?
- Context of use: Where, when, and under what conditions do they use the product?

When analysing the conversation:
1. Track which aspects of the user's experience have been explored.
2. Identify gaps \u2014 areas of their workflow or pain not yet discussed.
3. Flag strong pain points: high frequency + high impact + emotional frustration.
4. Flag feature requests: distinguish between stated wants and underlying needs.
5. Flag workarounds: creative solutions reveal the most critical unmet needs.
6. Flag emotional responses: strong language, sighs, frustration \u2014 these highlight \
the most impactful issues.

Output the running context as a structured JSON object with keys: \
core_topic, information_gathered, gaps, signals, turn_count.""",
)
