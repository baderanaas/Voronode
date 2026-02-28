"""Contract extraction agent - converts PDF to structured Contract model via Groq/Llama3."""

import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from decimal import Decimal, InvalidOperation
from backend.core.logging import get_logger
import pdfplumber
from pypdf import PdfReader

from backend.core.models import Contract
from backend.services.llm_client import GroqClient

logger = get_logger(__name__)


class ContractExtractor:
    """Extract structured contract data from PDF files using Groq/Llama3."""

    def __init__(self):
        self.llm_client = GroqClient()

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """
        Extract raw text from PDF (pdfplumber with pypdf fallback).

        This is only for converting PDF binary to plain text —
        all data extraction is handled by the LLM.
        """
        try:
            logger.debug("extracting_pdf_text", path=str(pdf_path), method="pdfplumber")
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

                if text.strip():
                    logger.debug("pdf_extraction_success", method="pdfplumber", text_length=len(text))
                    return text.strip()

        except Exception as e:
            logger.warning("pdfplumber_failed", error=str(e))

        try:
            logger.debug("extracting_pdf_text", path=str(pdf_path), method="pypdf")
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            if text.strip():
                logger.debug("pdf_extraction_success", method="pypdf", text_length=len(text))
                return text.strip()

        except Exception as e:
            logger.error("pypdf_failed", error=str(e))

        raise ValueError(f"Failed to extract text from PDF: {pdf_path}")

    def structure_contract(self, raw_text: str) -> dict:
        """
        Use Groq/Llama3 to extract structured contract data from raw text.

        Args:
            raw_text: Extracted PDF text

        Returns:
            Dictionary matching Contract schema
        """
        prompt = f"""You are a construction contract analysis AI. Extract structured contract terms from the PDF text below.

OUTPUT SCHEMA:
{{
  "contract_id": "CONTRACT-XXX",
  "contractor_id": "CONT-XXX or contractor identifier",
  "contractor_name": "Full company name",
  "project_id": "PRJ-XXX or project identifier",
  "project_name": "Full project name",
  "value": 250000.00,
  "retention_rate": 0.10,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "terms": "Summary of key contract terms",
  "unit_price_schedule": {{"cost_code": max_unit_price}},
  "approved_cost_codes": ["01-100", "05-500"]
}}

CRITICAL RULES:
1. ALL fields are REQUIRED except: unit_price_schedule and approved_cost_codes (can be empty)
2. retention_rate must be a decimal between 0 and 1 (e.g., 0.10 for 10%)
3. value is the total contract value as a number
4. Date format must be YYYY-MM-DD
5. unit_price_schedule maps cost codes to their maximum allowed unit price — return {{}} if no rate schedule found
6. approved_cost_codes lists all cost codes authorized under this contract — return [] if not specified
7. All monetary values as numbers (not strings)
8. Return ONLY valid JSON
9. Do NOT hallucinate cost codes or prices — only extract what is explicitly stated in the document

PDF TEXT:
{raw_text}

Extract the contract data now:
"""

        logger.debug("structuring_contract_with_llm", text_length=len(raw_text))
        result = self.llm_client.extract_json(prompt=prompt, temperature=0.1)

        logger.debug(
            "contract_structured",
            contract_id=result.get("contract_id"),
            cost_codes_count=len(result.get("approved_cost_codes", [])),
        )
        return result

    def validate_extracted_contract(self, data: dict) -> List[str]:
        """
        Validate extracted contract data and return warnings.

        Args:
            data: Extracted contract dictionary

        Returns:
            List of warning messages (empty if all valid)
        """
        warnings = []

        # Check retention rate range
        retention = data.get("retention_rate")
        if retention is not None:
            try:
                r = float(retention)
                if r < 0 or r > 1:
                    warnings.append(f"Retention rate {r} is outside valid range [0, 1]")
                if r > 0.20:
                    warnings.append(f"Retention rate {r:.0%} is unusually high (>20%)")
            except (ValueError, TypeError):
                warnings.append(f"Invalid retention rate: {retention}")

        # Check contract value
        value = data.get("value")
        if value is not None:
            try:
                v = float(value)
                if v < 0:
                    warnings.append(f"Contract value ${v:,.2f} is negative")
                if v == 0:
                    warnings.append("Contract value is zero")
            except (ValueError, TypeError):
                warnings.append(f"Invalid contract value: {value}")

        # Check date order
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and start > end:
            warnings.append(f"Start date {start} is after end date {end}")

        # Check unit price schedule for negative prices
        schedule = data.get("unit_price_schedule", {})
        if isinstance(schedule, dict):
            for code, price in schedule.items():
                try:
                    p = float(price)
                    if p < 0:
                        warnings.append(f"Negative unit price ${p:,.2f} for cost code {code}")
                except (ValueError, TypeError):
                    warnings.append(f"Invalid unit price for {code}: {price}")

        return warnings

    def _build_contract_model(self, contract_data: dict, warnings: List[str]) -> Contract:
        """
        Convert extracted dict to a validated Contract model.

        Args:
            contract_data: Structured data from LLM
            warnings: Validation warnings (affects confidence score)

        Returns:
            Validated Contract model
        """
        try:
            # Parse unit price schedule to Decimal
            unit_price_schedule = {}
            raw_schedule = contract_data.get("unit_price_schedule", {})
            if isinstance(raw_schedule, dict):
                for code, price in raw_schedule.items():
                    try:
                        unit_price_schedule[code] = Decimal(str(price))
                    except (InvalidOperation, ValueError):
                        logger.warning("skipping_invalid_unit_price", code=code, price=price)

            contract = Contract(
                id=contract_data.get("contract_id", ""),
                contractor_id=contract_data.get("contractor_id", ""),
                contractor_name=contract_data.get("contractor_name"),
                project_id=contract_data.get("project_id", ""),
                project_name=contract_data.get("project_name"),
                value=Decimal(str(contract_data["value"])),
                retention_rate=Decimal(str(contract_data["retention_rate"])),
                start_date=contract_data["start_date"],
                end_date=contract_data["end_date"],
                terms=contract_data.get("terms", ""),
                unit_price_schedule=unit_price_schedule,
                approved_cost_codes=contract_data.get("approved_cost_codes", []),
                extracted_at=datetime.now(),
                extraction_confidence=0.85 if not warnings else 0.65,
            )

            logger.debug(
                "contract_extraction_complete",
                contract_id=contract.id,
                value=float(contract.value),
                cost_codes=len(contract.approved_cost_codes),
                warnings=len(warnings),
            )

            return contract

        except Exception as e:
            logger.error("contract_model_validation_failed", error=str(e))
            raise ValueError(f"Failed to validate extracted contract data: {e}")

    def extract_contract_from_pdf(self, pdf_path: Path) -> Contract:
        """
        Full extraction pipeline: PDF -> text -> LLM structuring -> validation -> Contract model.

        Args:
            pdf_path: Path to PDF contract file

        Returns:
            Validated Contract model

        Raises:
            ValueError: If extraction or validation fails
        """
        logger.debug("starting_contract_extraction", path=str(pdf_path))

        # Step 1: Extract raw text from PDF
        raw_text = self._extract_text_from_pdf(pdf_path)

        # Step 2: Structure with LLM
        contract_data = self.structure_contract(raw_text)

        # Step 3: Validate and collect warnings
        warnings = self.validate_extracted_contract(contract_data)
        if warnings:
            for w in warnings:
                logger.warning("contract_extraction_warning", warning=w)

        # Step 4: Build Contract model
        return self._build_contract_model(contract_data, warnings)
