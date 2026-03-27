from backend.domains.models import DomainProfile

PROFILE = DomainProfile(
    id="hr",
    name="HR \u2014 Behavioural Competency (STAR)",
    description="Behavioural competency interview",
    framework="STAR",
    role_labels={"interviewer": "Interviewer", "responder": "Candidate"},
    gap_categories=[
        "Situation",
        "Task",
        "Action",
        "Result",
        "Leadership examples",
        "Conflict resolution",
        "Technical depth",
        "Cultural fit indicators",
    ],
    signal_types=["vague_answer", "red_flag", "strong_indicator", "inconsistency"],
    priority_rules=[
        "Incomplete STAR responses take highest priority \u2014 probe for missing components.",
        "Vague or generic answers need depth \u2014 ask for specific examples.",
        "Red flags (gaps in employment, evasive answers) require follow-up.",
        "Cultural fit and soft-skill probing come last.",
    ],
    system_prompt_fragment="""\
You are an HR interview analyst using the STAR (Situation, Task, Action, Result) \
framework for behavioural competency interviews.

STAR framework:
- Situation: The context or background of the example.
- Task: The specific challenge or responsibility the candidate faced.
- Action: What the candidate personally did (not the team).
- Result: The measurable outcome or impact.

When analysing the conversation:
1. Track which STAR components have been covered for each behavioural question.
2. Identify incomplete responses \u2014 e.g. a candidate describes a situation but skips \
the result.
3. Flag vague answers: "I helped the team" without specifics on personal contribution.
4. Flag red flags: unexplained employment gaps, blame-shifting, inability to provide \
concrete examples.
5. Flag strong indicators: quantified results, ownership language, growth mindset.
6. Track coverage across competency areas: leadership, conflict resolution, technical \
skill, collaboration.

Output the running context as a structured JSON object with keys: \
core_topic, information_gathered, gaps, signals, turn_count.""",
)
