"""OpenAI-compatible AI Failure Diagnosis provider via Vercel AI Gateway (Gemini LLM)."""

import json
from typing import Any

import httpx
from openclass_core.evidence import DiagnosisCategory, DiagnosisResult
from openclass_core.providers import ProviderError
from pydantic import SecretStr, ValidationError


class OpenAICompatibleDiagnosisProvider:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str = "https://ai-gateway.vercel.sh/v1",
        model: str = "google/gemini-2.5-flash",
        timeout: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip() or not base_url.startswith("https://"):
            raise ValueError("Invalid Diagnosis Provider configuration")
        self.key = api_key
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout
        self.transport = transport

    async def diagnose(self, context: dict[str, Any]) -> DiagnosisResult:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "diagnosis": {
                    "type": "string",
                    "enum": [cat.value for cat in DiagnosisCategory],
                },
                "rationale": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "recommended_action": {"type": "string"},
            },
            "required": ["diagnosis", "rationale", "confidence", "recommended_action"],
        }
        if self.key.get_secret_value() in json.dumps(context):
            raise ProviderError("Diagnosis context contains configured credential")

        categories_str = ", ".join([cat.value for cat in DiagnosisCategory])
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an OpenClass Supervisor diagnosing an unhandled or "
                        "low-trust decision run. Analyze the observation, decision "
                        "service instructions, and choice distribution. "
                        "Categorize the gap using ONLY one of the formal taxonomy values: "
                        f"{categories_str}. "
                        "Never invent ground truth or use decision choice keys as categories. "
                        "Provide concise, actionable rationale."
                    ),
                },
                {"role": "user", "content": json.dumps(context)},
            ],
            "max_tokens": 2000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "diagnosis_result", "strict": True, "schema": schema},
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, trust_env=False, transport=self.transport
            ) as client:
                response = await client.post(
                    self.url,
                    headers={"Authorization": f"Bearer {self.key.get_secret_value()}"},
                    json=payload,
                )
                if response.status_code != 200:
                    raise ProviderError(f"Diagnosis provider HTTP error: {response.status_code}")
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                raw_diag = str(parsed["diagnosis"]).strip().lower()
                diag_enum = None
                for cat in DiagnosisCategory:
                    if cat.value.lower() == raw_diag:
                        diag_enum = cat
                        break
                if diag_enum is None:
                    raise ProviderError(f"Unknown diagnosis category: {raw_diag}")
                return DiagnosisResult(
                    diagnosis=diag_enum,
                    rationale=parsed["rationale"],
                    confidence=float(parsed["confidence"]),
                    recommended_action=parsed.get("recommended_action"),
                    provider="vercel-ai-gateway",
                    model=self.model,
                    simulated=False,
                )
        except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
            raise ProviderError(f"Diagnosis failed: {type(exc).__name__}") from exc
