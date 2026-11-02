"""Reusable client for text generation through Gemini's Interactions API."""

import logging

from google import genai

from iphone_guide_chatbot.config.settings import GEMINI_API_KEY, GEMINI_MODEL


logger = logging.getLogger(__name__)


class GeminiConfigurationError(ValueError):
    """Raised when required Gemini configuration is missing."""


class GeminiGenerationError(RuntimeError):
    """Raised when Gemini fails to return generated text."""


class GeminiClient:
    """A reusable Gemini client; create one instance and reuse it for requests."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        configured_api_key = GEMINI_API_KEY if api_key is None else api_key
        self.model = model or GEMINI_MODEL

        if not configured_api_key or not configured_api_key.strip():
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is missing. Set it in the project .env file or environment."
            )

        # Construct once per GeminiClient instance and reuse for every request.
        self._client = genai.Client(api_key=configured_api_key)

    def generate_text(self, text: str) -> str:
        """Send text to Gemini and return its generated text."""
        try:
            interaction = self._client.interactions.create(
                model=self.model,
                input=text,
            )
        except Exception as error:
            logger.error("Gemini Interactions API request failed (%s)", type(error).__name__)
            raise GeminiGenerationError("Gemini text generation failed.") from error

        output_text = interaction.output_text
        if not isinstance(output_text, str) or not output_text:
            logger.error("Gemini Interactions API returned no text output.")
            raise GeminiGenerationError("Gemini returned no text output.")
        return output_text
