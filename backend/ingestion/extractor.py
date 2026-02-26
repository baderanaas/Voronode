"""Invoice extraction agent - converts PDF to structured Invoice model."""

from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog
import pdfplumber
from pypdf import PdfReader

from backend.core.models import Invoice, LineItem
from backend.services.llm_client import GroqClient

logger = structlog.get_logger()


class InvoiceExtractor:
    """Extract structured invoice data from PDF files."""

    def __init__(self):
        self.llm_client = GroqClient()

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """
        Extract text from PDF using pdfplumber (fallback to pypdf).

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text content

        Raises:
            ValueError: If text extraction fails
        """
        try:
            # Try pdfplumber first (better for tables/structured content)
            logger.info("extracting_pdf_text", path=str(pdf_path), method="pdfplumber")
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

                if text.strip():
                    logger.info(
                        "pdf_extraction_success",
                        method="pdfplumber",
                        text_length=len(text),
                    )
                    return text.strip()

        except Exception as e:
            logger.warning("pdfplumber_failed", error=str(e))

        # Fallback to pypdf
        try:
            logger.info("extracting_pdf_text", path=str(pdf_path), method="pypdf")
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            if text.strip():
                logger.info(
                    "pdf_extraction_success", method="pypdf", text_length=len(text)
                )
                return text.strip()

        except Exception as e:
            logger.error("pypdf_failed", error=str(e))

        raise ValueError(f"Failed to extract text from PDF: {pdf_path}")

    def structure_invoice(self, raw_text: str) -> dict:
        """
        Use Groq LLM to extract structured invoice data from raw text.

        Args:
            raw_text: Extracted PDF text

        Returns:
            Dictionary matching Invoice schema
        """
        prompt = f"""You are a financial document extraction AI. Extract structured invoice data from the PDF text below.

OUTPUT SCHEMA:
{{
  "invoice_number": "INV-2024-0001",
  "date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "contractor_name": "string",
  "project_name": "string",
  "contract_id": null,
  "line_items": [
    {{
      "cost_code": "XX-XXX",
      "description": "string",
      "quantity": 10.0,
      "unit_price": 100.0,
      "total": 1000.0
    }}
  ],
  "total_amount": 1000.0
}}

CRITICAL RULES:
1. ALL fields are REQUIRED except: due_date and contract_id (can be null)
2. cost_code must be extracted from the PDF - it's the code before the description (e.g., "05-500", "16-100")
3. If cost_code is not visible, infer it from the description using standard CSI codes
4. total = quantity × unit_price (must match exactly)
5. total_amount = sum of all line_items.total
6. Date format must be YYYY-MM-DD
7. All numbers as decimals (not strings)
8. Return ONLY valid JSON with NO null values except for due_date and contract_id

PDF TEXT:
{raw_text}

Extract the invoice data now:
"""

        logger.info("structuring_invoice_with_llm", text_length=len(raw_text))
        result = self.llm_client.extract_json(prompt=prompt)

        logger.info(
            "invoice_structured",
            invoice_number=result.get("invoice_number"),
            line_items_count=len(result.get("line_items", [])),
        )
        return result

    def extract_invoice_from_pdf(self, pdf_path: Path) -> Invoice:
        """
        Full extraction pipeline: PDF → text → structured Invoice.

        Args:
            pdf_path: Path to PDF invoice file

        Returns:
            Validated Invoice model

        Raises:
            ValueError: If extraction or validation fails
        """
        logger.info("starting_invoice_extraction", path=str(pdf_path))

        # Step 1: Extract text
        raw_text = self.extract_text_from_pdf(pdf_path)

        # Step 2: Structure with LLM
        invoice_data = self.structure_invoice(raw_text)

        # Step 3: Convert to Pydantic models
        try:
            # Extract line items
            line_items = []
            for idx, item_data in enumerate(invoice_data.get("line_items", [])):
                # Handle missing cost_code gracefully
                if not item_data.get("cost_code"):
                    logger.warning(
                        "line_item_missing_cost_code",
                        index=idx,
                        description=item_data.get("description"),
                    )
                    item_data["cost_code"] = "99-999"  # Placeholder for unknown

                line_item = LineItem(**item_data)
                line_items.append(line_item)

            # Build invoice
            invoice = Invoice(
                invoice_number=invoice_data["invoice_number"],
                date=invoice_data["date"],
                due_date=invoice_data.get("due_date"),
                contractor_id=invoice_data[
                    "contractor_name"
                ],  # Use name as ID placeholder
                contract_id=invoice_data.get("contract_id"),
                amount=invoice_data["total_amount"],
                line_items=line_items,
                extracted_at=datetime.now(),
                extraction_confidence=0.9,  # TODO: Calculate based on validation
            )

            logger.info(
                "invoice_extraction_complete",
                invoice_number=invoice.invoice_number,
                amount=float(invoice.amount),
                line_items=len(invoice.line_items),
            )

            return invoice

        except Exception as e:
            logger.error("invoice_model_validation_failed", error=str(e))
            raise ValueError(f"Failed to validate extracted invoice data: {e}")
