import os
import json
import logging
from typing import TypeVar, Type, Optional

import litellm
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


from app.config import settings

class AsyncLLMClient:
    def __init__(self, default_model: Optional[str] = None):
        self.default_model = default_model or settings.default_model
        if not self.default_model:
            raise ValueError(
                "No model configured. Set DEFAULT_MODEL in your environment (e.g. "
                "anthropic/claude-sonnet-5 or gemini/gemini-3-flash) — verify the exact "
                "current string against the provider's LiteLLM docs before trusting either "
                "example."
            )
        litellm.drop_params = True

    def _prepare_model(self, model: Optional[str] = None) -> str:
        target_model = model or self.default_model
        if target_model.startswith("gemini") and not target_model.startswith("gemini/"):
            target_model = f"gemini/{target_model}"
        return target_model

    async def extract_structured(
        self, prompt: str, schema: Type[T], model: Optional[str] = None, max_retries: int = 1
    ) -> T:
        target_model = self._prepare_model(model)
        schema_json = schema.model_json_schema()

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict data extraction AI. Extract the requested information "
                    "into a JSON object that exactly matches the given schema. Return ONLY "
                    "valid JSON — no markdown formatting, no explanations."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            content = None
            try:
                response = await litellm.acompletion(
                    model=target_model,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": schema.__name__, "schema": schema_json},
                    },
                )
                content = response.choices[0].message.content
                if content.startswith("```"):
                    content = content.strip("`").removeprefix("json").strip()
                return schema.model_validate_json(content)

            except (ValidationError, json.JSONDecodeError) as e:
                last_error = e
                logger.warning(f"Extraction validation failed (attempt {attempt + 1}): {e}")
                # Feed the actual error back rather than blindly repeating the same call —
                # num_retries on the raw API call retries identical input; this retries with
                # a correction.
                if content is not None:
                    messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": f"That response failed validation with this error:\n{e}\nReturn corrected JSON only.",
                })
            except Exception as e:
                # Not a validation problem (network/API/rate-limit) — a "fix your JSON"
                # follow-up wouldn't help, so don't burn a retry on it.
                logger.error(f"LLM call failed (attempt {attempt + 1}): {e}")
                last_error = e
                break

        raise last_error or RuntimeError("Structured extraction failed with no captured error")

    async def generate_response(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        model: Optional[str] = None,
    ) -> str:
        target_model = self._prepare_model(model)
        try:
            response = await litellm.acompletion(
                model=target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise
