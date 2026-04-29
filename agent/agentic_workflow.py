
from utils.model_loader import ModelLoader
from utils.config_loader import load_config
from prompt_library.prompt import SYSTEM_PROMPT
from utils.vector_store import VectorStore
from utils.rag_store import RAGStore
from utils.user_profiles import UserProfileStore
from utils.feedback_store import FeedbackStore
from typing import Dict, Any
from langgraph.graph import StateGraph, MessagesState, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from tools.weather_info_tool import WeatherInfoTool
from tools.place_search_tool import PlaceSearchTool
from tools.expense_calculator_tool import CalculatorTool
from tools.currency_conversion_tool import CurrencyConverterTool
import time


class SimpleTTLCache:
    def __init__(self, ttl_seconds: int = 300, max_size: int = 500):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
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
        if len(self._store) >= self.max_size:
            # Basic eviction
            oldest_key = next(iter(self._store))
            self._store.pop(oldest_key)
        self._store[key] = (value, time.time())


class GraphBuilder():
    def __init__(self,model_provider: str = "groq"):
        self.config = load_config()
        perf = self.config.get("performance", {})
        self.rag_k = int(perf.get("rag_k", 2))
        self.memory_k = int(perf.get("memory_k", 2))
        self.context_truncate = int(perf.get("context_truncate", 600))

        self.model_loader = ModelLoader(model_provider=model_provider)
        self.llm = self.model_loader.load_llm()
        
        self.tools = []
        
        self.weather_tools = WeatherInfoTool()
        self.place_search_tools = PlaceSearchTool()
        self.calculator_tools = CalculatorTool()
        self.currency_converter_tools = CurrencyConverterTool()
        
        self.tools.extend([* self.weather_tools.weather_tool_list, 
                           * self.place_search_tools.place_search_tool_list,
                           * self.calculator_tools.calculator_tool_list,
                           * self.currency_converter_tools.currency_converter_tool_list])
        
        self.llm_with_tools = self.llm.bind_tools(tools=self.tools)
        
        self.graph = None
        
        self.system_prompt = SYSTEM_PROMPT
        self.vector_store = VectorStore()
        self.rag_store = RAGStore()
        self.profile_store = UserProfileStore()
        self.feedback_store = FeedbackStore()
    
    
    def agent_function(self,state: MessagesState):
        """Main agent function"""
        def _truncate(text: str, limit: int = 1200) -> str:
            if not text:
                return ""
            return text[:limit]

        user_question = state["messages"]
        user_id = "anonymous"
        if isinstance(state, dict):
            user_id = state.get("user_id") or user_id

        last_message = ""
        if user_question:
            last = user_question[-1]
            if hasattr(last, "content"):
                last_message = last.content
            else:
                last_message = str(last)

        past_trips = []
        try:
            past_trips = self.vector_store.get_similar_trips(last_message, k=self.memory_k)
        except Exception:
            past_trips = []

        knowledge_docs = []
        try:
            knowledge_docs = self.rag_store.search(last_message, k=self.rag_k)
        except Exception:
            knowledge_docs = []

        memory_context = ""
        if past_trips:
            memory_context = _truncate("\n\n".join([doc.page_content for doc in past_trips]), self.context_truncate)

        knowledge_context = ""
        if knowledge_docs:
            knowledge_context = _truncate("\n\n".join([doc.page_content for doc in knowledge_docs]), self.context_truncate)

        profile = self.profile_store.get_profile(user_id)
        preferred = profile.get("preferred_places", [])
        profile_context = (
            "User Preferences (must reflect these in the itinerary):\n"
            f"- Budget: {profile.get('budget_range','mid')}\n"
            f"- Style: {profile.get('travel_style','backpacking')}\n"
            f"- Preferred places/interests: {preferred}\n"
            f"- Food: {profile.get('food_preference','veg')}\n"
            "Ensure the plan explicitly includes at least 2 items that match the preferred places/interests."
        )

        feedback_context = ""
        try:
            feedback_entries = self.feedback_store._load()
            recent_feedback = [f for f in feedback_entries if f.get("user_id") == user_id][-3:]
            if recent_feedback:
                feedback_context = _truncate("\n".join(
                    [f"- {f.get('feedback','')} (rating: {f.get('rating','')})" for f in recent_feedback]
                ), self.context_truncate)
        except Exception:
            feedback_context = ""

        extra_context = []
        if memory_context:
            extra_context.append(f"User Past Trips:\n{memory_context}")
        if profile_context:
            extra_context.append(profile_context)
        if knowledge_context:
            extra_context.append(f"Knowledge Base Context:\n{knowledge_context}")
        if feedback_context:
            extra_context.append(f"Feedback Context:\n{feedback_context}")

        input_question = [self.system_prompt]
        for ctx in extra_context:
            input_question.append(ctx)
        if state.get("minimal_mode", False):
            input_question.append("Return a minimal plan: day-by-day itinerary + 1-2 hotel options + total budget summary. Keep it short.")
        input_question.extend(user_question)
        response = self.llm_with_tools.invoke(input_question)
        return {"messages": [response]}
    def build_graph(self):
        graph_builder=StateGraph(MessagesState)
        graph_builder.add_node("agent", self.agent_function)
        graph_builder.add_node("tools", ToolNode(tools=self.tools))
        graph_builder.add_edge(START,"agent")
        graph_builder.add_conditional_edges("agent",tools_condition)
        graph_builder.add_edge("tools","agent")
        graph_builder.add_edge("agent",END)
        self.graph = graph_builder.compile()
        return self.graph
        
    def __call__(self):
        return self.build_graph()


class MultiAgentGraphBuilder():
    def __init__(self, model_provider: str = "groq"):
        self.config = load_config()
        perf = self.config.get("performance", {})
        self.rag_k = int(perf.get("rag_k", 2))
        self.memory_k = int(perf.get("memory_k", 2))
        self.context_truncate = int(perf.get("context_truncate", 600))
        self.cache_ttl = int(perf.get("response_cache_ttl_seconds", 300))
        self.rag_cache = SimpleTTLCache(self.cache_ttl)

        self.model_loader = ModelLoader(model_provider=model_provider)
        self.llm = self.model_loader.load_llm()

        self.tools = []

        self.weather_tools = WeatherInfoTool()
        self.place_search_tools = PlaceSearchTool()
        self.calculator_tools = CalculatorTool()
        self.currency_converter_tools = CurrencyConverterTool()

        self.tools.extend([* self.weather_tools.weather_tool_list,
                           * self.place_search_tools.place_search_tool_list,
                           * self.calculator_tools.calculator_tool_list,
                           * self.currency_converter_tools.currency_converter_tool_list])

        self.llm_with_tools = self.llm.bind_tools(tools=self.tools)

        self.system_prompt = SYSTEM_PROMPT
        self.vector_store = VectorStore()
        self.rag_store = RAGStore()
        self.profile_store = UserProfileStore()
        self.feedback_store = FeedbackStore()

        self.graph = None

    def _build_context(self, state: Dict[str, Any]) -> Dict[str, str]:
        def _truncate(text: str, limit: int = 1200) -> str:
            if not text:
                return ""
            return text[:limit]

        user_question = state["messages"]
        user_id = state.get("user_id", "anonymous")
        fast_mode = state.get("fast_mode", True)
        instant_mode = state.get("instant_mode", False)
        minimal_mode = state.get("minimal_mode", False)

        last_message = ""
        if user_question:
            last = user_question[-1]
            if hasattr(last, "content"):
                last_message = last.content
            else:
                last_message = str(last)

        past_trips = []
        knowledge_docs = []
        if not last_message:
            past_trips = []
            knowledge_docs = []
        else:
            try:
                past_trips = self.vector_store.get_similar_trips(last_message, k=self.memory_k)
            except Exception:
                past_trips = []

            if fast_mode:
                knowledge_docs = []
            else:
                cache_key = f"rag::{last_message.strip().lower()}::{self.rag_k}"
                cached = self.rag_cache.get(cache_key)
                if cached is not None:
                    knowledge_docs = cached
                else:
                    try:
                        knowledge_docs = self.rag_store.search(last_message, k=self.rag_k)
                    except Exception:
                        knowledge_docs = []
                    self.rag_cache.set(cache_key, knowledge_docs)

        # Context Compression: Use top N chunks instead of blind truncation
        if instant_mode:
            past_trips = []
            knowledge_docs = []
        elif fast_mode:
            past_trips = past_trips[:1]  # Top 1 memory
            knowledge_docs = []          # Skip RAG
        else:
            past_trips = past_trips[:2]
            knowledge_docs = knowledge_docs[:1] # Top 1 RAG

        memory_context = ""
        if past_trips:
            memory_context = "\n\n".join([doc.page_content for doc in past_trips])

        knowledge_context = ""
        if knowledge_docs:
            knowledge_context = "\n\n".join([doc.page_content for doc in knowledge_docs])

        profile = self.profile_store.get_profile(user_id)
        preferred = profile.get("preferred_places", [])
        profile_context = (
            "User Preferences (must reflect these in the itinerary):\n"
            f"- Budget: {profile.get('budget_range','mid')}\n"
            f"- Style: {profile.get('travel_style','backpacking')}\n"
            f"- Preferred places/interests: {preferred}\n"
            f"- Food: {profile.get('food_preference','veg')}\n"
            "Ensure the plan explicitly includes at least 2 items that match the preferred places/interests."
        )

        feedback_context = ""
        if not fast_mode and not instant_mode:
            try:
                feedback_entries = self.feedback_store._load()
                recent_feedback = [f for f in feedback_entries if f.get("user_id") == user_id][-3:]
                if recent_feedback:
                    feedback_context = _truncate("\n".join(
                        [f"- {f.get('feedback','')} (rating: {f.get('rating','')})" for f in recent_feedback]
                    ), self.context_truncate)
            except Exception:
                feedback_context = ""

        return {
            "memory": memory_context,
            "knowledge": knowledge_context,
            "profile": profile_context,
            "feedback": feedback_context,
            "minimal": "1" if minimal_mode else "0",
        }

    def planner_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        context = self._build_context(state)
        messages = state["messages"]
        input_question = [self.system_prompt]
        if context.get("memory"):
            input_question.append(f"User Past Trips:\n{context['memory']}")
        if context.get("profile"):
            input_question.append(context["profile"])
        if context.get("knowledge"):
            input_question.append(f"Knowledge Base Context:\n{context['knowledge']}")
        if context.get("feedback"):
            input_question.append(f"Feedback Context:\n{context['feedback']}")
        if context.get("minimal") == "1":
            input_question.append("Return a minimal plan: day-by-day itinerary + 1-2 hotel options + total budget summary. Keep it short.")
        if state.get("instant_mode", False):
            input_question.append("Do not call external tools. Use only provided context and general knowledge.")
        input_question.append("Keep the response concise and avoid repetition.")
        input_question.extend(messages)
        response = self.llm_with_tools.invoke(input_question)
        return {"messages": [response]}

    def refiner_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if state.get("fast_mode", True) or state.get("instant_mode", False):
            return state
        messages = state["messages"]
        refiner_prompt = (
            "You are a local expert and budget optimizer."
            " Add hidden gems, authentic experiences, and refine costs to match the user's budget."
            " Keep the output concise and structured."
        )
        input_question = [self.system_prompt, refiner_prompt]
        input_question.extend(messages)
        response = self.llm_with_tools.invoke(input_question)
        return {"messages": [response]}

    def build_graph(self):
        graph_builder = StateGraph(MessagesState)
        graph_builder.add_node("planner", self.planner_agent)
        graph_builder.add_node("refiner", self.refiner_agent)
        graph_builder.add_node("tools", ToolNode(tools=self.tools))

        graph_builder.add_edge(START, "planner")
        graph_builder.add_conditional_edges("planner", tools_condition)
        graph_builder.add_edge("tools", "planner")
        graph_builder.add_edge("planner", "refiner")
        graph_builder.add_edge("refiner", END)

        self.graph = graph_builder.compile()
        return self.graph

    def __call__(self):
        return self.build_graph()
