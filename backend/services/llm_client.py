"""LLM clients for structured extraction and semantic validation.

Supports:
- GroqClient: Groq API with Llama models (for document extraction)
- OpenAIClient: OpenAI API with GPT models (for multi-agent system)
- GeminiClient: Google Gemini API (for planner agent)
"""

import json
import time
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, ValidationError
import structlog
from groq import Groq
from openai import OpenAI
from google import genai

from backend.core.config import settings

logger = structlog.get_logger()


class GroqClient:
    """Centralized Groq API wrapper with retry logic and structured outputs."""

    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = settings.groq_model
        self.max_retries = settings.groq_max_retries

    def extract_json(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = None,
    ) -> Dict[str, Any]:
        """
        Extract structured JSON from LLM using JSON mode.

        Args:
            prompt: The extraction prompt
            schema: Optional Pydantic model for validation
            temperature: Override default extraction temperature

        Returns:
            Parsed JSON dictionary

        Raises:
            ValueError: If extraction fails after retries
            ValidationError: If schema validation fails
        """
        if temperature is None:
            temperature = settings.groq_extraction_temperature

        last_error = None

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "groq_extraction_attempt",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a financial document extraction AI. Return ONLY valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )

                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from LLM")

                # Parse JSON
                result = json.loads(content)

                # Validate against schema if provided
                if schema:
                    validated = schema(**result)
                    result = validated.model_dump()

                logger.info(
                    "groq_extraction_success",
                    attempt=attempt + 1,
                    keys=list(result.keys()),
                )
                return result

            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                last_error = e
                logger.warning(
                    "groq_extraction_failed",
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                # Exponential backoff
                if attempt < self.max_retries - 1:
                    sleep_time = 2 ** attempt
                    logger.info("retrying_after_delay", seconds=sleep_time)
                    time.sleep(sleep_time)

        # All retries exhausted
        raise ValueError(
            f"Failed to extract JSON after {self.max_retries} attempts: {last_error}"
        )

    def validate_semantic(
        self, field: str, value: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use LLM to validate semantic correctness of a field.

        Args:
            field: Field name being validated (e.g., "cost_code")
            value: Field value (e.g., "05-500")
            context: Additional context (e.g., {"description": "Concrete Pour"})

        Returns:
            {
                "valid": bool,
                "confidence": float,
                "reason": str
            }
        """
        prompt = f"""Validate if this field value makes semantic sense given the context.

FIELD: {field}
VALUE: {value}
CONTEXT: {json.dumps(context, indent=2)}

Analyze if the value is semantically correct for this field given the context.
For example, cost code "05-500" (Structural Steel) should NOT match description "Concrete Pour".

Return JSON:
{{
  "valid": true/false,
  "confidence": 0.0-1.0,
  "reason": "explanation of why valid or invalid"
}}
"""

        try:
            result = self.extract_json(
                prompt=prompt, temperature=settings.groq_validation_temperature
            )

            # Ensure required fields
            if "valid" not in result or "confidence" not in result:
                logger.warning("semantic_validation_missing_fields", result=result)
                return {
                    "valid": True,  # Default to valid if uncertain
                    "confidence": 0.5,
                    "reason": "Validation incomplete",
                }

            return result

        except Exception as e:
            logger.error("semantic_validation_error", error=str(e))
            # Default to valid on error to avoid blocking pipeline
            return {
                "valid": True,
                "confidence": 0.5,
                "reason": f"Validation error: {str(e)}",
            }


class OpenAIClient:
    """OpenAI API wrapper for multi-agent conversational system."""

    def __init__(self, model: Optional[str] = None):
        """
        Initialize OpenAI client.

        Args:
            model: Model to use (default: gpt-4o-mini from settings)
        """
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = model or settings.openai_chat_model
        self.max_retries = 3

    def extract_json(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = None,
    ) -> Dict[str, Any]:
        """
        Extract structured JSON from LLM using JSON mode.

        Args:
            prompt: The extraction prompt
            schema: Optional Pydantic model for validation
            temperature: Temperature for generation (default: 0.7)

        Returns:
            Parsed JSON dictionary

        Raises:
            ValueError: If extraction fails after retries
            ValidationError: If schema validation fails
        """
        if temperature is None:
            temperature = 0.7

        last_error = None

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "openai_extraction_attempt",
                    attempt=attempt + 1,
                    model=self.model,
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful AI assistant. Return ONLY valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )

                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from LLM")

                # Parse JSON
                result = json.loads(content)

                # Validate against schema if provided
                if schema:
                    validated = schema(**result)
                    result = validated.model_dump()

                logger.info(
                    "openai_extraction_success",
                    attempt=attempt + 1,
                    keys=list(result.keys()),
                )
                return result

            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                last_error = e
                logger.warning(
                    "openai_extraction_failed",
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                # Exponential backoff
                if attempt < self.max_retries - 1:
                    sleep_time = 2 ** attempt
                    logger.info("retrying_after_delay", seconds=sleep_time)
                    time.sleep(sleep_time)

        # All retries exhausted
        raise ValueError(
            f"Failed to extract JSON after {self.max_retries} attempts: {last_error}"
        )


class GeminiClient:
    """Google Gemini API wrapper for planner agent."""

    def __init__(self, model: Optional[str] = None):
        """
        Initialize Gemini client.

        Args:
            model: Model to use (default: gemini-2.5-pro from settings)
        """
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = model or settings.gemini_model
        self.max_retries = 3

    def extract_json(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = None,
    ) -> Dict[str, Any]:
        """
        Extract structured JSON from LLM using JSON mode.

        Args:
            prompt: The extraction prompt
            schema: Optional Pydantic model for validation
            temperature: Temperature for generation (default: 0.7)

        Returns:
            Parsed JSON dictionary

        Raises:
            ValueError: If extraction fails after retries
            ValidationError: If schema validation fails
        """
        if temperature is None:
            temperature = 0.7

        last_error = None

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "gemini_extraction_attempt",
                    attempt=attempt + 1,
                    model=self.model,
                )

                # Create generation config with JSON mode
                config = genai.types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                )

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )

                content = response.text
                if not content:
                    raise ValueError("Empty response from LLM")

                # Parse JSON
                result = json.loads(content)

                # Validate against schema if provided
                if schema:
                    validated = schema(**result)
                    result = validated.model_dump()

                logger.info(
                    "gemini_extraction_success",
                    attempt=attempt + 1,
                    keys=list(result.keys()),
                )
                return result

            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                last_error = e
                logger.warning(
                    "gemini_extraction_failed",
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                # Exponential backoff
                if attempt < self.max_retries - 1:
                    sleep_time = 2 ** attempt
                    logger.info("retrying_after_delay", seconds=sleep_time)
                    time.sleep(sleep_time)

        # All retries exhausted
        raise ValueError(
            f"Failed to extract JSON after {self.max_retries} attempts: {last_error}"
        )
