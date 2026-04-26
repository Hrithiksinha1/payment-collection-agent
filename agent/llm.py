import os
from dotenv import load_dotenv
from openai import OpenAI


# --- Load environment variables ---
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# --- Custom Exception ---
class LLMError(Exception):
    """Raised when LLM call fails."""
    pass


# --- LLM Call Function ---
def call_llm(system: str, messages: list) -> str:
    """
    Calls OpenAI GPT-4o model.

    Args:
        system (str): System prompt
        messages (list): Conversation history [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        str: Assistant response text

    Raises:
        LLMError: If API call fails
    """

    if not OPENAI_API_KEY:
        raise LLMError("LLM service is not configured. Please try again later.")

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system},
                *messages
            ],
        )

        return response.choices[0].message.content.strip()

    except Exception:
        raise LLMError("I'm having trouble responding right now. Please try again.")