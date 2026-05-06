"""
AI Copilot for PharmaSignal — powered by Gemini Flash.

Uses Gemini function calling (tool use) to answer questions about safety signals,
drug mentions, sentiment trends, and post content for a given project.
"""
import json
import logging
import os
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from models.database import SafetySignal, EnrichedPost, RawPost, SignalSeverity
from models.schemas import CopilotRequest, CopilotResponse
from config import settings

logger = logging.getLogger(__name__)

# ── Tool definitions (Gemini FunctionDeclaration format) ──────────────────────

def _make_tools():
    from google.genai import types
    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="get_signal_summary",
            description="Get a summary of safety signals for the project: counts by severity, top drugs, top symptoms.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "severity": types.Schema(
                        type=types.Type.STRING,
                        enum=["HIGH", "MED", "LOW", "ALL"],
                        description="Filter by severity. Use ALL to get all.",
                    )
                },
                required=["severity"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_recent_signals",
            description="Fetch the most recent safety signals, optionally filtered by drug name.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "drug": types.Schema(type=types.Type.STRING, description="Drug name filter (optional)."),
                    "limit": types.Schema(type=types.Type.INTEGER, description="Number of signals to return (max 10)."),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="get_sentiment_trend",
            description="Get the average sentiment score for posts mentioning a specific drug.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "drug": types.Schema(type=types.Type.STRING, description="Drug name to analyse."),
                },
                required=["drug"],
            ),
        ),
        types.FunctionDeclaration(
            name="search_posts",
            description="Search enriched posts for a keyword or symptom.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "keyword": types.Schema(type=types.Type.STRING, description="Keyword or symptom to search for."),
                    "limit": types.Schema(type=types.Type.INTEGER, description="Number of results (max 10)."),
                },
                required=["keyword"],
            ),
        ),
    ])


# ── Tool implementations (unchanged) ─────────────────────────────────────────

async def _get_signal_summary(project_id: UUID, severity: str, db: AsyncSession) -> dict:
    from sqlalchemy import and_
    filters = [SafetySignal.project_id == project_id]
    if severity != "ALL":
        filters.append(SafetySignal.severity == SignalSeverity(severity))
    result = await db.execute(
        select(SafetySignal.severity, SafetySignal.drug, SafetySignal.symptom)
        .where(and_(*filters)).limit(200)
    )
    rows = result.all()
    counts, drugs, symptoms = {}, {}, {}
    for row in rows:
        sev = row.severity.value if hasattr(row.severity, "value") else str(row.severity)
        counts[sev] = counts.get(sev, 0) + 1
        if row.drug: drugs[row.drug] = drugs.get(row.drug, 0) + 1
        if row.symptom: symptoms[row.symptom] = symptoms.get(row.symptom, 0) + 1
    return {
        "total": len(rows), "by_severity": counts,
        "top_drugs": sorted(drugs.items(), key=lambda x: -x[1])[:5],
        "top_symptoms": sorted(symptoms.items(), key=lambda x: -x[1])[:5],
    }


async def _get_recent_signals(project_id: UUID, drug, limit: int, db: AsyncSession) -> list:
    from sqlalchemy import and_
    filters = [SafetySignal.project_id == project_id]
    if drug: filters.append(SafetySignal.drug.ilike(f"%{drug}%"))
    result = await db.execute(
        select(SafetySignal).where(and_(*filters))
        .order_by(desc(SafetySignal.created_at)).limit(min(limit or 5, 10))
    )
    return [
        {"severity": s.severity.value, "drug": s.drug, "symptom": s.symptom,
         "causality": s.causality, "confidence": round(s.confidence, 2),
         "context": s.context_window, "triage": s.triage_action.value if s.triage_action else "pending"}
        for s in result.scalars().all()
    ]


async def _get_sentiment_trend(project_id: UUID, drug: str, db: AsyncSession) -> dict:
    result = await db.execute(
        select(func.avg(EnrichedPost.sentiment_score), func.count(EnrichedPost.id))
        .where(EnrichedPost.project_id == project_id, EnrichedPost.drugs.any(drug.lower()))
    )
    row = result.one_or_none()
    if not row or not row[0]:
        return {"drug": drug, "avg_sentiment": None, "post_count": 0}
    avg = float(row[0])
    return {"drug": drug, "avg_sentiment": round(avg, 3), "post_count": row[1],
            "label": "positive" if avg > 0.05 else "negative" if avg < -0.05 else "neutral"}


async def _search_posts(project_id: UUID, keyword: str, limit: int, db: AsyncSession) -> list:
    result = await db.execute(
        select(EnrichedPost)
        .where(EnrichedPost.project_id == project_id, EnrichedPost.clean_text.ilike(f"%{keyword}%"))
        .order_by(desc(EnrichedPost.processed_at)).limit(min(limit or 5, 10))
    )
    return [
        {"text": p.clean_text[:200], "drugs": p.drugs, "symptoms": p.symptoms[:3],
         "sentiment": p.sentiment, "severity": p.safety_severity.value if p.safety_severity else None}
        for p in result.scalars().all()
    ]


async def _dispatch_tool(name: str, args: dict, project_id: UUID, db: AsyncSession) -> str:
    if name == "get_signal_summary":
        result = await _get_signal_summary(project_id, args.get("severity", "ALL"), db)
    elif name == "get_recent_signals":
        result = await _get_recent_signals(project_id, args.get("drug"), args.get("limit", 5), db)
    elif name == "get_sentiment_trend":
        result = await _get_sentiment_trend(project_id, args["drug"], db)
    elif name == "search_posts":
        result = await _search_posts(project_id, args["keyword"], args.get("limit", 5), db)
    else:
        result = {"error": f"Unknown tool: {name}"}
    return json.dumps(result, default=str)


# ── Main handler ──────────────────────────────────────────────────────────────

async def handle_copilot_message(
    project_id: UUID,
    data: CopilotRequest,
    db: AsyncSession,
) -> CopilotResponse:
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return CopilotResponse(
            text_response=(
                "⚠️ Copilot requires a Gemini API key. "
                "Add `GEMINI_API_KEY=AIza...` to your `.env` file. "
                "Get a free key at https://aistudio.google.com/apikey"
            ),
            card=None, tool_used=None,
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return CopilotResponse(
            text_response="⚠️ google-genai package not installed. Run: pip install google-genai",
            card=None, tool_used=None,
        )

    client = genai.Client(api_key=api_key)
    tools = _make_tools()

    system = (
        "You are PharmaSignal Copilot — an AI assistant for pharmacovigilance analysts. "
        "You help users understand safety signals, drug-symptom patterns, and patient sentiment "
        "detected from social media. Be concise and clinically precise. "
        "Always call a tool to fetch real data before answering quantitative questions."
    )

    # Build conversation history in Gemini format
    contents: list = []
    for m in data.conversation_history:
        role = "model" if m.role == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=m.content)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=data.message)]))

    tool_used = None
    card = None

    # Agentic loop — run until Gemini stops calling functions (max 5 turns)
    for _ in range(5):
        try:
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=[tools],
                    system_instruction=system,
                    max_output_tokens=1024,
                ),
            )
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                return CopilotResponse(
                    text_response=(
                        "⚠️ Gemini API rate limit reached. The free tier quota has been exhausted for today. "
                        "You can still use all other features (signals, compliance, reports). "
                        "The quota resets daily — try again tomorrow, or add billing at https://aistudio.google.com/apikey"
                    ),
                    card=None, tool_used=None,
                )
            logger.exception("Gemini API error")
            return CopilotResponse(
                text_response=f"⚠️ Gemini API error: {err_str[:200]}",
                card=None, tool_used=None,
            )

        candidate = response.candidates[0]
        contents.append(candidate.content)  # add model turn to history

        # Check if any part is a function call
        fc_part = next(
            (p for p in candidate.content.parts if hasattr(p, "function_call") and p.function_call),
            None,
        )

        if fc_part:
            fc = fc_part.function_call
            tool_used = fc.name
            tool_args = dict(fc.args) if fc.args else {}
            tool_result_str = await _dispatch_tool(fc.name, tool_args, project_id, db)
            tool_result_obj = json.loads(tool_result_str)

            # Build card for specific tools
            if fc.name == "get_signal_summary":
                card = {"type": "signal_summary", "data": tool_result_obj}
            elif fc.name == "get_recent_signals":
                card = {"type": "signal_list", "data": tool_result_obj}

            # Feed result back into conversation
            contents.append(types.Content(
                role="user",
                parts=[types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response={"result": tool_result_obj},
                    )
                )],
            ))

        else:
            # Model produced a text response — we're done
            text = next(
                (p.text for p in candidate.content.parts if hasattr(p, "text") and p.text),
                "Analysis complete.",
            )
            return CopilotResponse(text_response=text, card=card, tool_used=tool_used)

    return CopilotResponse(
        text_response="Analysis complete. Check the data panel for details.",
        card=card, tool_used=tool_used,
    )
