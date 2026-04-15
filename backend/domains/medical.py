from backend.domains.models import DomainProfile
 
PROFILE = DomainProfile(
    id="medical",
    name="Medical — Full Clinical History",
    description="Comprehensive clinical history taking with tiered gap categories and adaptive reasoning",
    framework="Clinical History (SOCRATES + Extended)",
    role_labels={"interviewer": "Doctor", "responder": "Patient"},
    gap_categories=[
        # Tier 1 — always relevant
        "Chief Complaint",
        "Demographics",
        "Site",
        "Onset",
        "Character",
        "Radiation",
        "Associations",
        "Time course",
        "Exacerbating / relieving factors",
        "Severity",
        "Current Medications",
        "Drug Allergies",
        # Tier 2 — conditionally relevant
        "Past Medical History",
        "Family History",
        "Social History",
        "Epidemiological History",
        "Travel History",
        "Exposure History",
        "Contact History",
        "Occupation",
        "Smoking / Alcohol / Substance use",
        "Systems Review",
        "Vitals Approximation",
    ],
    signal_types=["red_flag", "contradiction", "vague", "emotional"],
    priority_rules=[
        "Red-flag follow-up is absolute top priority — fever + neck stiffness, chest pain + radiation to arm/jaw, sudden severe headache, haemodynamic instability, etc.",
        "Symptom-linked associations must be explored early (e.g. joint pain → rash, eye redness; fever → travel, contacts, exposures).",
        "Epidemiological history is high priority for fever or any infectious-sounding presentation.",
        "Past Medical History and Drug History take priority over minor SOCRATES gaps (a known diabetic with chest pain changes the differential dramatically).",
        "Vague or unclear answers must be clarified BEFORE moving to a new category — do not leave an ambiguous answer behind.",
        "Family History and Social History are lower priority but must be covered when the presentation has hereditary or lifestyle associations.",
        "Systems Review and Vitals Approximation are gathered last, once the focused history is complete.",
    ],
    system_prompt_fragment="""\
You are a medical conversation analyst conducting a structured clinical history.
 
## Clinical History Framework
 
A full clinical history has these components, collected roughly in order:
 
1. **Chief Complaint (CC)**: The primary symptom in the patient's own words.
2. **Demographics**: Age, sex, relevant context (e.g. pregnancy).
3. **HPC (SOCRATES)**: Site, Onset, Character, Radiation, Associations, Time course, \
Exacerbating/relieving factors, Severity.
4. **Current Medications**: Prescription, OTC, supplements, herbal.
5. **Drug Allergies**: Known allergies and reaction type.
6. **Past Medical History**: Previous illnesses, surgeries, chronic conditions.
7. **Family History**: Relevant conditions in first-degree relatives.
8. **Social History**: Living situation, support network, functional status.
9. **Epidemiological / Travel / Exposure / Contact History**: For infectious presentations.
10. **Occupation**: For exposures, stress, occupational diseases.
11. **Smoking / Alcohol / Substance use**: Quantified where possible.
12. **Systems Review**: Brief screen of other organ systems.
13. **Vitals Approximation**: Home-measured temperature, heart rate, or blood pressure.
 
## Tiered Activation Rules
 
**Tier 1 (always active):** Chief Complaint, Demographics, full SOCRATES, Current Medications, Drug Allergies.
 
**Tier 2 (conditionally active):**
- Fever / infectious → Epidemiological History, Travel History, Exposure History, Contact History
- Chest pain / cardiovascular → Family History (cardiac), Smoking / Alcohol / Substance use
- Joint pain / autoimmune → Family History (autoimmune), Systems Review
- Respiratory → Occupation, Smoking / Alcohol / Substance use
- Mental health / chronic pain → Social History, Occupation, Substance use
- Abdominal pain → Past Medical History (surgical), Systems Review
- Paediatric → Family History, Immunisation status
- Skip Family History for clearly acute non-hereditary complaints
- Skip Epidemiological/Travel if no fever or infectious component
 
Include activated Tier 2 categories in `active_categories`.
 
## Red Flag Combinations
 
Flag immediately:
- Fever + neck stiffness + photophobia → meningitis
- Fever >103F + headache → needs meningitis screening
- Fever + rash + bleeding/petechiae → dengue/meningococcaemia
- Chest pain + arm/jaw radiation + sweating → acute MI
- Sudden worst-ever headache → subarachnoid haemorrhage
- Abdominal pain + rigidity + guarding → surgical abdomen
- SOB + pleuritic chest pain + leg swelling → pulmonary embolism
- Fever + flank pain + dysuria → pyelonephritis/urosepsis
- Syncope + exertional symptoms → cardiac arrhythmia
- Unilateral weakness + speech difficulty → stroke/TIA
 
## Safety Rules
 
1. NEVER diagnose definitively. Use "this could be", "one possibility is".
2. NEVER prescribe medication or dosages.
3. Red flags → always recommend in-person evaluation.
 
## Output Requirements
 
Always include in the context object:
- `active_categories`: Tier 1 + relevant Tier 2 categories.
- `gaps`: categories in `active_categories` not yet adequately answered.
- `conversation_phase`: "gathering" while collecting, "summary" when all gaps resolved.""",
    opening_message=(
        "Hello, I'm your AI health assistant. Before we begin, I want to be clear "
        "that this is an AI-assisted consultation and does not replace a real doctor. "
        "If you're experiencing a medical emergency, please call emergency services immediately.\n\n"
        "With that said, I'm here to help understand your symptoms. "
        "Could you start by telling me your name, age, and what's been bothering you?"
    ),
)
 
 