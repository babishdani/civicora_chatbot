
from unittest.mock import patch
import chatbot


def test_openrouter_fallback():
    with (
        patch.object(
            chatbot, "call_groq",
            side_effect=RuntimeError("Groq quota exhausted")
        ),
        patch.object(
            chatbot, "call_gemini",
            side_effect=RuntimeError("Gemini quota exhausted")
        ),
        patch.object(
            chatbot, "call_openrouter",
            return_value="OpenRouter fallback successful"
        ),
    ):
        result = chatbot.call_llm_with_fallback("Hello")

        assert result == "OpenRouter fallback successful"
        print("\nPASS: OpenRouter fallback works!")


if __name__ == "__main__":
    test_openrouter_fallback()
