"""
AquaGuard Agentic AI — ReAct-style agent with tool calling.

Uses Groq (free tier) by default — fast inference, generous free limits.
Configure via .env:
    GROQ_API_KEY=...        <- get free key at console.groq.com
    GROQ_MODEL=...          (optional, default: llama-3.3-70b-versatile)

Fallback to Gemini if GROQ_API_KEY not set:
    GEMINI_API_KEY=...      <- get free key at aistudio.google.com/apikey
    GEMINI_MODEL=...        (optional, default: gemini-1.5-flash)
"""

import json
import os
from openai import OpenAI
from agents.agent_tools import TOOLS, execute_tool
from utils.config_loader import get_config
from utils.logger import get_logger

logger = get_logger(__name__)


def _build_client():
    """Returns (client, model_name) — prefers Groq, falls back to Gemini.
    Returns (None, None) when no key is configured instead of raising.
    """
    cfg        = get_config()["agent"]
    groq_key   = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if groq_key and groq_key != "your_groq_api_key_here":
        model = os.getenv("GROQ_MODEL", cfg["default_groq_model"])
        return OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1"), model

    if gemini_key and gemini_key != "your_gemini_key_here":
        model = os.getenv("GEMINI_MODEL", cfg["default_gemini_model"])
        return OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        ), model

    logger.warning("[Agent] No LLM API key found — agent will return setup instructions.")
    return None, None


def _system_prompt() -> str:
    return """You are OceanSense, an expert ocean health AI.
Answer ocean questions: pollution, species, climate, fishing, tides, etc.
Detect query language (English/Hindi/Marathi) and respond in same.

Sequence for location queries:
1. geocode_location (if name given)
2. fetch_environment_data
3. run_ml_predictions
4. assess_species_impact

Structure responses:
Location → Environment → Risk → Species → Summary.
Cite satellite values: SST > 28.5°C = risk, Chl > 4 mg/m3 = bloom."""


class OceanAgent:
    """
    Agentic AI that autonomously calls ocean monitoring tools
    to answer natural language queries.
    """

    def __init__(self):
        self.client, self.model = _build_client()
        self.max_iterations = get_config()["agent"]["max_iterations"]
        if self.client:
            logger.info(f"[Agent] Using model: {self.model}")
        else:
            logger.warning("[Agent] No API key — running in no-key mode")

    def _no_key_message(self) -> str:
        return (
            "**AI Agent not configured.**\n\n"
            "To enable the AI Agent, add an API key to your `.env` file:\n\n"
            "**Option 1 — Groq (free, fast):**\n"
            "1. Go to https://console.groq.com and sign up\n"
            "2. Create an API key\n"
            "3. Add `GROQ_API_KEY=your_key_here` to your `.env` file\n"
            "4. Restart the backend (`./start_backend.ps1`)\n\n"
            "**Option 2 — Gemini (free):**\n"
            "1. Go to https://aistudio.google.com/apikey\n"
            "2. Create an API key\n"
            "3. Add `GEMINI_API_KEY=your_key_here` to your `.env` file\n"
            "4. Restart the backend"
        )

    def run(self, query: str, verbose: bool = False) -> str:
        """
        Run the agent on a user query.
        Returns the final natural language answer.
        """
        if self.client is None:
            return self._no_key_message()

        messages = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": query}
        ]

        logger.info(f"[Agent] Query: {query}")

        for iteration in range(self.max_iterations):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=[{"type": "function", "function": t} for t in TOOLS],
                    tool_choice="auto"
                )
            except Exception as api_err:
                err_str = str(api_err)
                logger.error(f"[Agent] API error on iteration {iteration}: {err_str}")
                # Retry without tools on tool_use_failed errors
                if "tool_use_failed" in err_str or "400" in err_str:
                    try:
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=messages,
                        )
                        return response.choices[0].message.content or "Unable to process request."
                    except Exception:
                        pass
                return f"I encountered an API error: {err_str[:200]}. Please try again."

            message = response.choices[0].message

            # No more tool calls → final answer
            if not message.tool_calls:
                answer = message.content or ""
                logger.info(f"[Agent] Final answer after {iteration + 1} iterations")
                return answer

            # Append assistant message with tool calls
            messages.append(message)

            # Execute each tool call and append results
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                if verbose:
                    print(f"\n→ Calling tool: {fn_name}")
                    print(f"  Args: {json.dumps(fn_args, indent=2)}")

                result = execute_tool(fn_name, fn_args)

                if verbose:
                    print(f"  Result: {json.dumps(result, indent=2, default=str)}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str)
                })

        logger.warning("[Agent] Reached max iterations without final answer")
        return "I reached the maximum number of reasoning steps. Please try a more specific query."
