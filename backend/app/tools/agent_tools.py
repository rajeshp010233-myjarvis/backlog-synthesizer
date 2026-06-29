"""
LLM-callable tool definitions for the agent pipeline.

Tools are defined in OpenAI function-calling format (the de-facto standard).
`to_anthropic_tools()` converts them for Anthropic's API.

Each agent that uses tool invocation calls `make_story_writer_executor()` (or a
similar factory) to get a closure that the provider's tool loop can execute.
"""
import json

# ── Tool schemas (OpenAI format) ───────────────────────────────────────────

STORY_WRITER_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_constraints",
            "description": (
                "Search the architecture constraint database for constraints relevant to a "
                "specific topic. Use this before writing any story that touches technical "
                "requirements, system boundaries, or security rules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Topic or keyword to search for "
                            "(e.g. 'DRM security', 'mobile downloads', 'authentication tokens')"
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_existing_tickets",
            "description": (
                "Search existing backlog tickets to check whether an intent is already "
                "partially or fully covered. Returns matching ticket summaries. Use this "
                "before writing a story that your plan flagged as duplication risk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": (
                            "Keyword or phrase to search for in existing ticket titles "
                            "and descriptions (e.g. 'DRM uplift', 'subtitle persistence')"
                        ),
                    }
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_intent_detail",
            "description": (
                "Get the full detail of a specific extracted intent by its ID, including "
                "the verbatim source quote and the speaker role. Use this when you need the "
                "exact quote for an acceptance criterion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent_id": {
                        "type": "string",
                        "description": "The intent ID to retrieve (e.g. 'INT-01')",
                    }
                },
                "required": ["intent_id"],
            },
        },
    },
]


# ── Format converter ───────────────────────────────────────────────────────

def to_anthropic_tools(oai_tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tool schemas to Anthropic format."""
    result = []
    for t in oai_tools:
        fn = t["function"]
        result.append({
            "name":         fn["name"],
            "description":  fn["description"],
            "input_schema": fn["parameters"],
        })
    return result


# ── Executor factory ───────────────────────────────────────────────────────

def make_story_writer_executor(
    session_id: str,
    intents: list[dict],
    existing_tickets: list[dict],
):
    """Return a tool executor function closed over the current pipeline state.

    The executor is called by the provider's tool loop with (tool_name, args_dict)
    and returns a string result that is fed back to the LLM as a tool result.
    """
    intent_index = {i.get("id", ""): i for i in intents}

    def execute(tool_name: str, args: dict) -> str:
        if tool_name == "search_constraints":
            from app.tools.vector_store import query_documents
            query = args.get("query", "")
            docs = query_documents("constraints", session_id, query, n_results=5)
            if not docs:
                return f"No architecture constraints found for query: '{query}'."
            return f"Found {len(docs)} constraint(s):\n\n" + "\n---\n".join(docs)

        if tool_name == "check_existing_tickets":
            keyword = args.get("keyword", "").lower()
            matches = [
                t for t in existing_tickets
                if keyword in (
                    t.get("title", "") + " " + t.get("description", "")
                ).lower()
            ]
            if not matches:
                return f"No existing tickets match '{keyword}'."
            summaries = [
                {"id": t.get("id"), "title": t.get("title"), "status": t.get("status")}
                for t in matches[:5]
            ]
            return f"Found {len(matches)} matching ticket(s):\n" + json.dumps(summaries, indent=2)

        if tool_name == "get_intent_detail":
            intent_id = args.get("intent_id", "")
            intent = intent_index.get(intent_id)
            if not intent:
                return f"Intent '{intent_id}' not found. Available IDs: {list(intent_index.keys())[:10]}"
            return json.dumps(intent, indent=2)

        return f"Unknown tool: '{tool_name}'. Available: search_constraints, check_existing_tickets, get_intent_detail"

    return execute
