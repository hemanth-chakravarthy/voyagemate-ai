# main.py (replace your existing file)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import datetime
import re

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# quick health and root endpoints (add near top of main.py)
@app.get("/")
def root():
    return {"status": "voyagemate-backend", "info": "FastAPI is running. Use /query to POST requests."}

@app.get("/health")
def health():
    return {"status": "ok"}


class QueryRequest(BaseModel):
    question: str

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

    # 4) Look for explicit heading-based sections (Generic Tourist Plan, Off-Beat Plan, Cost Breakdown, Daily Expense Budget)
    headings = [
        "Generic Tourist Plan",
        "Off-Beat Plan",
        "Cost Breakdown",
        "Daily Expense Budget"
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
    lines = (sections.get("Generic Tourist Plan", "") + "\n" + sections.get("Off-Beat Plan", "") + "\n" + intro).splitlines()
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
    candidate_text = "\n".join([sections.get("Generic Tourist Plan",""), sections.get("Off-Beat Plan",""), intro])
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
        "intro": intro or "",
        "generic_plan": sections.get("Generic Tourist Plan", ""),
        "offbeat_plan": sections.get("Off-Beat Plan", ""),
        "cost_breakdown_text": cost_info,
        "costs": costs,
        "weather": weather.strip() if weather else "",
        "daily_budget": sections.get("Daily Expense Budget", ""),
        "day_by_day": day_by_day,   # list of {"day": "...", "text": "..."}
        "attractions_list": attractions[:40],
        "raw": raw_text,
        "tools_used": tools_used,
    }

    return parsed

@app.post("/query")
async def query_travel_agent(query: QueryRequest):
    try:
        # call your existing agentic GraphBuilder
        from agent.agentic_workflow import GraphBuilder
        graph = GraphBuilder(model_provider="groq")
        react_app = graph()
        messages = {"messages": [query.question]}
        output = react_app.invoke(messages)

        # extract assistant text — your agent returns dict or string; be defensive
        assistant_text = ""
        if isinstance(output, dict) and "messages" in output:
            last = output["messages"][-1]
            if hasattr(last, "content"):
                assistant_text = last.content
            else:
                assistant_text = str(last)
        else:
            assistant_text = str(output)

        structured = split_sections(assistant_text)
        return JSONResponse(status_code=200, content=structured)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


