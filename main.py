# main.py (replace your existing file)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from utils.config_loader import load_config
import json
import time
import os
import datetime
import re

load_dotenv()
from utils.semantic_cache import SemanticCache
from logger.logging import log_cache_event

app = FastAPI()

class SimpleTTLCache:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._store = {}

    def get(self, key):
        item = self._store.get(key)
        if not item:
            return None
        value, ts = item
        if time.time() - ts > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key, value):
        self._store[key] = (value, time.time())


_config = load_config()
_perf = _config.get("performance", {})
_response_cache = SimpleTTLCache(int(_perf.get("response_cache_ttl_seconds", 300)))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global stats for semantic cache
cache_stats = {
    "hits": 0,
    "misses": 0,
    "total_savings_usd": 0.0,
    "total_latency_saved_ms": 0.0
}

_semantic_cache = None

@app.on_event("startup")
async def startup_event():
    print("Warming up system resources...")
    try:
        from utils.vector_store import VectorStore
        # This will initialize HuggingFace embeddings and connect to Qdrant
        VectorStore()
        print("Embeddings loaded and vector store connected.")
    except Exception as e:
        print(f"Warning: Failed to warm up VectorStore: {e}")
        
    try:
        from agent.agentic_workflow import MultiAgentGraphBuilder
        # This will load the LLM connection
        MultiAgentGraphBuilder(model_provider="groq")
        print("LLM connection warmed up.")
    except Exception as e:
        print(f"Warning: Failed to warm up LLM: {e}")

    global _semantic_cache
    try:
        _semantic_cache = SemanticCache()
        print("Semantic Cache initialized.")
    except Exception as e:
        print(f"Warning: Failed to initialize Semantic Cache: {e}")

@app.get("/")
def root():
    return {"status": "voyagemate-backend", "info": "FastAPI is running. Use /query to POST requests."}

@app.get("/health")
def health():
    return {"status": "ok"}


class QueryRequest(BaseModel):
    question: str
    user_id: str = Field(default="anonymous")
    profile: dict = Field(default_factory=dict)
    fast_mode: bool = Field(default=True)
    minimal_mode: bool = Field(default=False)
    instant_mode: bool = Field(default=False)

class FeedbackRequest(BaseModel):
    user_id: str = Field(default="anonymous")
    plan_id: str
    rating: int
    feedback: str

def split_sections(text: str) -> dict:
    """
    Improved splitter:
    - Extract 'Tools Used' block and helper lines.
    - Detect explicit 'Weather' blocks using keywords and isolate them.
    - Extract 'day_by_day' itinerary when the assistant uses "Day 1", "Day 2", or "Day-by-Day" style.
    - Fill generic_plan/offbeat_plan if explicit headings exist; otherwise provide day_by_day and raw.
    """
    raw_text = text or ""
    working_text = raw_text
    tools_used = []

    # 1) Extract "Tools Used" block (case-insensitive)
    m_tools = re.search(r'\bTools Used\b', working_text, flags=re.I)
    if m_tools:
        tools_start = m_tools.start()
        tools_block = working_text[tools_start:]
        working_text = working_text[:tools_start].rstrip()

        # parse tools lines
        lines = tools_block.splitlines()[1:]
        extracted = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            if re.search(r'\b(call|use|invoke)\b', ln, flags=re.I) or ':' in ln:
                continue
            # likely a tool name or short phrase
            if len(ln.split()) <= 4:
                extracted.append(ln)
        # dedupe
        seen = set()
        for t in extracted:
            if t not in seen:
                tools_used.append(t)
                seen.add(t)

    # 2) Remove helper lines ("Call the X function") across working_text
    def _strip_helper_lines(s: str) -> str:
        lines = s.splitlines()
        cleaned = []
        for ln in lines:
            s_ln = ln.strip()
            if re.search(r'call the [a-zA-Z0-9_]+ function', s_ln, flags=re.I):
                continue
            if re.search(r'\b(Call|Use|Invoke)\b', s_ln) and len(s_ln.split()) < 8:
                continue
            cleaned.append(ln)
        return "\n".join(cleaned).strip()

    working_text = _strip_helper_lines(working_text)

    # 3) Try to extract a weather block if present (look for "Weather" word nearby)
    weather = ""
    # Patterns that likely introduce weather block
    weather_patterns = [r'\bWeather\b', r'\bWeather Details\b', r'\bWeather Overview\b', r'\bForecast\b']
    weather_idx = None
    for p in weather_patterns:
        m = re.search(p, working_text, flags=re.I)
        if m:
            weather_idx = m.start()
            break
    if weather_idx is not None:
        # take the weather block until the next blank-line+capitalized-heading or till 3000 chars heuristically
        # We'll look for next major heading like "Day", "Cost", "Generic Tourist Plan", "Off-Beat Plan", etc.
        next_heading = re.search(r'\n(?:\s*\n|(?=(?:Day\s*\d|\bCost\b|\bGeneric Tourist Plan\b|\bOff-Beat Plan\b|\bDaily Expense Budget\b)))', working_text[weather_idx:], flags=re.I)
        if next_heading:
            end = weather_idx + next_heading.start()
            weather = working_text[weather_idx:end].strip()
            # remove from working_text
            working_text = (working_text[:weather_idx] + working_text[end:]).strip()
        else:

            # take till end
            weather = working_text[weather_idx:].strip()
            working_text = working_text[:weather_idx].strip()

    working_text = working_text.strip()

    # 4) Look for explicit heading-based sections
    headings = [
        "Trip Summary",
        "Weather",
        "Itinerary",
        "Cost Breakdown"
    ]
    lower = working_text.lower()
    positions = {}
    for h in headings:
        idx = lower.find(h.lower())
        if idx != -1:
            positions[h] = idx

    sections = {}
    if positions:
        ordered = sorted(positions.items(), key=lambda x: x[1])
        for i, (title, idx) in enumerate(ordered):
            start = idx
            end = len(working_text)
            if i + 1 < len(ordered):
                end = ordered[i + 1][1]
            sections[title] = working_text[start:end].strip()
        first_idx = ordered[0][1]
        intro = working_text[:first_idx].strip() if first_idx > 0 else ""
    else:
        intro = working_text

    # 5) Day-by-day extraction (robust): find lines that start with "Day 1", "Day 2", or patterns like "Day-by-Day", "Day-by-day Itinerary"
    day_by_day = []
    # Common markers: "Day 1:", "Day 1 -", "Day 1", "Day 01"
    day_line_regex = re.compile(r'^\s*(?:Day|D)\s*0*\d+\b', flags=re.I)
    lines = (sections.get("Itinerary", "") + "\n" + intro).splitlines()
    current_day = None
    current_content = []
    for ln in lines:
        if day_line_regex.match(ln):
            # push previous
            if current_day:
                day_by_day.append({"day": current_day, "text": "\n".join(current_content).strip()})
            # start new
            current_day = ln.strip()
            current_content = []
        else:
            if current_day:
                current_content.append(ln)
    if current_day:
        day_by_day.append({"day": current_day, "text": "\n".join(current_content).strip()})

    # If we didn't find day_by_day above, also try finding a block that mentions "Day-by-Day" or "Day-by day" and then split by "Day X"
    if not day_by_day:
        match = re.search(r'(Day-?by-?Day|Day by Day|Day-by-day|Day-by Day|Day-by-Day)', intro, flags=re.I)
        if match:
            # try splitting intro by Day occurrences
            parts = re.split(r'(?i)(?=^\s*Day\s*0*\d+\b)', intro, flags=re.M)
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                first_line = p.splitlines()[0].strip()
                if day_line_regex.match(first_line):
                    rest = "\n".join(p.splitlines()[1:]).strip()
                    day_by_day.append({"day": first_line, "text": rest})

    # 6) Cost parsing (same heuristics)
    cost_info = sections.get("Cost Breakdown", "")
    def parse_costs(block: str):
        if not block:
            return {}
        matches = re.findall(r'([A-Za-z \-:&]+)[\:\-]?\s*₹\s*([\d,]+)', block)
        result = {}
        for label, num in matches:
            try:
                n = int(num.replace(",", ""))
            except ValueError:
                continue
            result[label.strip()] = n
        tot = re.search(r'\bTotal\b\s*[:\-]?\s*₹\s*([\d,]+)', block, re.I)
        if tot:
            try:
                result["Total"] = int(tot.group(1).replace(",", ""))
            except ValueError:
                pass
        return result

    costs = parse_costs(cost_info)

    # 7) Extract attractions heuristically (from day_by_day or plans)
    attractions = []
    # candidate text to search
    candidate_text = "\n".join([sections.get("Itinerary",""), intro])
    for line in candidate_text.splitlines():
        line = line.strip()
        if len(line) < 3:
            continue
        m = re.match(r'^([A-Z][A-Za-z0-9 &\'\-\.\:]+?)(?:\:|\-|\—|\(|$)', line)
        if m:
            name = m.group(1).strip().rstrip(':')
            if name.lower().startswith("hotel name") or name.lower().startswith("breakfast"):
                continue
            if name not in attractions:
                attractions.append(name)
        # also capture lines that look like "Om Beach" etc (two words with capitalized first letters)
        if re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+$', line):
            if line not in attractions:
                attractions.append(line)

    # 8) Put it all together
    parsed = {
        "intro": sections.get("Trip Summary", intro or ""),
        "generic_plan": sections.get("Itinerary", ""),
        "offbeat_plan": "",
        "cost_breakdown_text": cost_info,
        "costs": costs,
        "weather": sections.get("Weather", weather.strip() if weather else ""),
        "daily_budget": "",
        "day_by_day": day_by_day,   # list of {"day": "...", "text": "..."}
        "attractions_list": attractions[:40],
        "raw": raw_text,
        "tools_used": tools_used,
    }

    return parsed

def _select_mode(query: str) -> str:
    """Auto-select mode based on query complexity."""
    if len(query) < 20:
        return "instant"
    elif any(word in query.lower() for word in ["budget", "plan", "itinerary", "days"]):
        return "full"
    else:
        return "fast"

async def _extract_destination_fast(query: str) -> str:
    """Hybrid extraction: tries fast LLM, falls back to regex."""
    import re
    # Fallback heuristic
    fallback = query.strip().split(" for ")[0][:40]
    
    try:
        from utils.model_loader import ModelLoader
        llm = ModelLoader(model_provider="groq").load_llm()
        prompt = f"Extract ONLY the main travel destination city/country from this query. Output nothing but the location name. Query: '{query}'"
        resp = await llm.ainvoke(prompt)
        dest = resp.content.strip()
        if len(dest) > 40 or "\n" in dest:
            return fallback
        return dest
    except Exception:
        return fallback

@app.post("/query")
async def query_travel_agent(query: QueryRequest):
    import asyncio
    t_start = time.time()
    log_data = {"mode": "", "cache_hit": False, "rag_time": 0, "tool_time": 0, "llm_time": 0, "total": 0}

    try:
        actual_mode = _select_mode(query.question)
        log_data["mode"] = actual_mode

        # If full mode, try to extract destination for tools
        destination = ""
        if actual_mode == "full":
            destination = await _extract_destination_fast(query.question)

        # Robust Cache Key
        profile_items = [(k, tuple(v) if isinstance(v, list) else v) for k, v in query.profile.items()] if query.profile else []
        profile_hash = hash(frozenset(profile_items))

        cache_key = hash(query.question.strip().lower() + query.user_id + str(profile_hash) + actual_mode + destination)
        
        cached = _response_cache.get(cache_key)
        if cached:
            log_data["cache_hit"] = True
            log_data["total"] = round((time.time() - t_start) * 1000)
            print(f"FAST ARCH: {json.dumps(log_data)}")
            return JSONResponse(status_code=200, content=cached)

        # 1.5) Semantic Cache Check
        if _semantic_cache:
            semantic_cached = _semantic_cache.get(query.question)
            if semantic_cached:
                log_data["cache_hit"] = True
                log_data["semantic_hit"] = True
                latency = round((time.time() - t_start) * 1000)
                log_data["total"] = latency
                
                # Update global stats
                cache_stats["hits"] += 1
                savings = _perf.get("semantic_cache", {}).get("estimated_cost_per_call", 0.02)
                cache_stats["total_savings_usd"] += savings
                # Assume average LLM call takes 3000ms (as per user request "2-5 seconds")
                latency_saved = 3000 - latency
                cache_stats["total_latency_saved_ms"] += max(0, latency_saved)
                
                log_cache_event("semantic_hit", {
                    "question": query.question,
                    "latency_ms": latency,
                    "savings_usd": savings
                })
                
                print(f"FAST ARCH (SEMANTIC HIT): {json.dumps(log_data)}")
                print(f"STATS: Total Saved: ${cache_stats['total_savings_usd']:.2f}, Latency Saved: {cache_stats['total_latency_saved_ms']/1000:.1f}s")
                return JSONResponse(status_code=200, content=semantic_cached)
        
        cache_stats["misses"] += 1

        from agent.agentic_workflow import MultiAgentGraphBuilder
        from utils.user_profiles import UserProfileStore
        
        user_id = query.user_id or "anonymous"
        if query.profile:
            UserProfileStore().upsert_profile(user_id, query.profile)

        # Base messages for context builder
        messages = {
            "messages": [query.question],
            "user_id": user_id,
            "fast_mode": actual_mode == "fast",
            "instant_mode": actual_mode == "instant",
            "minimal_mode": query.minimal_mode,
        }

        # Context Building Phase (RAG/Memory)
        t_rag_start = time.time()
        builder = MultiAgentGraphBuilder(model_provider="groq")
        context = builder._build_context(messages)
        log_data["rag_time"] = round((time.time() - t_rag_start) * 1000)

        tool_context = ""
        if actual_mode == "full" and destination:
            t_tool_start = time.time()
            from utils.weather_info import WeatherForecastTool
            from utils.place_info_search import FoursquarePlaceSearchTool
            
            weather_service = WeatherForecastTool(api_key=os.environ.get("OPENWEATHER_API_KEY", ""))
            places_service = FoursquarePlaceSearchTool()
            
            # Parallel tool fetching with timeout
            async def safe_weather():
                try: return await asyncio.wait_for(weather_service.get_current_weather(destination), timeout=1.5)
                except Exception: return {}
                
            async def safe_places():
                try: return await asyncio.wait_for(places_service.search_attractions(destination, limit=3), timeout=1.5)
                except Exception: return {}

            w_data, p_data = await asyncio.gather(safe_weather(), safe_places())
            
            if w_data and w_data.get('main'):
                temp = w_data['main'].get('temp', 'N/A')
                desc = w_data.get('weather', [{}])[0].get('description', 'N/A')
                tool_context += f"Current weather in {destination}: {temp}°C, {desc}\n"
            if p_data and isinstance(p_data, dict) and p_data.get('results'):
                names = [r.get('name') for r in p_data['results'][:3] if r.get('name')]
                tool_context += f"Top attractions in {destination}: {', '.join(names)}\n"
            
            log_data["tool_time"] = round((time.time() - t_tool_start) * 1000)

        # Build Prompt
        input_question = [builder.system_prompt]
        if context.get("memory"):
            input_question.append(f"User Past Trips:\n{context['memory']}")
        if context.get("profile"):
            input_question.append(context["profile"])
        if context.get("knowledge"):
            input_question.append(f"Knowledge Base Context:\n{context['knowledge']}")
        if context.get("feedback"):
            input_question.append(f"Feedback Context:\n{context['feedback']}")
        if tool_context:
            input_question.append(f"Live Tool Data:\n{tool_context}")
        
        input_question.append("Do not assume missing data. Only use provided context and general knowledge. Do not attempt to call external tools.")
        input_question.append(query.question)

        t_llm_start = time.time()
        
        # Bypass Graph for Fast/Instant modes
        if actual_mode in ["instant", "fast"]:
            # Direct LLM call
            response = await builder.llm.ainvoke(input_question)
            assistant_text = response.content
        else:
            # Full graph for refiner
            planner_response = await builder.llm.ainvoke(input_question)
            
            # Refiner call
            refiner_prompt = "You are a local expert and budget optimizer. Add hidden gems, refine costs to match budget. Keep it structured."
            refiner_input = [builder.system_prompt, refiner_prompt, planner_response.content]
            final_response = await builder.llm.ainvoke(refiner_input)
            assistant_text = final_response.content

        log_data["llm_time"] = round((time.time() - t_llm_start) * 1000)

        structured = split_sections(assistant_text)
        structured["plan_id"] = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

        try:
            plan_metadata = {
                "user_id": user_id,
                "destination": destination,
                "duration": None,
                "budget": None,
                "preferences": query.profile.get("preferred_places", []),
                "plan_id": structured["plan_id"],
            }
            from utils.vector_store import VectorStore
            VectorStore().save_trip(assistant_text, plan_metadata)
        except Exception:
            pass

        _response_cache.set(cache_key, structured)
        if _semantic_cache:
            _semantic_cache.set(query.question, structured)
            log_cache_event("cache_miss_stored", {
                "question": query.question,
                "latency_ms": round((time.time() - t_start) * 1000)
            })
        
        log_data["total"] = round((time.time() - t_start) * 1000)
        print(f"FAST ARCH: {json.dumps(log_data)}")
        
        return JSONResponse(status_code=200, content=structured)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/feedback")
async def submit_feedback(payload: FeedbackRequest):
    try:
        from utils.feedback_store import FeedbackStore
        from utils.vector_store import VectorStore
        from utils.user_profiles import UserProfileStore

        feedback_store = FeedbackStore()
        vector_store = VectorStore()
        profile_store = UserProfileStore()

        entry = {
            "user_id": payload.user_id,
            "plan_id": payload.plan_id,
            "rating": payload.rating,
            "feedback": payload.feedback,
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
        feedback_store.add_feedback(entry)

        if payload.rating <= 3:
            profile_store.upsert_profile(
                payload.user_id,
                {
                    "budget_range": "low",
                },
            )

        vector_store.save_feedback(
            payload.feedback,
            {
                "user_id": payload.user_id,
                "plan_id": payload.plan_id,
                "rating": payload.rating,
            },
        )

        return JSONResponse(status_code=200, content={"status": "ok"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


