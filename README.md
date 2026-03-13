# VoyageMate AI

![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B?logo=streamlit)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
![LangChain](https://img.shields.io/badge/AI-LangChain-1e88e5)
![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-8e24aa)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)

VoyageMate AI is an agentic AI-powered travel planner that generates personalized itineraries, real-time weather insights, place recommendations, and detailed cost breakdowns. It uses a ReAct-based LangGraph workflow to orchestrate multiple external APIs through a FastAPI backend, with a Streamlit frontend for user interaction.

**Live Demo:** [voyagemate-frontend.onrender.com](https://voyagemate-frontend.onrender.com)

---

## Features

- **AI Itinerary Generation** — Produces both a standard tourist plan and an off-beat alternative for every destination.
- **Day-by-Day Breakdown** — Structured daily itinerary with activities, hotel suggestions, and approximate costs per day.
- **Real-Time Weather** — Fetches current weather and a 5-day forecast for the destination using OpenWeatherMap.
- **Place Discovery** — Recommends attractions, restaurants, and activities via Foursquare with Tavily as a fallback.
- **Expense Estimation** — Calculates hotel, food, transport, and activity costs with a total trip budget.
- **Currency Conversion** — Converts costs between currencies using live exchange rates.
- **Geocoding & Directions** — Forward geocoding and turn-by-turn routing via LocationIQ.
- **Agentic Workflow** — Built on LangGraph's ReAct loop so the agent calls tools only when needed and composes a single, coherent response.

---

## Architecture

```
User (Streamlit UI)
        |
        | HTTP POST /query
        v
  FastAPI Backend (main.py)
        |
        v
  GraphBuilder (LangGraph ReAct Agent)
        |
   _____|_____________________________________
  |           |           |         |         |
Weather    Places    Calculator  Currency   Tavily
(OWM)   (Foursquare/ (internal)  (ExchangeRate (fallback
         LocationIQ)              API)        search)
```

The backend parses the agent's Markdown response into structured sections (weather, day-by-day, costs, etc.) and returns a JSON object to the frontend for display.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI, Uvicorn |
| AI / Orchestration | LangChain, LangGraph |
| LLM Provider | Groq (`llama-3.1-8b-instant`) |
| Place Search | Foursquare Places API v3 |
| Fallback Search | Tavily Search |
| Weather | OpenWeatherMap API |
| Geocoding / Routing | LocationIQ |
| Currency Conversion | ExchangeRate API |
| Deployment | Render (backend + frontend separately) |

---

## Project Structure

```
voyagemate-ai/
├── agent/
│   └── agentic_workflow.py     # LangGraph GraphBuilder and ReAct agent
├── config/
│   └── config.yaml             # LLM provider and model configuration
├── exception/                  # Custom exception classes
├── logger/                     # Logging configuration
├── notebook/                   # Jupyter notebooks for experimentation
├── prompt_library/
│   └── prompt.py               # System prompt for the travel agent
├── tools/
│   ├── weather_info_tool.py    # LangChain tool wrappers for weather
│   ├── place_search_tool.py    # LangChain tool wrappers for place search
│   ├── expense_calculator_tool.py
│   └── currency_conversion_tool.py
├── utils/
│   ├── model_loader.py         # LLM loading (Groq / OpenAI)
│   ├── config_loader.py        # YAML config reader
│   ├── weather_info.py         # OpenWeatherMap API client
│   ├── place_info_search.py    # Foursquare, LocationIQ, Tavily clients
│   ├── currency_converter.py   # ExchangeRate API client
│   ├── expense_calculator.py   # Budget calculation helpers
│   └── save_to_document.py     # Export itinerary to Markdown file
├── main.py                     # FastAPI application and response parser
├── streamlit_app.py            # Streamlit frontend
├── requirements.txt
└── .env                        # API keys (never commit this file)
```

---

## Getting Started

### Prerequisites

- Python 3.12
- API keys for: Groq, Foursquare, LocationIQ, OpenWeatherMap, Tavily, ExchangeRate API

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-username/voyagemate-ai.git
   cd voyagemate-ai
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   source .venv/bin/activate   # macOS / Linux
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   Create a `.env` file in the project root (use `.env.example` as a template):

   ```env
   GROQ_API_KEY=your_groq_api_key
   FOURSQUARE_API_KEY=your_foursquare_api_key
   LOCATIONIQ_API_KEY=your_locationiq_api_key
   OPENWEATHER_API_KEY=your_openweather_api_key
   TAVILY_API_KEY=your_tavily_api_key
   EXCHANGERATE_API_KEY=your_exchangerate_api_key
   ```

---

## Running Locally

**Start the FastAPI backend:**

```bash
uvicorn main:app --reload --port 8000
```

**Start the Streamlit frontend** (in a separate terminal):

```bash
streamlit run streamlit_app.py
```

The frontend will be available at `http://localhost:8501` and will communicate with the backend at `http://localhost:8000`.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check — confirms backend is running |
| `GET` | `/health` | Returns `{"status": "ok"}` |
| `POST` | `/query` | Main endpoint — accepts `{"question": "..."}` and returns structured travel plan |

### Example Request

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Plan a 5-day trip to Gokarna"}'
```

### Example Response (abbreviated)

```json
{
  "intro": "...",
  "generic_plan": "...",
  "offbeat_plan": "...",
  "day_by_day": [{ "day": "Day 1", "text": "..." }],
  "weather": "...",
  "costs": { "Hotel": 5000, "Food": 2000, "Total": 10000 },
  "raw": "..."
}
```

---

## Configuration

Model and provider settings are managed in `config/config.yaml`:

```yaml
llm:
  groq:
    provider: groq
    model_name: llama-3.1-8b-instant
  openai:
    provider: openai
    model_name: o4-mini
```

To switch providers, change the `model_provider` argument passed to `GraphBuilder` in `main.py`.

---

## License

This project is licensed under the MIT License.
