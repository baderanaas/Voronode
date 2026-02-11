"""
Unit tests for Contract Extractor.

Tests:
- structure_contract with valid/invalid LLM responses
- validate_extracted_contract (bad retention, negative value, date order, negative prices)
- extract_contract_from_pdf end-to-end with mocked LLM
"""

import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from backend.agents.contract_extractor import ContractExtractor
from backend.core.models import Contract


@pytest.fixture
def contract_extractor():
    """Create ContractExtractor with mocked GroqClient."""
    with patch("backend.agents.contract_extractor.GroqClient") as mock_groq_cls:
        mock_groq = Mock()
        mock_groq_cls.return_value = mock_groq
        extractor = ContractExtractor()
        extractor.llm_client = mock_groq
        yield extractor


@pytest.fixture
def valid_contract_data():
    """Valid contract data as returned by LLM."""
    return {
        "contract_id": "CONTRACT-001",
        "contractor_id": "CONT-001",
        "contractor_name": "Schultz LLC",
        "project_id": "PRJ-001",
        "project_name": "South Alyssa Tower",
        "value": 250000.00,
        "retention_rate": 0.10,
        "start_date": "2025-06-01",
        "end_date": "2026-12-31",
        "terms": "Standard construction contract with 10% retention.",
        "unit_price_schedule": {"01-100": 450.00, "05-500": 460.00},
        "approved_cost_codes": ["01-100", "05-500", "15-100", "16-100"],
    }


class TestStructureContract:
    """Test LLM-based contract structuring."""

    def test_structure_contract_valid(self, contract_extractor, valid_contract_data):
        """Test successful contract structuring."""
        contract_extractor.llm_client.extract_json.return_value = valid_contract_data

        result = contract_extractor.structure_contract("Some contract text")

        assert result["contract_id"] == "CONTRACT-001"
        assert result["retention_rate"] == 0.10
        assert result["value"] == 250000.00
        assert len(result["approved_cost_codes"]) == 4
        assert len(result["unit_price_schedule"]) == 2

        # Verify LLM was called with correct params
        contract_extractor.llm_client.extract_json.assert_called_once()
        call_kwargs = contract_extractor.llm_client.extract_json.call_args
        assert call_kwargs.kwargs["temperature"] == 0.1

    def test_structure_contract_empty_schedule(self, contract_extractor, valid_contract_data):
        """Test contract with no unit price schedule."""
        valid_contract_data["unit_price_schedule"] = {}
        valid_contract_data["approved_cost_codes"] = []
        contract_extractor.llm_client.extract_json.return_value = valid_contract_data

        result = contract_extractor.structure_contract("Contract text without schedule")

        assert result["unit_price_schedule"] == {}
        assert result["approved_cost_codes"] == []

    def test_structure_contract_llm_failure(self, contract_extractor):
        """Test handling of LLM extraction failure."""
        contract_extractor.llm_client.extract_json.side_effect = ValueError(
            "Failed to extract JSON after 3 attempts"
        )

        with pytest.raises(ValueError, match="Failed to extract"):
            contract_extractor.structure_contract("Bad text")


class TestValidateExtractedContract:
    """Test contract data validation."""

    def test_valid_contract_no_warnings(self, contract_extractor, valid_contract_data):
        """Test that valid contract produces no warnings."""
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert warnings == []

    def test_retention_out_of_range(self, contract_extractor, valid_contract_data):
        """Test that retention > 1 produces warning."""
        valid_contract_data["retention_rate"] = 1.5
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert any("outside valid range" in w for w in warnings)

    def test_retention_negative(self, contract_extractor, valid_contract_data):
        """Test that negative retention produces warning."""
        valid_contract_data["retention_rate"] = -0.1
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert any("outside valid range" in w for w in warnings)

    def test_retention_unusually_high(self, contract_extractor, valid_contract_data):
        """Test that retention > 20% produces warning."""
        valid_contract_data["retention_rate"] = 0.25
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert any("unusually high" in w for w in warnings)

    def test_negative_contract_value(self, contract_extractor, valid_contract_data):
        """Test that negative value produces warning."""
        valid_contract_data["value"] = -50000
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert any("negative" in w for w in warnings)

    def test_zero_contract_value(self, contract_extractor, valid_contract_data):
        """Test that zero value produces warning."""
        valid_contract_data["value"] = 0
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert any("zero" in w for w in warnings)

    def test_date_order_reversed(self, contract_extractor, valid_contract_data):
        """Test that start_date > end_date produces warning."""
        valid_contract_data["start_date"] = "2027-01-01"
        valid_contract_data["end_date"] = "2025-06-01"
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert any("after end date" in w for w in warnings)

    def test_negative_unit_price(self, contract_extractor, valid_contract_data):
        """Test that negative unit price produces warning."""
        valid_contract_data["unit_price_schedule"]["01-100"] = -450.00
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert any("Negative unit price" in w for w in warnings)

    def test_invalid_retention_type(self, contract_extractor, valid_contract_data):
        """Test that non-numeric retention produces warning."""
        valid_contract_data["retention_rate"] = "not_a_number"
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert any("Invalid retention rate" in w for w in warnings)

    def test_multiple_warnings(self, contract_extractor, valid_contract_data):
        """Test that multiple issues produce multiple warnings."""
        valid_contract_data["value"] = -100
        valid_contract_data["retention_rate"] = 1.5
        valid_contract_data["start_date"] = "2027-01-01"
        valid_contract_data["end_date"] = "2025-01-01"
        warnings = contract_extractor.validate_extracted_contract(valid_contract_data)
        assert len(warnings) >= 3


class TestBuildContractModel:
    """Test Contract model building from extracted data."""

    def test_build_valid_contract(self, contract_extractor, valid_contract_data):
        """Test building Contract model from valid data."""
        contract = contract_extractor._build_contract_model(valid_contract_data, [])

        assert isinstance(contract, Contract)
        assert contract.id == "CONTRACT-001"
        assert contract.contractor_id == "CONT-001"
        assert contract.contractor_name == "Schultz LLC"
        assert contract.value == Decimal("250000.00")
        assert contract.retention_rate == Decimal("0.10")
        assert contract.start_date == date(2025, 6, 1)
        assert contract.end_date == date(2026, 12, 31)
        assert len(contract.unit_price_schedule) == 2
        assert contract.unit_price_schedule["01-100"] == Decimal("450.00")
        assert contract.approved_cost_codes == ["01-100", "05-500", "15-100", "16-100"]
        assert contract.extracted_at is not None
        assert contract.extraction_confidence == 0.85

    def test_build_contract_with_warnings_lowers_confidence(
        self, contract_extractor, valid_contract_data
    ):
        """Test that warnings lower extraction confidence."""
        contract = contract_extractor._build_contract_model(
            valid_contract_data, ["Some warning"]
        )
        assert contract.extraction_confidence == 0.65

    def test_build_contract_missing_required_field(self, contract_extractor):
        """Test that missing required field raises ValueError."""
        bad_data = {"contract_id": "C-1"}  # Missing most fields

        with pytest.raises(ValueError, match="Failed to validate"):
            contract_extractor._build_contract_model(bad_data, [])

    def test_build_contract_skips_invalid_unit_prices(
        self, contract_extractor, valid_contract_data
    ):
        """Test that invalid unit prices are skipped, not crashed."""
        valid_contract_data["unit_price_schedule"]["BAD"] = "not_a_number"

        contract = contract_extractor._build_contract_model(valid_contract_data, [])

        # Valid prices kept, invalid one skipped
        assert "01-100" in contract.unit_price_schedule
        assert "BAD" not in contract.unit_price_schedule


class TestExtractContractFromPDF:
    """Test end-to-end PDF extraction pipeline."""

    def test_extract_contract_from_pdf_success(
        self, contract_extractor, valid_contract_data
    ):
        """Test full pipeline with mocked PDF and LLM."""
        # Mock PDF text extraction
        with patch.object(
            contract_extractor, "_extract_text_from_pdf", return_value="Contract text here"
        ):
            contract_extractor.llm_client.extract_json.return_value = valid_contract_data

            contract = contract_extractor.extract_contract_from_pdf(Path("test.pdf"))

            assert isinstance(contract, Contract)
            assert contract.id == "CONTRACT-001"
            assert contract.value == Decimal("250000.00")

    def test_extract_contract_from_pdf_text_failure(self, contract_extractor):
        """Test pipeline handles PDF text extraction failure."""
        with patch.object(
            contract_extractor,
            "_extract_text_from_pdf",
            side_effect=ValueError("Failed to extract text"),
        ):
            with pytest.raises(ValueError, match="Failed to extract text"):
                contract_extractor.extract_contract_from_pdf(Path("bad.pdf"))

    def test_extract_contract_from_pdf_llm_failure(self, contract_extractor):
        """Test pipeline handles LLM extraction failure."""
        with patch.object(
            contract_extractor, "_extract_text_from_pdf", return_value="Some text"
        ):
            contract_extractor.llm_client.extract_json.side_effect = ValueError(
                "LLM failed"
            )

            with pytest.raises(ValueError, match="LLM failed"):
                contract_extractor.extract_contract_from_pdf(Path("test.pdf"))

    def test_extract_contract_with_warnings(
        self, contract_extractor, valid_contract_data
    ):
        """Test that warnings are logged but extraction still succeeds."""
        valid_contract_data["retention_rate"] = 0.25  # Unusually high

        with patch.object(
            contract_extractor, "_extract_text_from_pdf", return_value="Contract text"
        ):
            contract_extractor.llm_client.extract_json.return_value = valid_contract_data

            # Should not raise, but confidence should be lower
            contract = contract_extractor.extract_contract_from_pdf(Path("test.pdf"))

            assert contract.extraction_confidence == 0.65
