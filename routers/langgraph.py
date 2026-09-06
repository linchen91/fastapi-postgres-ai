"""
Smart Search Assistant – A real-world search system powered by LangGraph and the Tavily API
1. Understand user needs
2. Perform real-world information searches using the Tavily API
3. Generate answers based on search results

Special handling: Bayern traffic queries use BR.de data directly.
"""

from typing import TypedDict, Annotated
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from dotenv import load_dotenv
from tavily import TavilyClient
from fastapi import APIRouter, HTTPException
import os, httpx

load_dotenv(override=True)
router = APIRouter()

TRAFFIC_JSON_URL = 'https://www.br.de/verkehrskarte/verkehrsdaten/verkehrsmeldungen.json'
TRAFFIC_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

BAYERN_KEYWORDS = [
    'bayern', 'bavaria', 'münchen', 'munich', 'nürnberg', 'nuremberg',
    'augsburg', 'regensburg', 'würzburg', 'wurzburg', 'ingolstadt'
]

TRAFFIC_KEYWORDS = [
    'verkehr', 'traffic', 'stau', 'meldung', 'meldung',
    'autobahn', 'straße', 'strasse', 'road', 'unfall', 'accident',
    'br.de', 'verkehrskarte', 'verkehrsdaten'
]


def is_bayern_traffic_query(query: str) -> bool:
    query_lower = query.lower()
    return any(kw in query_lower for kw in BAYERN_KEYWORDS) and any(k in query_lower for k in TRAFFIC_KEYWORDS)

class SearchState(TypedDict):
    messages: Annotated[list, add_messages]
    user_query: str        # user query
    search_query: str      # search keywords extracted from query
    search_results: str    # Tavily search results
    final_answer: str      # final answer
    step: str              # current step


# OpenRouter
LLM_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID")

_llm = None
_tavily_client = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=LLM_MODEL_ID,
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            temperature=0.7
        )
    return _llm


def get_tavily():
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _tavily_client

def understand_query_node(state: SearchState) -> SearchState:
    """
    Step 1: Understand the user's query and generate a search query.
    """
    user_message = next(
        (
            message.content
            for message in state["messages"]
            if isinstance(message, HumanMessage)
        ),
        "",
    )

    if not user_message or not user_message.strip():
        return {
            'user_query': '',
            'search_query': '',
            'step': 'error',
            'messages': [AIMessage(content='No user message found in the state.')]
        }

    understand_prompt = f"""Analyze user queries："{user_message}"

    Please complete two tasks:
    1. Concisely summarize what the user wants to know.
    2. Generate the most suitable search keywords (precise terms in either
        German or English, depending on the query's language).

    Format:
    Understanding: [Summary of user needs]
    Search Terms: [Best search keywords]"""

    response = get_llm().invoke([HumanMessage(content=understand_prompt)])

    # Extract search keywords
    response_text = response.content
    search_query = user_message  # Use the original query by default.

    for marker in ("Search Terms：", "Search Terms:", "Search keywords：", "Search keywords:"):
        if marker in response_text:
            parts = response_text.split(marker, 1)
            if len(parts) > 1 and parts[1].strip():
                search_query = parts[1].strip()
            break

    return {
        'user_query': response.content,
        'search_query': search_query,
        'step': 'understood',
        'messages': [AIMessage(content=f"I understand your requirements：{response.content}")]
    }


def tavily_search_node(state: SearchState) -> SearchState:
    """Step 2: Perform real-world searches using the Tavily API or BR.de traffic data."""

    search_query = state["search_query"]
    user_query = state.get("user_query", "")

    if is_bayern_traffic_query(user_query):
        try:
            print(f"🚗 Bayern traffic detected, fetching BR.de data...")
            with httpx.Client(
                headers=TRAFFIC_HEADERS,
                verify=False,
                follow_redirects=True,
                timeout=30.0,
            ) as client:
                res = client.get(TRAFFIC_JSON_URL)
                res.raise_for_status()
                data = res.json()

            messages = []
            for category in data.get('bmtKategorien', []):
                cat_title = category.get('titel', '')
                for msg in category.get('meldungen', []):
                    headline = msg.get('headline', '')
                    description = '\n'.join(msg.get('absatz', []))
                    time = msg.get('meldungsZeit', '')
                    messages.append(f"[{cat_title}] {headline}\n{description}\nZeit: {time}")

            summary = data.get('verkehrslageHinweis', '')
            timestamp = data.get('exportZeitstempel', '')
            total = len(messages)

            result = f"Bayern Verkehrslage (BR.de) - Stand: {timestamp}\n"
            result += f"Zusammenfassung: {summary}\n"
            result += f"Gesamt: {total} Meldungen\n\n"
            result += "\n---\n".join(messages) if messages else "Keine Meldungen verfügbar."

            return {
                "search_results": result,
                "step": "searched",
                "messages": [AIMessage(content="✅ Bayern traffic data loaded from BR.de!")]
            }
        except Exception as e:
            print(f"❌ BR.de fetch failed: {e}, falling back to Tavily")

    try:
        print(f"🔍 Searching...: {search_query}")

        # Call the Tavily Search API
        response = get_tavily().search(
            query=search_query,
            search_depth="basic",
            include_answer=True,
            include_raw_content=False,
            max_results=5
        )

        # Process search results
        search_results = ""

        # Prioritize using Tavily's comprehensive answers.
        if response.get("answer"):
            search_results = f"Comprehensive Answer：\n{response['answer']}\n\n"

        # Add specific search results
        if response.get("results"):
            search_results += "Related information: \n"
            for i, result in enumerate(response["results"][:3], 1):
                title = result.get("title", "")
                content = result.get("content", "")
                url = result.get("url", "")
                search_results += f"{i}. {title}\n{content}\nSource：{url}\n\n"

        if not search_results:
            search_results = "Sorry, no relevant information was found. "

        return {
            "search_results": search_results,
            "step": "searched",
            "messages": [AIMessage(content=f"✅ Search complete! Relevant information found; compiling the answer for you...")]
        }
    except Exception as e:
        error_msg = f"An error occurred during the search: {str(e)}"
        print(f"❌ {error_msg}")

        return {
            "search_results": f"Search failed:{error_msg}",
            "step": "search_failed",
            "messages": [AIMessage(content="❌ An issue encountered while searching, answer based on the existing knowledge...")]
        }

def generate_answer_node(state: SearchState) -> SearchState:
    """Step 3: Generate the final answer based on the search results."""

    user_query = state.get("user_query", "").strip()
    if not user_query:
        return {
            "final_answer": "Unable to generate an answer: User query missing",
            "step": "error",
            "messages": [AIMessage(content="❌ No user query provided; unable to generate an answer")]
        }

    # Extract the ORIGINAL user message for language detection.
    # state["user_query"] is the LLM's analysis, NOT the user's actual question.
    original_message = ""
    for message in state["messages"]:
        if isinstance(message, HumanMessage):
            original_message = message.content
            break

    # Check for search results.
    if state["step"] == "search_failed":
        # If the search fails, answer based on LLM knowledge.
        fallback_prompt = f"""The search API is temporarily unavailable; please answer the user's question based on existing knowledge.

        User's original question: {original_message}

        Please provide a helpful answer in HTML format and indicate that it is based on existing knowledge.
        You MUST answer in the SAME language as the user's original question above.
        If the user asked in English, respond in English. If the user asked in German, respond in German.
        Use proper HTML tags like <h3>, <p>, <ul>, <li>, <code>, <pre>, <strong>, <em> for formatting."""

        response = get_llm().invoke([HumanMessage(content=fallback_prompt)])

        return {
            "final_answer": response.content,
            "step": "completed",
            "messages": [AIMessage(content=response.content)]
        }

    # Generate an answer based on search results.
    answer_prompt = f"""Provide a complete and accurate answer to the user based on the following search results.

    User's original question: {original_message}

    Search results:
    {state['search_results']}

    Requirements:
    1. You MUST answer in the SAME language as the user's original question above. If the user asked in English, respond in English. If the user asked in German, respond in German. Do NOT switch languages based on the search results language.
    2. Synthesize search results to provide accurate and useful answers.
    3. For technical questions, provide specific solutions or code.
    4. Cite sources for key information.
    5. Ensure the answer is well-structured and easy to understand.
    6. If search results are incomplete, state this and offer supplementary suggestions.
    7. Format your answer using HTML tags: <h3>, <p>, <ul>, <li>, <code>, <pre>, <strong>, <em>, <a>, <blockquote>.
    8. Use <code> and <pre> for code snippets.
    9. Use <ul>/<li> for lists and <a href="..."> for links.
    10. Do NOT include <html>, <head>, <body> tags - just the content HTML.
    11. Do NOT include markdown formatting - use HTML only."""

    response = get_llm().invoke([HumanMessage(content=answer_prompt)])

    return {
        "final_answer": response.content,
        "step": "completed",
        "messages": [AIMessage(content=response.content)]
    }

# Build a search workflow
def create_search_assistant():
    workflow = StateGraph(SearchState)

    # Add three nodes.
    workflow.add_node("understand", understand_query_node)
    workflow.add_node("search", tavily_search_node)
    workflow.add_node("answer", generate_answer_node)

    # Set up a linear workflow
    workflow.add_edge(START, "understand")
    workflow.add_edge("understand", "search")
    workflow.add_edge("search", "answer")
    workflow.add_edge("answer", END)

    # Compiled graph
    memory = InMemorySaver()
    app = workflow.compile(checkpointer=memory)

    return app

@router.post("/langgraph")
async def ai_langgraph(payload: dict):
    """Main function: Run the intelligent search assistant."""

    # Check API key
    if not LLM_API_KEY or not LLM_BASE_URL or not LLM_MODEL_ID:
        raise HTTPException(status_code=500, detail="OpenRouter API configuration is missing.")
    if not os.getenv("TAVILY_API_KEY"):
        raise HTTPException(status_code=500, detail="❌ Error: TAVILY_API_KEY is missing.")

    app = create_search_assistant()

    print("🔍 Smart search assistant activated!")

    user_input = payload.get('query')

    if not user_input:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body.")

    config = {"configurable": {"thread_id": f"search-session-1"}}

    # Initial state
    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "user_query": "",
        "search_query": "",
        "search_results": "",
        "final_answer": "",
        "step": "start"
    }

    try:
        print("\n" + "="*60)

        # Execute workflow
        async for output in app.astream(initial_state, config=config):
            for node_name, node_output in output.items():
                if "messages" in node_output and node_output["messages"]:
                    latest_message = node_output["messages"][-1]
                    if isinstance(latest_message, AIMessage):
                        if node_name == "understand":
                            print(f"🧠 Comprehension stage: {latest_message.content}")
                        elif node_name == "search":
                            print(f"🔍 Search phase: {latest_message.content}")
                        elif node_name == "answer":
                            print(f"\n💡 Final Answer:\n{latest_message.content}")
                            return {"langgraph": latest_message.content}

        print("\n" + "="*60 + "\n")
        return {"langgraph": "No response generated."}

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ An error occurred.: {e}")
        raise HTTPException(status_code=500, detail=str(e))