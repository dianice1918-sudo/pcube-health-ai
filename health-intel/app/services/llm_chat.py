import json
import os
import base64
import time
import requests
import urllib.error
import urllib.request
from typing import Any, Iterator

from app.env import load_app_env

load_app_env()

PINECONE_SUPPORTED_UPLOADS = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".json": "application/json",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
} 

LLM_REQUEST_TIMEOUT_SECONDS = max(
    5,
    min(60, int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "30"))),
)


def _no_proxy_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _build_system_prompt(assistant: str = "general") -> str:
    if assistant == "medication":
        return (
            "You are PCUBE Medication Assistant. Provide educational, safety-first medication guidance for common symptoms. "
            "Use plain language and be conservative. Never claim to diagnose, never present yourself as a prescriber, "
            "and never replace a clinician or pharmacist. Always consider allergies, current medications, age context, "
            "and the possibility that urgent care may be safer than self-treatment. "
            "Prefer supportive care and common non-prescription options when appropriate. "
            "Do not keep defaulting to only acetaminophen or ibuprofen. Match suggestions to the symptom pattern when it is reasonable to do so. "
            "When appropriate, consider categories such as antihistamines, saline nasal spray, throat lozenges, cough suppressants, expectorants, antacids, oral rehydration support, or reflux medicines. "
            "If you mention pain relievers, explain when acetaminophen may be preferred and when ibuprofen may be unsuitable because of stomach, kidney, bleeding, pregnancy, or blood-pressure concerns. "
            "If you mention medication ideas, keep them general, note that label directions and local clinician advice take priority, "
            "and warn the user to confirm suitability in pregnancy, kidney disease, liver disease, ulcers, bleeding risk, and blood-pressure concerns. "
            "Format the answer with these headings exactly on their own lines: "
            "Overview, Supportive Care, Possible Medication Options, Interaction and Avoidance Notes, Follow-up and Escalation, Safety Note."
        )
    if assistant == "nutrition":
        return (
            "You are PCUBE Nutrition Assistant. Provide educational, practical nutrition guidance based on the user's goals, symptoms, "
            "preferences, allergies, and recent health context. Keep the tone supportive and concrete. "
            "Do not diagnose disease and do not promise medical outcomes. "
            "Prefer balanced meal ideas, hydration support, pantry-friendly options, and recipe starters that are easy to follow. "
            "Mention when symptoms, allergies, glucose concerns, kidney disease, pregnancy, or severe illness should change the plan or require clinician review. "
            "Format the answer with these headings exactly on their own lines: "
            "Overview, Meal Priorities, Suggested Meals, Recipe Ideas, Watch-outs, Safety Note."
        )
    return (
        "You are PCUBE Health Assistant. Explain health information clearly in simple language. "
        "Use user-provided metrics and context. Be practical and concise. "
        "Never claim to diagnose disease. Encourage medical consultation for severe symptoms."
    )


def _build_health_context(context: dict[str, Any]) -> str:
    return (
        "User context:\n"
        f"- Risk score: {context.get('risk_score')}\n"
        f"- Risk level: {context.get('risk_level')}\n"
        f"- Trend: {context.get('trend')}\n"
        f"- Latest systolic BP: {context.get('systolic_bp')}\n"
        f"- Latest diastolic BP: {context.get('diastolic_bp')}\n"
        f"- Latest BMI: {context.get('bmi')}\n"
        f"- Latest blood glucose: {context.get('blood_glucose')}\n"
        f"- Latest cholesterol: {context.get('cholesterol')}\n"
        f"- Activity level: {context.get('activity_level')}\n"
        f"- Steps count: {context.get('steps_count')}\n"
        f"- Activity minutes: {context.get('activity_minutes')}\n"
        f"- Hydration liters: {context.get('hydration_liters')}\n"
        f"- Weather condition: {context.get('weather_condition')}\n"
        f"- Temperature C: {context.get('temperature_c')}\n"
        f"- UV index: {context.get('uv_index')}\n"
        f"- AQI: {context.get('aqi')}\n"
        f"- Regional context enabled: {context.get('location_label')}\n"
    )


def _unique_lines(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        clean = " ".join(str(item or "").split()).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        ordered.append(clean)
    return ordered


def _looks_like_greeting(lowered: str) -> bool:
    clean = " ".join(lowered.split()).strip(".,!? ")
    if not clean:
        return False
    greetings = {
        "hello",
        "hi",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
    }
    return clean in greetings


def _fallback_symptom_guidance(question_text: str) -> tuple[list[str], list[str], list[str]]:
    lowered = question_text.lower()
    matched_possible: list[str] = []
    matched_steps: list[str] = []
    matched_urgent: list[str] = []

    rules = (
        {
            "keywords": ("headache", "migraine"),
            "possible": "Headache can happen with dehydration, lack of sleep, stress, viral illness, or migraine-like symptoms.",
            "steps": (
                "Drink water, rest in a quiet room, and note whether light, noise, or screen time makes it worse.",
                "Check your temperature if you feel feverish and avoid skipping meals.",
            ),
            "urgent": "Get urgent care now if the headache is sudden and severe, follows a head injury, or comes with confusion, weakness, stiff neck, or vision loss.",
        },
        {
            "keywords": ("fever", "temperature", "chills"),
            "possible": "Fever or chills often happen with viral infections, flu-like illness, or another infection.",
            "steps": (
                "Rest, drink fluids regularly, and re-check your temperature every few hours if you can.",
                "If you are not eating well, focus on fluids and light meals to reduce dehydration risk.",
            ),
            "urgent": "Seek prompt medical care if fever stays high, lasts more than about 3 days, or is paired with confusion, stiff neck, dehydration, or trouble breathing.",
        },
        {
            "keywords": ("cough", "sore throat", "runny nose", "congestion"),
            "possible": "Cough, sore throat, and congestion often fit a viral upper respiratory infection, allergy flare, or airway irritation.",
            "steps": (
                "Hydrate well, rest, and monitor whether symptoms are getting better or worsening over the next 24-48 hours.",
                "Watch for fever, wheezing, or chest tightness because those change the urgency.",
            ),
            "urgent": "Get urgent care if you have trouble breathing, blue lips, chest pain, or cannot keep fluids down.",
        },
        {
            "keywords": ("stomach pain", "abdominal pain", "nausea", "vomiting", "diarrhea"),
            "possible": "Stomach symptoms can happen with food irritation, viral gastroenteritis, reflux, food poisoning, or medication side effects.",
            "steps": (
                "Take small sips of water or oral rehydration fluids and use bland foods if you can tolerate them.",
                "Track vomiting, diarrhea frequency, blood in stool, and whether the pain is getting sharper or more localized.",
            ),
            "urgent": "Get urgent care if pain becomes severe, settles in one area, you vomit repeatedly, you see blood, or you cannot keep fluids down.",
        },
        {
            "keywords": ("dizzy", "dizziness", "weak", "weakness", "fatigue"),
            "possible": "Dizziness, weakness, or fatigue can come from dehydration, low food intake, infection, anemia, or low blood pressure.",
            "steps": (
                "Sit or lie down, sip fluids, and avoid driving or climbing until the feeling passes.",
                "If you have a blood pressure or glucose reading, check it because that can help narrow the cause.",
            ),
            "urgent": "Seek urgent care if you faint, have one-sided weakness, chest pain, trouble breathing, or severe worsening symptoms.",
        },
        {
            "keywords": ("chest pain", "chest discomfort", "shortness of breath", "trouble breathing"),
            "possible": "Chest discomfort or shortness of breath can range from anxiety or muscle strain to heart or lung problems.",
            "steps": (
                "Stop exertion immediately and note whether the symptoms happen at rest, with walking, or with deep breathing.",
            ),
            "urgent": "Because chest symptoms can be serious, seek emergency care now if the pain is severe, spreading, or paired with sweating, fainting, or breathing difficulty.",
        },
    )

    for rule in rules:
        if any(keyword in lowered for keyword in rule["keywords"]):
            matched_possible.append(rule["possible"])
            matched_steps.extend(rule["steps"])
            matched_urgent.append(rule["urgent"])

    if not matched_possible and question_text:
        matched_steps.append(
            "Share the main symptom, when it started, any fever reading, your age if relevant, and what makes it better or worse."
        )
        matched_steps.append(
            "List any medicines already taken and whether symptoms are improving, stable, or getting worse."
        )

    return (
        _unique_lines(matched_possible),
        _unique_lines(matched_steps),
        _unique_lines(matched_urgent),
    )


def pinecone_supported_file_extensions() -> list[str]:
    return sorted(PINECONE_SUPPORTED_UPLOADS.keys())


def _pinecone_config() -> tuple[str, str, str, str, str]:
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY is missing. Configure it in environment variables.")

    assistant_name = os.getenv("PINECONE_ASSISTANT_NAME", "").strip()
    if not assistant_name:
        raise RuntimeError(
            "PINECONE_ASSISTANT_NAME is missing. Set it to the name of your Pinecone assistant."
        )

    api_version = os.getenv("PINECONE_API_VERSION", "2025-10").strip() or "2025-10"

    chat_base = os.getenv(
        "PINECONE_API_BASE",
        "https://prod-1-data.ke.pinecone.io/assistant/chat/{assistant_name}/chat/completions",
    ).strip()
    if "{assistant_name}" in chat_base:
        chat_endpoint = chat_base.format(assistant_name=assistant_name)
    else:
        chat_endpoint = f"{chat_base.rstrip('/')}/{assistant_name}/chat/completions"

    files_base = os.getenv(
        "PINECONE_FILES_API_BASE",
        "https://prod-1-data.ke.pinecone.io/assistant/files/{assistant_name}",
    ).strip()
    if "{assistant_name}" in files_base:
        files_endpoint = files_base.format(assistant_name=assistant_name)
    else:
        files_endpoint = f"{files_base.rstrip('/')}/{assistant_name}"

    return api_key, assistant_name, api_version, chat_endpoint, files_endpoint


def _validate_pinecone_upload_name(file_name: str) -> tuple[str, str]:
    name = os.path.basename(str(file_name or "")).strip()
    if not name:
        raise RuntimeError("A file name is required.")
    _, ext = os.path.splitext(name)
    ext = ext.lower()
    content_type = PINECONE_SUPPORTED_UPLOADS.get(ext)
    if not content_type:
        supported = ", ".join(pinecone_supported_file_extensions())
        raise RuntimeError(f"Unsupported file type. Use one of: {supported}.")
    return name, content_type


def list_pinecone_assistant_files() -> list[dict[str, Any]]:
    api_key, _assistant_name, api_version, _chat_endpoint, files_endpoint = _pinecone_config()
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.get(
            files_endpoint,
            headers={
                "Api-Key": api_key,
                "X-Pinecone-Api-Version": api_version,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Pinecone file request failed: {exc}") from exc

    if not response.ok:
        detail = response.text.strip()
        raise RuntimeError(f"Pinecone file request failed: HTTP {response.status_code} {detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("Pinecone file response was not valid JSON.") from exc
    files = data.get("files")
    if not isinstance(files, list):
        return []
    return [item for item in files if isinstance(item, dict)]


def upload_pinecone_assistant_file(
    *,
    file_name: str,
    file_bytes: bytes,
    content_type: str | None = None,
) -> dict[str, Any]:
    api_key, _assistant_name, api_version, _chat_endpoint, files_endpoint = _pinecone_config()
    safe_name, default_type = _validate_pinecone_upload_name(file_name)
    if not file_bytes:
        raise RuntimeError("Uploaded file is empty.")

    files = {
        "file": (
            safe_name,
            file_bytes,
            str(content_type or default_type or "application/octet-stream"),
        )
    }
    data = {}
    if safe_name.lower().endswith(".pdf"):
        data["multimodal"] = "true"

    try:
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            files_endpoint,
            headers={
                "Api-Key": api_key,
                "X-Pinecone-Api-Version": api_version,
            },
            files=files,
            data=data,
            timeout=120,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Pinecone upload failed: {exc}") from exc

    if not response.ok:
        detail = response.text.strip()
        raise RuntimeError(f"Pinecone upload failed: HTTP {response.status_code} {detail}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Pinecone upload response was not valid JSON.") from exc
    item = payload.get("file") if isinstance(payload.get("file"), dict) else payload
    if not isinstance(item, dict):
        raise RuntimeError("Pinecone upload response did not include file details.")
    return item


def build_fallback_chat_answer(
    *,
    question: str,
    context: dict[str, Any],
    image_mode: bool = False,
    failure_reason: str | None = None,
) -> str:
    question_text = " ".join(str(question or "").split())
    lowered = question_text.lower()

    risk_score = context.get("risk_score")
    risk_level = str(context.get("risk_level") or "UNKNOWN").upper()
    trend = str(context.get("trend") or "UNKNOWN").upper()
    activity_level = context.get("activity_level")
    steps_count = context.get("steps_count")
    hydration = context.get("hydration_liters")
    possible_matches, self_care_steps, urgent_watchouts = _fallback_symptom_guidance(question_text)

    emergency_terms = (
        "chest pain",
        "trouble breathing",
        "shortness of breath",
        "fainted",
        "seizure",
        "stroke",
        "bleeding",
        "suicidal",
    )
    has_emergency_signal = any(term in lowered for term in emergency_terms)

    lines: list[str] = []
    if _looks_like_greeting(lowered) and not possible_matches:
        lines.extend(
            [
                "Hello. I can still help with general health guidance right now.",
                "Tell me your main symptoms, when they started, any fever reading, and what makes them better or worse.",
                "I can also help you decide what details matter most to monitor before you seek care.",
                "This information is educational and not a medical diagnosis.",
            ]
        )
        return "\n".join(lines)

    lines.append("I am using local health guidance right now, but I can still help with general next steps.")
    if question_text:
        lines.append(f'Question noted: "{question_text[:220]}"')

    if possible_matches:
        lines.append("What this pattern can sometimes fit:")
        for item in possible_matches[:3]:
            lines.append(f"- {item}")

    if self_care_steps:
        lines.append("What to do now:")
        for item in self_care_steps[:4]:
            lines.append(f"- {item}")

    if has_emergency_signal:
        lines.append("Urgent warning:")
        lines.append(
            "- Severe chest pain, breathing difficulty, heavy bleeding, one-sided weakness, confusion, or seizure symptoms need emergency care now."
        )
    elif urgent_watchouts:
        lines.append("Get urgent care now if:")
        for item in urgent_watchouts[:2]:
            lines.append(f"- {item}")
    else:
        lines.append("Safety check:")
        lines.append("- Seek in-person care promptly if symptoms are severe, clearly worsening, or not improving.")

    if risk_score is not None:
        lines.append(
            f"Latest health snapshot: score {risk_score}, level {risk_level}, trend {trend}."
        )
    else:
        lines.append(f"Latest health snapshot: level {risk_level}, trend {trend}.")

    if activity_level or steps_count is not None or hydration is not None:
        lines.append(
            f"Lifestyle notes: activity={activity_level or 'unknown'}, steps={steps_count if steps_count is not None else 'unknown'}, hydration_liters={hydration if hydration is not None else 'unknown'}."
        )

    if image_mode:
        lines.append(
            "Image analysis is unavailable in local guidance mode, so I am responding only to the text you provided."
        )

    if failure_reason:
        reason = failure_reason.lower()
        if "insufficient_quota" in reason or "http 429" in reason:
            lines.append("Live AI responses are temporarily unavailable, so this answer is based on local safety guidance.")
        elif "no files found" in reason:
            lines.append(
                "The Pinecone assistant is connected but does not have any uploaded files yet, so I am using local safety guidance for now."
            )

    lines.append("This information is educational and not a medical diagnosis.")
    return "\n".join(lines)


def build_fallback_medication_answer(
    *,
    primary_complaint: str,
    age_range: str | None = None,
    risk_level: str | None = None,
    allergies: str | None = None,
    current_medications: str | None = None,
    additional_notes: str | None = None,
) -> str:
    complaint = " ".join(str(primary_complaint or "").split())
    lowered = complaint.lower()
    notes = " ".join(str(additional_notes or "").split()).lower()
    overview: list[str] = []
    supportive: list[str] = []
    options: list[str] = []
    avoid: list[str] = []
    follow_up: list[str] = []
    safety: list[str] = []

    if any(term in lowered for term in ("headache", "fever", "body ache", "body pain", "migraine")):
        overview.append("This sounds like a short-term symptom pattern where supportive care and non-prescription relief may be considered if it is otherwise safe for you.")
        supportive.extend(
            [
                "Rest, drink fluids regularly, and avoid skipping meals.",
                "Track fever, worsening pain, or symptoms that are not improving after 24 to 48 hours.",
            ]
        )
        options.extend(
            [
                "Acetaminophen may be considered for pain or fever if you are not allergic and do not have liver-related restrictions. Follow the package label.",
                "Ibuprofen may be considered for pain or migraine-type discomfort in some adults, but avoid it if you have stomach ulcer risk, kidney disease, bleeding risk, certain blood-pressure concerns, or pregnancy-related restrictions unless a clinician says it is safe.",
                "If the problem seems migraine-like, reducing light, noise, and screen time can matter as much as medicine.",
                "For migraine-type symptoms, some people also ask a pharmacist about caffeine-containing headache products, but those are not ideal for everyone and may worsen palpitations, anxiety, or blood-pressure issues.",
            ]
        )
        avoid.append("Avoid combining multiple pain relievers unless a clinician or pharmacist has confirmed that it is safe.")
        follow_up.append("Seek same-day care if the headache is unusually severe, comes with stiff neck, confusion, weakness, chest pain, or repeated vomiting.")
    elif any(term in lowered for term in ("cough", "sore throat", "runny nose", "congestion", "cold")):
        overview.append("This sounds closer to a cough, throat, or congestion pattern where supportive care is usually the first step.")
        supportive.extend(
            [
                "Hydrate well, rest, and use warm fluids or steam if they help.",
                "Honey can soothe throat irritation for adults who can safely take it.",
            ]
        )
        options.extend(
            [
                "Saline nasal spray or rinse may help congestion without major medication interaction concerns.",
                "Simple throat lozenges may help throat discomfort if they are safe for you to use.",
                "If sneezing or a runny nose is a big part of the problem, a pharmacist may suggest a non-drowsy antihistamine such as cetirizine or loratadine when appropriate.",
                "If mucus is thick and chesty, an expectorant such as guaifenesin may be considered if it is suitable for you.",
                "If the cough is dry and irritating, some adults ask about dextromethorphan-based cough products, but it should be checked against your current medicines.",
            ]
        )
        avoid.append("Use extra caution with decongestants if you have high blood pressure, heart concerns, or stimulant sensitivity.")
        follow_up.append("Get urgent evaluation if breathing becomes difficult, chest pain develops, or you cannot keep fluids down.")
    elif any(term in lowered for term in ("stomach", "abdominal", "nausea", "vomiting", "diarrhea", "reflux")):
        overview.append("This sounds like a stomach or digestive complaint where hydration and gentler symptom support matter first.")
        supportive.extend(
            [
                "Use small sips of water or oral rehydration fluids and stick to bland foods if tolerated.",
                "Pay attention to worsening pain location, blood, black stool, or ongoing dehydration signs.",
            ]
        )
        options.extend(
            [
                "For reflux or heartburn-type symptoms, a simple antacid may help some people, while others ask about acid-reducing options such as omeprazole when symptoms are recurring and a clinician or pharmacist agrees it fits.",
                "For diarrhea without red-flag symptoms, oral rehydration support is often more important than medicine at first.",
                "Some people ask about loperamide for diarrhea, but it should be avoided if there is blood in stool, high fever, or significant abdominal pain.",
                "For nausea or diarrhea, avoid self-treating aggressively until you are sure there is no fever, blood, or severe abdominal pain.",
            ]
        )
        avoid.extend(
            [
                "Avoid NSAID pain relievers if stomach irritation, ulcer history, or bleeding risk is a concern.",
                "Do not rely on anti-diarrheal medication if you have blood in stool, high fever, or worsening abdominal pain without medical advice.",
            ]
        )
        follow_up.append("Seek urgent care if pain is severe, focused in one area, you are vomiting repeatedly, or you cannot keep fluids down.")
    else:
        overview.append("I can only give broad medication guidance from the details provided, so the safest plan is to start with supportive care and confirm the exact symptom pattern before taking medicine.")
        supportive.extend(
            [
                "Rest, hydrate, and write down the exact symptom, start time, severity, and what makes it better or worse.",
                "Confirm your allergies, pregnancy status if relevant, and the names of all medicines or supplements you already use.",
            ]
        )
        options.append("Before starting a new medicine, confirm the exact symptom type with a clinician or pharmacist so the choice is matched to the problem.")
        follow_up.append("Get in-person care promptly if symptoms are severe, clearly worsening, or not improving.")

    if allergies and str(allergies).strip():
        avoid.append(f"Avoid anything containing or related to: {' '.join(str(allergies).split())}.")
    if current_medications and str(current_medications).strip():
        avoid.append(
            f"Ask a pharmacist or clinician to review interaction risk with your current medicines: {' '.join(str(current_medications).split())}."
        )
    if age_range and str(age_range).strip() == "60+":
        avoid.append("Older adults can have more side effects from sedating medicines, some antihistamines, and dehydration-related medicines, so confirm before using them.")
    if risk_level and str(risk_level).strip().lower() == "high":
        follow_up.insert(0, "Because the reported risk level is high, a clinician or pharmacist should review any medication choice before you rely on it.")
    if "pregnan" in notes:
        avoid.append("Pregnancy can change which medicines are safe, so confirm every option with a clinician or pharmacist before using it.")

    safety.extend(
        [
            "This is educational guidance only and not a prescription.",
            "Use the product label, local pharmacy advice, and clinician instructions as the final authority before starting or combining medicines.",
        ]
    )

    sections = [
        ("Overview", overview),
        ("Supportive Care", supportive),
        ("Possible Medication Options", options),
        ("Interaction and Avoidance Notes", avoid),
        ("Follow-up and Escalation", follow_up),
        ("Safety Note", safety),
    ]
    lines: list[str] = []
    for heading, items in sections:
        lines.append(heading)
        if items:
            for item in _unique_lines(items):
                lines.append(f"- {item}")
        else:
            lines.append("- No additional notes.")
    return "\n".join(lines)


def build_fallback_nutrition_answer(
    *,
    goal: str,
    symptom_focus: str | None = None,
    dietary_preferences: str | None = None,
    allergies: str | None = None,
    budget_level: str | None = None,
    cooking_time: str | None = None,
    additional_notes: str | None = None,
) -> str:
    goal_text = " ".join(str(goal or "").split())
    symptom_text = " ".join(str(symptom_focus or "").split())
    pref_text = " ".join(str(dietary_preferences or "").split())
    allergy_text = " ".join(str(allergies or "").split())
    notes_text = " ".join(str(additional_notes or "").split()).lower()
    lowered = f"{goal_text} {symptom_text} {pref_text}".lower()

    overview: list[str] = []
    priorities: list[str] = []
    meals: list[str] = []
    recipes: list[str] = []
    watchouts: list[str] = []
    safety: list[str] = []

    if "weight" in lowered or "fat loss" in lowered or "lose" in lowered:
        overview.append("This plan leans toward steady, portion-aware meals that keep protein and fiber strong without making the day feel overly restrictive.")
        priorities.extend(
            [
                "Build most meals around vegetables or fruit, a lean protein, and a moderate starch portion.",
                "Keep drinks mostly water and avoid frequent liquid calories if weight balance is the goal.",
            ]
        )
        meals.extend(
            [
                "Greek yogurt or oats with fruit for breakfast.",
                "Beans, grilled chicken, fish, or eggs with vegetables for lunch or dinner.",
                "A simple snack such as fruit with nuts or yogurt if needed.",
            ]
        )
        recipes.extend(
            [
                "Try an oats bowl with yogurt, chia seeds, and sliced fruit.",
                "Try a sheet-pan meal with fish or chicken, mixed vegetables, and a small rice or potato portion.",
            ]
        )
    elif "energy" in lowered or "fatigue" in lowered:
        overview.append("This plan focuses on steady energy by avoiding long fasting gaps and pairing carbohydrates with protein or healthy fat.")
        priorities.extend(
            [
                "Eat at regular intervals instead of waiting until you are exhausted or shaky.",
                "Pair carbohydrates with protein to reduce energy crashes later in the day.",
            ]
        )
        meals.extend(
            [
                "Eggs with toast and fruit, or oatmeal with nuts and yogurt.",
                "Rice, beans, fish, tofu, or chicken with vegetables for a balanced midday meal.",
                "Carry a simple snack like roasted nuts, yogurt, or fruit.",
            ]
        )
        recipes.extend(
            [
                "Prepare overnight oats with milk or yogurt, oats, fruit, and nuts.",
                "Cook a quick vegetable-and-egg stir fry served with rice or sweet potato.",
            ]
        )
    elif any(term in lowered for term in ("stomach", "nausea", "vomiting", "diarrhea", "reflux")):
        overview.append("This plan leans toward gentler foods and hydration support until the stomach feels calmer.")
        priorities.extend(
            [
                "Use small, frequent meals instead of heavy portions.",
                "Choose bland or simpler foods first and reintroduce richer foods slowly.",
            ]
        )
        meals.extend(
            [
                "Bananas, rice, toast, crackers, oatmeal, applesauce, or simple soup can be easier to tolerate.",
                "Use oral rehydration fluids or water in small frequent sips if intake is low.",
            ]
        )
        recipes.extend(
            [
                "Try a light broth soup with rice and a small amount of chicken or beans.",
                "Try soft oatmeal with banana if solid foods are tolerated.",
            ]
        )
        watchouts.extend(
            [
                "Avoid very greasy, spicy, or heavy meals while symptoms are active.",
                "Avoid dehydration by drinking small amounts regularly even if appetite is poor.",
            ]
        )
    else:
        overview.append("This plan uses a balanced meal template that can be adjusted once your goals or symptoms become more specific.")
        priorities.extend(
            [
                "Aim for a protein source, a high-fiber plant food, and water with most meals.",
                "Keep meal timing steady so hunger swings do not drive over-snacking later.",
            ]
        )
        meals.extend(
            [
                "Oats, yogurt, fruit, eggs, beans, fish, chicken, lentils, vegetables, and simple grains are solid starting points.",
            ]
        )
        recipes.extend(
            [
                "Try a rice bowl with beans or chicken, vegetables, and a light sauce.",
                "Try a yogurt-and-fruit bowl or oats with nuts for a quick breakfast.",
            ]
        )

    if pref_text:
        priorities.append(f"Keep these preferences in the rotation where possible: {pref_text}.")
    if allergy_text:
        watchouts.append(f"Strictly avoid foods related to: {allergy_text}.")
    if budget_level and str(budget_level).strip():
        level = str(budget_level).strip().lower()
        if level == "budget":
            recipes.append("Budget-friendly staples include oats, beans, eggs, rice, bananas, frozen vegetables, and canned fish if tolerated.")
        elif level == "flexible":
            recipes.append("You have room to mix staples with fresher proteins, yogurt, fruit, and pre-cut vegetables if convenience matters.")
    if cooking_time and str(cooking_time).strip():
        time_text = str(cooking_time).strip().lower()
        if "15" in time_text or "quick" in time_text:
            priorities.append("Favor quick assembly meals, leftovers, and one-pan recipes that can be finished in about 15 minutes.")
    if "pregnan" in notes_text:
        watchouts.append("Pregnancy changes nutrition and food-safety priorities, so confirm meal restrictions and supplement needs with a clinician.")
    if "kidney" in notes_text:
        watchouts.append("Kidney conditions can change protein, sodium, and potassium targets, so a clinician or dietitian should review the plan.")
    if "diabet" in notes_text or "glucose" in notes_text:
        watchouts.append("If blood sugar management is a concern, keep meal portions and carbohydrate timing consistent and review this plan with your clinician.")

    safety.extend(
        [
            "This is educational nutrition guidance only and not a medical treatment plan.",
            "Seek clinical review for severe symptoms, dehydration, ongoing vomiting, inability to eat, or major dietary restrictions related to chronic disease.",
        ]
    )

    sections = [
        ("Overview", overview),
        ("Meal Priorities", priorities),
        ("Suggested Meals", meals),
        ("Recipe Ideas", recipes),
        ("Watch-outs", watchouts),
        ("Safety Note", safety),
    ]
    lines: list[str] = []
    for heading, items in sections:
        lines.append(heading)
        if items:
            for item in _unique_lines(items):
                lines.append(f"- {item}")
        else:
            lines.append("- No additional notes.")
    return "\n".join(lines)


def _base_messages(
    context: dict[str, Any],
    history: list[dict[str, str]],
    *,
    assistant: str = "general",
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt(assistant)},
        {"role": "system", "content": _build_health_context(context)},
    ]
    for item in history[-8:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


def _openai_messages(
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    image_bytes: bytes | None,
    image_mime_type: str | None,
    assistant: str,
) -> list[dict[str, Any]]:
    messages = _base_messages(context, history, assistant=assistant)
    if image_bytes and image_mime_type:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{image_mime_type};base64,{b64}"
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": question})
    return messages


def _ollama_messages(
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    image_bytes: bytes | None,
    assistant: str,
) -> list[dict[str, Any]]:
    messages = _base_messages(context, history, assistant=assistant)
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages.append({"role": "user", "content": question, "images": [b64]})
    else:
        messages.append({"role": "user", "content": question})
    return messages


def _pinecone_messages(
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    assistant: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                "Use the following assistant guidance and health context when answering.\n\n"
                f"{_build_system_prompt(assistant)}\n\n"
                f"{_build_health_context(context)}"
            ),
        }
    ]
    for item in history[-8:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    opener = _no_proxy_opener()
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    timeout = timeout_seconds or LLM_REQUEST_TIMEOUT_SECONDS
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LLM request failed: HTTP {e.code} {detail}")
        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
    raise RuntimeError(f"LLM request failed: {last_error}")


def _chunk_text_for_stream(text: str, chunk_size: int = 36) -> Iterator[str]:
    words = str(text or "").split()
    if not words:
        return
    chunk: list[str] = []
    current_len = 0
    for word in words:
        projected = current_len + len(word) + (1 if chunk else 0)
        if chunk and projected > chunk_size:
            yield " ".join(chunk) + " "
            chunk = [word]
            current_len = len(word)
            continue
        chunk.append(word)
        current_len = projected
    if chunk:
        yield " ".join(chunk)


def _extract_stream_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
                continue
            if item.get("type") == "text":
                nested = item.get("text")
                if isinstance(nested, str) and nested:
                    parts.append(nested)
    return "".join(parts)


def _stream_openai(
    *,
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    assistant: str = "general",
    timeout_seconds: float | None = None,
) -> tuple[Iterator[str], str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Configure it in environment variables.")

    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions")
    messages = _openai_messages(question, context, history, None, None, assistant)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": int(os.getenv("OPENAI_CHAT_MAX_TOKENS", "500")),
        "stream": True,
    }

    def iterator() -> Iterator[str]:
        try:
            session = requests.Session()
            session.trust_env = False
            with session.post(
                api_base,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=payload,
                stream=True,
                timeout=(5, timeout_seconds or LLM_REQUEST_TIMEOUT_SECONDS),
            ) as response:
                if response.status_code >= 400:
                    detail = response.text
                    raise RuntimeError(f"LLM request failed: HTTP {response.status_code} {detail}")
                for raw_line in response.iter_lines(decode_unicode=True):
                    line = str(raw_line or "").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        payload_item = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = payload_item.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = _extract_stream_text(delta.get("content"))
                    if text:
                        yield text
        except requests.RequestException as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

    return iterator(), model


def _ask_openai(
    *,
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    image_bytes: bytes | None,
    image_mime_type: str | None,
    assistant: str = "general",
    timeout_seconds: float | None = None,
) -> tuple[str, str | None, int | None, int | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Configure it in environment variables.")

    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions")
    messages = _openai_messages(question, context, history, image_bytes, image_mime_type, assistant)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": int(os.getenv("OPENAI_CHAT_MAX_TOKENS", "500")),
    }
    data = _http_post_json(
        api_base,
        payload,
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        timeout_seconds,
    )

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM response did not include choices")
    message = choices[0].get("message", {})
    answer = message.get("content")
    if not answer:
        raise RuntimeError("LLM response did not include answer content")

    usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    return answer.strip(), model, prompt_tokens, completion_tokens


def _ask_xai(
    *,
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    image_bytes: bytes | None,
    image_mime_type: str | None,
    assistant: str = "general",
    timeout_seconds: float | None = None,
) -> tuple[str, str | None, int | None, int | None]:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is missing. Configure it in environment variables.")

    model = os.getenv("XAI_CHAT_MODEL", "grok-4")
    api_base = os.getenv("XAI_API_BASE", "https://api.x.ai/v1/chat/completions")
    messages = _openai_messages(question, context, history, image_bytes, image_mime_type, assistant)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": int(os.getenv("OPENAI_CHAT_MAX_TOKENS", "500")),
    }
    data = _http_post_json(
        api_base,
        payload,
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        timeout_seconds,
    )

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM response did not include choices")
    message = choices[0].get("message", {})
    answer = message.get("content")
    if not answer:
        raise RuntimeError("LLM response did not include answer content")

    usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    return answer.strip(), model, prompt_tokens, completion_tokens


def _ask_ollama(
    *,
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    image_bytes: bytes | None,
    assistant: str = "general",
    timeout_seconds: float | None = None,
) -> tuple[str, str | None, int | None, int | None]:
    api_base = os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434/api/chat")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    messages = _ollama_messages(question, context, history, image_bytes, assistant)
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    data = _http_post_json(
        api_base,
        payload,
        {"Content-Type": "application/json"},
        timeout_seconds,
    )
    message = data.get("message") or {}
    answer = message.get("content")
    if not answer:
        raise RuntimeError("LLM response did not include answer content")
    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")
    return str(answer).strip(), model, prompt_tokens, completion_tokens


def _ask_pinecone(
    *,
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    image_bytes: bytes | None,
    assistant: str = "general",
    timeout_seconds: float | None = None,
) -> tuple[str, str | None, int | None, int | None]:
    api_key, _assistant_name, api_version, endpoint, _files_endpoint = _pinecone_config()

    if image_bytes:
        raise RuntimeError("Pinecone chat in this app currently supports text prompts only.")

    model = os.getenv("PINECONE_CHAT_MODEL", "gpt-4o").strip() or "gpt-4o"
    messages = _pinecone_messages(question, context, history, assistant)
    payload = {
        "messages": messages,
        "model": model,
        "stream": False,
        "temperature": 0.3,
    }
    data = _http_post_json(
        endpoint,
        payload,
        {
            "Content-Type": "application/json",
            "Api-Key": api_key,
            "X-Pinecone-Api-Version": api_version,
        },
        timeout_seconds,
    )

    response = data.get("chat_completion") if isinstance(data.get("chat_completion"), dict) else data
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("Pinecone response did not include choices")
    message = choices[0].get("message", {})
    answer = message.get("content")
    if not answer:
        raise RuntimeError("Pinecone response did not include answer content")

    usage = response.get("usage", {}) if isinstance(response.get("usage"), dict) else {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    resolved_model = response.get("model") or model
    return str(answer).strip(), resolved_model, prompt_tokens, completion_tokens


def _provider_candidates(preferred: str) -> list[str]:
    preferred = (preferred or "").strip().lower()
    if preferred in {"pinecone", "assistant"}:
        return ["pinecone", "openai", "xai", "ollama"]

    ordered: list[str] = []
    for candidate in [preferred, "pinecone", "openai", "xai", "ollama"]:
        normalized = candidate.strip().lower()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return ordered


def _provider_is_configured(provider: str) -> bool:
    provider = provider.strip().lower()
    if provider in {"pinecone", "assistant"}:
        return bool((os.getenv("PINECONE_API_KEY") or "").strip() and (os.getenv("PINECONE_ASSISTANT_NAME") or "").strip())
    if provider in {"openai"}:
        return bool((os.getenv("OPENAI_API_KEY") or "").strip())
    if provider in {"xai", "grok"}:
        return bool((os.getenv("XAI_API_KEY") or "").strip())
    if provider in {"ollama", "local"}:
        return bool((os.getenv("OLLAMA_API_BASE") or "").strip())
    return False


def _ask_provider(
    provider: str,
    *,
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    image_bytes: bytes | None,
    image_mime_type: str | None,
    assistant: str,
    timeout_seconds: float | None = None,
) -> tuple[str, str | None, int | None, int | None]:
    provider = provider.strip().lower()
    if provider in {"pinecone", "assistant"}:
        return _ask_pinecone(
            question=question,
            context=context,
            history=history,
            image_bytes=image_bytes,
            assistant=assistant,
            timeout_seconds=timeout_seconds,
        )
    if provider in {"xai", "grok"}:
        return _ask_xai(
            question=question,
            context=context,
            history=history,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            assistant=assistant,
            timeout_seconds=timeout_seconds,
        )
    if provider in {"ollama", "local"}:
        return _ask_ollama(
            question=question,
            context=context,
            history=history,
            image_bytes=image_bytes,
            assistant=assistant,
            timeout_seconds=timeout_seconds,
        )
    return _ask_openai(
        question=question,
        context=context,
        history=history,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        assistant=assistant,
        timeout_seconds=timeout_seconds,
    )


def ask_llm(
    *,
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
    assistant: str = "general",
) -> tuple[str, str | None, int | None, int | None]:
    preferred = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    deadline = time.monotonic() + LLM_REQUEST_TIMEOUT_SECONDS
    last_error: Exception | None = None
    for provider in _provider_candidates(preferred):
        if not _provider_is_configured(provider):
            continue
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            return _ask_provider(
                provider,
                question=question,
                context=context,
                history=history,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                assistant=assistant,
                timeout_seconds=remaining,
            )
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise RuntimeError(f"AI request failed after trying available providers: {last_error}") from last_error
    raise RuntimeError("No AI provider is configured.")


def stream_llm_response(
    *,
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    assistant: str = "general",
) -> tuple[Iterator[str], str | None, bool]:
    try:
        answer, model, _prompt_tokens, _completion_tokens = ask_llm(
            question=question,
            context=context,
            history=history,
            assistant=assistant,
        )
        return _chunk_text_for_stream(answer), model, False
    except Exception as exc:
        fallback_answer = build_fallback_chat_answer(
            question=question,
            context=context,
            failure_reason=str(exc),
        )
        return _chunk_text_for_stream(fallback_answer), "local-fallback", True
