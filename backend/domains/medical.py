from backend.domains.models import DomainProfile

PROFILE = DomainProfile(
    id="medical",
    name="Medical \u2014 SOCRATES",
    description="SOCRATES symptom history taking",
    framework="SOCRATES",
    role_labels={"interviewer": "Doctor", "responder": "Patient"},
    gap_categories=[
        "Site",
        "Onset",
        "Character",
        "Radiation",
        "Associations",
        "Time course",
        "Exacerbating / relieving factors",
        "Severity",
    ],
    signal_types=["red_flag", "contradiction", "vague", "emotional"],
    priority_rules=[
        "Red-flag follow-up takes highest priority (e.g. exertional symptoms, sudden onset).",
        "Uncovered SOCRATES categories are next \u2014 ask about the largest remaining gap.",
        "Depth questions on already-covered areas come last (clarify ambiguous answers).",
    ],
    system_prompt_fragment="""\
You are a medical conversation analyst using the SOCRATES framework for symptom \
history taking.

SOCRATES stands for:
- Site: Where exactly is the symptom?
- Onset: When did it start? Was it sudden or gradual?
- Character: What does it feel like (sharp, dull, burning, etc.)?
- Radiation: Does it spread anywhere?
- Associations: Any other symptoms occurring alongside?
- Time course: Is it constant or intermittent? Getting better or worse?
- Exacerbating / relieving factors: What makes it better or worse?
- Severity: How bad is it on a scale of 1\u201310?

When analysing the conversation:
1. Track which SOCRATES categories have been adequately covered by the patient's \
answers.
2. Identify gaps \u2014 categories not yet addressed or answered vaguely.
3. Flag red-flag signals: exertional symptoms, sudden severe onset, radiation to arm/\
jaw/back, associated syncope, haemodynamic instability, or any feature suggesting a \
life-threatening condition.
4. Flag contradictions where the patient gives conflicting information.
5. Flag vague answers that need clarification ("it hurts sometimes" without specifics).

Output the running context as a structured JSON object with keys: \
core_topic, information_gathered, gaps, signals, turn_count.""",
    opening_message="Hello, I'm your doctor today. What brings you in?",
)
