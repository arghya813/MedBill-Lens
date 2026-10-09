"""Real AI provider built on any OpenAI-compatible chat-completions API.

Works out of the box with OpenAI, and with self-hosted or third-party
OpenAI-compatible gateways (vLLM, Ollama's OpenAI shim, Together, Groq,
LM Studio, OpenRouter, ...) by setting ``AI_BASE_URL``.

The provider is responsible only for language work: extraction,
categorization, explanations, questions and summaries. It is explicitly
instructed never to compute or invent benchmark figures, and the response
schema keeps it from doing so.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from datetime import date
from typing import Any

import httpx

from app.core.config import Settings, settings
from app.core.enums import (
    ADDITIVE_CATEGORIES,
    CREDIT_CATEGORIES,
    ChargeCategory,
    SAFE_DISCLAIMER,
)
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.providers.base import (
    AIProvider,
    Categorization,
    DocumentInput,
    ExplanationContext,
    ExtractedBill,
    ExtractedItem,
    ProviderCapabilities,
    ProviderStatus,
    SummaryContext,
    sanitize_items,
)
from app.providers.deterministic_parser import parse_bill_text
from app.services.categorization import categorize, service_name_for
from app.utils.text import guard_language, truncate_words

logger = get_logger(__name__)

MAX_IMAGE_BYTES = 4 * 1024 * 1024

#: Characters of extracted document text sent in an extraction prompt. Bills
#: longer than this are truncated with an explicit marker rather than silently.
MAX_PROMPT_TEXT_CHARS = 60_000

#: Only these MIME types may be sent to a vision endpoint as inline images.
_IMAGE_MIME_TYPES = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/webp": "image/webp",
    "image/gif": "image/gif",
}


def _data_url(content_type: str, payload: bytes) -> str:
    """Build an inline image data URL with the correct MIME type.

    Hard-coding ``data:image/png`` made JPEG uploads and any non-image payload
    (a PDF, for instance) fail at the provider.
    """
    mime = _IMAGE_MIME_TYPES.get(content_type.split(";")[0].strip().lower(), "image/png")
    return f"data:{mime};base64," + base64.b64encode(payload).decode("ascii")

CATEGORIES_HELP = ", ".join(sorted(ADDITIVE_CATEGORIES | CREDIT_CATEGORIES | {"tax", "package"}))

EXTRACTION_SYSTEM_PROMPT = f"""You extract structured data from hospital bills.

Return ONLY a JSON object with this exact shape:

{{
  "hospital_name": string|null,
  "hospital_location": string|null,
  "city": string|null,
  "patient_name": string|null,
  "patient_id": string|null,
  "bill_number": string|null,
  "bill_date": "YYYY-MM-DD"|null,
  "admission_date": "YYYY-MM-DD"|null,
  "discharge_date": "YYYY-MM-DD"|null,
  "room_category": string|null,
  "length_of_stay_days": integer|null,
  "diagnosis": string|null,
  "stated_grand_total": number|null,
  "items": [
    {{
      "description": "the charge description exactly as printed",
      "category": one of [{CATEGORIES_HELP}],
      "service_name": "short canonical name of the service, or null",
      "quantity": number,
      "unit_price": number,
      "total_price": number,
      "confidence": number between 0 and 1
    }}
  ]
}}

Rules:
- One entry per chargeable line item. Do not merge different charges.
- "category" must be one of the listed values. Use "miscellaneous" if unsure.
- "confidence" reflects how certain you are about the description, category and
  amount. Use a low value (below 0.6) when the text is ambiguous.
- Never invent a line item, amount or date that is not present in the document.
- Do not include taxes, discounts or insurance deductions as separate items
  unless they appear as their own rows on the bill.
- Do not add any commentary. Output JSON only.
"""

CATEGORIZE_SYSTEM_PROMPT = f"""You classify a single hospital charge into one category.

Allowed categories: {CATEGORIES_HELP}

Return ONLY JSON: {{"category": "...", "service_name": string|null, "confidence": 0-1, "reason": "short phrase"}}
"""

EXPLAIN_SYSTEM_PROMPT = f"""You help a patient understand a hospital bill comparison.

You will be given a charge and a benchmark range that was calculated by a
deterministic engine. Explain the comparison in plain, calm language.

Hard rules:
- Never describe a charge as fraud, a scam, cheating, illegal, unlawful, or
  malpractice. Never accuse anyone of wrongdoing.
- Never claim the bill is wrong. Say only that the charge is above the available
  benchmark and may be worth an itemised explanation.
- Every reason you give for a difference must be phrased as a possibility
  ("may", "could", "possible factors include"), never as a fact.
- Do not invent new numbers. Use only the figures supplied to you.
- Do not give medical, legal or financial advice.
- 2 to 4 short sentences. No headings, no bullet points, no markdown.
"""

QUESTIONS_SYSTEM_PROMPT = """You write questions a patient can ask a hospital billing department.

Hard rules:
- Informational, respectful and neutral in tone. Never accusatory.
- Never accuse the hospital of fraud, overcharging illegally, or any wrongdoing.
- Questions must ask for clarification, itemisation, quantities, or the basis of
  a charge. Never demand money or threaten escalation.
- 4 to 6 questions, one per line, no numbering, no markdown.
"""

SUMMARY_SYSTEM_PROMPT = f"""You write a short plain-English summary of a hospital bill analysis.

Hard rules:
- Use only the figures supplied to you. Do not compute or invent numbers.
- Never say the bill is wrong, fraudulent, illegal, or that the hospital
  overcharged. Say the comparison indicates several charges may deserve review.
- State clearly that a benchmark comparison does not establish that a hospital
  made an incorrect or unlawful charge.
- 3 to 5 sentences, plain language, no markdown headings.

Context: {SAFE_DISCLAIMER}
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        return fence.group(1)
    return text


def _parse_json(text: str) -> dict[str, Any] | None:
    candidate = _strip_code_fence(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost JSON object in the response.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _to_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[₹,\s]|[Rr]s\.?", "", value).strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


class OpenAICompatibleProvider(AIProvider):
    """Chat-completions based provider with optional vision support."""

    name = "openai_compatible"
    is_real = True
    capabilities = ProviderCapabilities(
        supports_vision=True, supports_chat=True, supports_json_mode=True
    )

    def __init__(self, config: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.config = config or settings
        self._client = client
        self._owns_client = client is None

    # -- plumbing ------------------------------------------------------
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.ai_base_url.rstrip("/"),
                timeout=httpx.Timeout(self.config.ai_timeout_seconds),
                headers={
                    "Authorization": f"Bearer {self.config.ai_api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _chat(
        self,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        model: str | None = None,
        max_tokens: int = 2000,
    ) -> str:
        if not self.config.ai_api_key:
            raise ProviderError("No AI API key is configured.")

        payload: dict[str, Any] = {
            "model": model or self.config.ai_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        client = self._get_client()
        last_error: Exception | None = None
        for attempt in range(self.config.ai_max_retries + 1):
            try:
                response = await client.post("/chat/completions", json=payload)
                if response.status_code >= 400:
                    detail = response.text[:300]
                    raise ProviderError(
                        f"AI provider returned HTTP {response.status_code}: {detail}"
                    )
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise ProviderError("AI provider returned an empty response.")
                return (choices[0].get("message") or {}).get("content") or ""
            except ProviderError:
                raise
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_error = exc
                if attempt < self.config.ai_max_retries:
                    await asyncio.sleep(0.6 * (2**attempt))

        raise ProviderError(f"AI provider request failed: {type(last_error).__name__}")

    # -- extraction ----------------------------------------------------
    async def extract_bill(self, document: DocumentInput) -> ExtractedBill:
        text = document.text or ""
        if not text.strip() and document.image_bytes and len(document.image_bytes) <= MAX_IMAGE_BYTES:
            # No text layer and we have an image: use vision.
            return await self._extract_with_vision(document)

        if not text.strip():
            # No text layer and no usable image: the document cannot be read.
            logger.info("extraction_no_readable_text")
            return ExtractedBill(
                items=[],
                confidence=0.0,
                provider=self.name,
                method="unreadable",
                warnings=[
                    "The document has no readable text layer, so the AI provider could "
                    "not read it. Please upload a clearer scan or enter the charges manually."
                ],
            )

        excerpt = text[:MAX_PROMPT_TEXT_CHARS]
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Extract the bill data from the following document text.\n\n"
                    f"{excerpt}"
                    + (f"\n\n[truncated: {len(text)} characters total]" if len(text) > MAX_PROMPT_TEXT_CHARS else "")
                ),
            }
        ]
        if document.image_bytes and len(document.image_bytes) <= MAX_IMAGE_BYTES:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _data_url(
                            document.content_type or "image/png", document.image_bytes
                        )
                    },
                }
            )

        raw = await self._chat(
            [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            json_mode=True,
            model=self.config.ai_vision_model or self.config.ai_model,
            max_tokens=4000,
        )
        return self._bill_from_json(raw, fallback_text=text, used_vision=bool(document.image_bytes))

    async def _extract_with_vision(self, document: DocumentInput) -> ExtractedBill:
        model = self.config.ai_vision_model or self.config.ai_model
        url = _data_url(
            document.content_type or "image/png", document.image_bytes or b""
        )
        raw = await self._chat(
            [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract the bill data from this scanned hospital bill image.",
                        },
                        {"type": "image_url", "image_url": {"url": url}},
                    ],
                },
            ],
            json_mode=True,
            model=model,
            max_tokens=4000,
        )
        return self._bill_from_json(raw, fallback_text="", used_vision=True)

    def _bill_from_json(self, raw: str, *, fallback_text: str, used_vision: bool) -> ExtractedBill:
        payload = _parse_json(raw) or {}
        if not payload and fallback_text:
            # Model failed to return usable JSON: use the deterministic parser
            # so the user is never left with nothing.
            parsed = parse_bill_text(fallback_text)
            items = [
                ExtractedItem(
                    description=i.description,
                    category=categorize(i.description)[0],
                    quantity=i.quantity,
                    unit_price=i.unit_price,
                    total_price=i.total_price,
                    confidence=round(i.confidence * 0.7, 3),
                    service_name=service_name_for(i.description, categorize(i.description)[0]),
                )
                for i in parsed.items
            ]
            return ExtractedBill(
                items=items,
                confidence=parsed.confidence,
                provider=self.name,
                method="rules_fallback",
                warnings=parsed.warnings
                + ["The AI response could not be parsed; a rule-based read was used instead."],
                used_vision=used_vision,
            )

        raw_items = payload.get("items")
        items: list[ExtractedItem] = []
        if isinstance(raw_items, list):
            for clean in sanitize_items(raw_items):
                if clean["category"] not in {c.value for c in ChargeCategory}:
                    clean["category"] = categorize(clean["description"])[0]
                items.append(ExtractedItem(**clean))

        warnings: list[str] = []
        if not items:
            warnings.append(
                "The AI provider did not return any chargeable line items for this document."
            )

        los = payload.get("length_of_stay_days")
        return ExtractedBill(
            hospital_name=_clean_str(payload.get("hospital_name")),
            hospital_location=_clean_str(payload.get("hospital_location")),
            city=_clean_str(payload.get("city")),
            patient_name=_clean_str(payload.get("patient_name")),
            patient_id=_clean_str(payload.get("patient_id")),
            bill_number=_clean_str(payload.get("bill_number")),
            bill_date=_to_date(payload.get("bill_date")),
            admission_date=_to_date(payload.get("admission_date")),
            discharge_date=_to_date(payload.get("discharge_date")),
            room_category=_clean_str(payload.get("room_category")),
            length_of_stay_days=int(los) if isinstance(los, (int, float)) and los > 0 else None,
            diagnosis=_clean_str(payload.get("diagnosis")),
            items=items,
            stated_grand_total=_to_float(payload.get("stated_grand_total")),
            confidence=0.9 if items else 0.2,
            warnings=warnings,
            provider=self.name,
            method="ai_vision" if used_vision else "ai_text",
            used_vision=used_vision,
        )

    # -- categorization ------------------------------------------------
    async def classify_charge(
        self,
        description: str,
        *,
        category_hint: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Categorization:
        rule_category, rule_confidence, reason = categorize(description, hint=category_hint)
        try:
            raw = await self._chat(
                [
                    {"role": "system", "content": CATEGORIZE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Charge description: {description}\nContext: {json.dumps(context or {})}",
                    },
                ],
                json_mode=True,
                max_tokens=300,
            )
        except ProviderError:
            return Categorization(
                category=rule_category,
                confidence=rule_confidence,
                service_name=service_name_for(description, rule_category),
                reason=reason,
                source="rules_fallback",
            )

        payload = _parse_json(raw) or {}
        category = str(payload.get("category") or rule_category).lower().strip()
        if category not in {c.value for c in ChargeCategory}:
            return Categorization(
                category=rule_category,
                confidence=rule_confidence,
                service_name=service_name_for(description, rule_category),
                reason=reason,
                source="rules_fallback",
            )
        try:
            confidence = float(payload.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        return Categorization(
            category=category,
            confidence=min(1.0, max(0.0, confidence)),
            service_name=_clean_str(payload.get("service_name"))
            or service_name_for(description, category),
            reason=_clean_str(payload.get("reason")) or reason,
            source="ai",
        )

    # -- language ------------------------------------------------------
    async def explain_difference(self, context: ExplanationContext) -> str:
        payload = {
            "charge_description": context.description,
            "category": context.category,
            "quantity": context.quantity,
            "actual_amount": context.actual_amount,
            "benchmark_min": context.benchmark_min,
            "benchmark_median": context.benchmark_median,
            "benchmark_max": context.benchmark_max,
            "percentage_above_max": context.percentage_above_max,
            "percentage_difference": context.percentage_difference,
            "comparison_status": context.flag_label,
            "matched_benchmark_service": context.matched_service_name,
            "benchmark_source": context.source_name,
            "benchmark_dataset_label": context.dataset_label,
            "comparison_context": {
                "city": context.city,
                "hospital_category": context.hospital_category,
                "treatment": context.treatment,
                "room_category": context.room_category,
            },
        }
        try:
            raw = await self._chat(
                [
                    {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": "Explain this comparison to the patient.\n\n"
                        + json.dumps(payload, indent=2),
                    },
                ],
                max_tokens=400,
            )
        except ProviderError:
            from app.providers.demo import DemoAIProvider

            return await DemoAIProvider().explain_difference(context)

        cleaned, _ = guard_language(truncate_words(_clean_str(raw) or "", 170))
        if len(cleaned) < 40:
            from app.providers.demo import DemoAIProvider

            return await DemoAIProvider().explain_difference(context)
        return cleaned

    async def generate_questions(
        self, context: ExplanationContext, *, scope: str = "charge"
    ) -> list[str]:
        target = context.description if scope == "charge" else "the whole bill"
        try:
            raw = await self._chat(
                [
                    {"role": "system", "content": QUESTIONS_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Write questions about: {target} "
                            f"(category: {context.category}, amount: {context.actual_amount})."
                        ),
                    },
                ],
                max_tokens=400,
            )
        except ProviderError:
            from app.providers.demo import DemoAIProvider

            return await DemoAIProvider().generate_questions(context, scope=scope)

        questions: list[str] = []
        for line in raw.splitlines():
            line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            line = _clean_str(line)
            if not line or len(line) < 12:
                continue
            cleaned, _ = guard_language(line)
            if not cleaned.endswith("?"):
                cleaned = cleaned.rstrip(".") + "?"
            questions.append(cleaned)
        if not questions:
            from app.providers.demo import DemoAIProvider

            return await DemoAIProvider().generate_questions(context, scope=scope)
        return questions[:6]

    async def summarize_bill(self, context: SummaryContext) -> str:
        payload = {
            "hospital_name": context.hospital_name,
            "bill_total": context.bill_total,
            "benchmark_min_total": context.benchmark_min_total,
            "benchmark_max_total": context.benchmark_max_total,
            "difference_min": context.difference_min,
            "difference_max": context.difference_max,
            "charges_analyzed": context.items_analyzed,
            "charges_within_benchmark": context.items_within_range,
            "charges_above_benchmark": context.items_above_range,
            "charges_without_benchmark": context.items_insufficient_data,
            "largest_differences": [
                {"charge": name, "status": label, "percentage_above_benchmark": pct}
                for name, label, pct in context.top_flagged
            ],
            "benchmark_dataset_label": context.dataset_label,
            "comparison_context": {
                "city": context.city,
                "hospital_category": context.hospital_category,
                "treatment": context.treatment,
            },
        }
        try:
            raw = await self._chat(
                [
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, indent=2)},
                ],
                max_tokens=500,
            )
        except ProviderError:
            from app.providers.demo import DemoAIProvider

            return await DemoAIProvider().summarize_bill(context)

        cleaned, _ = guard_language(_clean_str(raw) or "")
        if len(cleaned) < 60:
            from app.providers.demo import DemoAIProvider

            return await DemoAIProvider().summarize_bill(context)
        return cleaned

    async def health(self) -> ProviderStatus:
        if not self.config.ai_api_key:
            return ProviderStatus(
                name=self.name,
                is_real=True,
                ready=False,
                detail="AI_API_KEY is not set. MedBill Lens is running in demo mode.",
            )
        try:
            await self._chat(
                [{"role": "user", "content": "ping"}], max_tokens=5
            )
        except ProviderError as exc:
            return ProviderStatus(
                name=self.name, is_real=True, ready=False, detail=str(exc)[:200]
            )
        return ProviderStatus(
            name=self.name,
            is_real=True,
            ready=True,
            detail=f"Model {self.config.ai_model} via {self.config.ai_base_url}",
        )

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None


def _clean_str(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None
