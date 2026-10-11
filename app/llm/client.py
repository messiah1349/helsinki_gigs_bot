import os
import logging
from typing import Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

async def call_gemini(
    prompt: str,
    system_instruction: Optional[str] = None,
    json_response: bool = True,
    temperature: float = 0.2,
    model_name: Optional[str] = None
) -> str:
    """
    Direct asynchronous REST call to Google Gemini Flash API using httpx.
    Completely eliminates LangChain, gRPC, and protobuf memory footprint (~40MB saved).
    """
    api_key = settings.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    model = model_name or settings.LLM_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": temperature
        }
    }

    if system_instruction:
        body["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    if json_response:
        body["generationConfig"]["response_mime_type"] = "application/json"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"No response candidate returned from Gemini: {data}")
        return candidates[0]["content"]["parts"][0]["text"]
