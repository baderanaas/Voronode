"""
Unit tests for Budget Extractor.

Tests:
- _read_budget_file with Excel/CSV formats
- _find_column with flexible column naming
- _parse_budget_lines with various data formats
- _extract_project_metadata with different metadata patterns
- _validate_with_llm with valid/invalid responses
- extract_from_file end-to-end with mocked components
"""

import pytest
import pandas as pd
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

from backend.agents.budget_extractor import BudgetExtractor


@pytest.fixture
def budget_extractor():
    """Create BudgetExtractor with mocked GroqClient."""
    with patch("backend.agents.budget_extractor.GroqClient") as mock_groq_cls:
        mock_groq = Mock()
        mock_groq_cls.return_value = mock_groq
        extractor = BudgetExtractor()
        extractor.llm_client = mock_groq
        yield extractor


@pytest.fixture
def sample_budget_df():
    """Create sample budget DataFrame."""
    return pd.DataFrame({
        "Cost Code": ["01-100", "05-500", "15-100", "16-100"],
        "Description": ["Site Prep", "Structural Steel", "Plumbing", "Electrical"],
        "Budget": [400000, 800000, 350000, 600000],
        "Spent": [145000, 310000, 88000, 420000],
        "Remaining": [255000, 490000, 262000, 180000],
    })


@pytest.fixture
def valid_llm_validation():
    """Valid LLM validation response."""
    return {
        "project_id": "PRJ-001",
        "project_name": "South Alyssa Tower",
        "validation_warnings": [],
        "is_valid": True,
    }


class TestFindColumn:
    """Test flexible column name matching."""

    def test_find_exact_match(self, budget_extractor):
        """Test exact column name match."""
        df = pd.DataFrame({"cost_code": [1, 2], "amount": [100, 200]})
        result = budget_extractor._find_column(df, ["cost_code", "code"])
        assert result == "cost_code"

    def test_find_alternative_name(self, budget_extractor):
        """Test matching alternative column name."""
        df = pd.DataFrame({"account_code": [1, 2], "amount": [100, 200]})
        result = budget_extractor._find_column(df, ["cost_code", "code", "account_code"])
        assert result == "account_code"

    def test_find_case_insensitive(self, budget_extractor):
        """Test case-insensitive matching."""
        df = pd.DataFrame({"Cost Code": [1, 2], "Amount": [100, 200]})
        # After normalization, "Cost Code" becomes "cost_code"
        result = budget_extractor._find_column(df, ["cost_code"])
        assert result == "Cost Code"

    def test_find_not_found(self, budget_extractor):
        """Test returning None when column not found."""
        df = pd.DataFrame({"xyz": [1, 2], "abc": [100, 200]})
        result = budget_extractor._find_column(df, ["cost_code", "code"])
        assert result is None

    def test_find_with_spaces_normalized(self, budget_extractor):
        """Test matching columns with spaces (normalized to underscores)."""
        df = pd.DataFrame({"Cost Code": [1, 2]})
        df.columns = df.columns.str.lower().str.strip().str.replace(" ", "_")
        result = budget_extractor._find_column(df, ["cost_code"])
        assert result == "cost_code"


class TestReadBudgetFile:
    """Test reading Excel and CSV files."""

    def test_read_csv_file(self, budget_extractor, sample_budget_df, tmp_path):
        """Test reading CSV file."""
        csv_path = tmp_path / "budget.csv"
        sample_budget_df.to_csv(csv_path, index=False)

        df = budget_extractor._read_budget_file(csv_path)

        assert len(df) == 4
        assert "Cost Code" in df.columns
        assert df.iloc[0]["Cost Code"] == "01-100"

    def test_read_excel_file(self, budget_extractor, sample_budget_df, tmp_path):
        """Test reading Excel file."""
        excel_path = tmp_path / "budget.xlsx"
        sample_budget_df.to_excel(excel_path, index=False, sheet_name="Budget")

        df = budget_extractor._read_budget_file(excel_path)

        assert len(df) == 4
        assert "Cost Code" in df.columns
        assert df.iloc[0]["Cost Code"] == "01-100"

    def test_read_excel_first_sheet_fallback(self, budget_extractor, sample_budget_df, tmp_path):
        """Test reading first sheet when 'Budget' sheet doesn't exist."""
        excel_path = tmp_path / "budget.xlsx"
        sample_budget_df.to_excel(excel_path, index=False, sheet_name="Sheet1")

        df = budget_extractor._read_budget_file(excel_path)

        assert len(df) == 4
        assert "Cost Code" in df.columns

    def test_read_drops_empty_rows(self, budget_extractor, tmp_path):
        """Test that completely empty rows are dropped."""
        df_with_empty = pd.DataFrame({
            "Cost Code": ["01-100", None, "05-500"],
            "Budget": [100000, None, 200000],
        })
        csv_path = tmp_path / "budget.csv"
        df_with_empty.to_csv(csv_path, index=False)

        df = budget_extractor._read_budget_file(csv_path)

        # Empty row should be dropped (only 2 valid rows remain)
        assert len(df) == 2

    def test_read_unsupported_format(self, budget_extractor, tmp_path):
        """Test that unsupported file format raises error."""
        txt_path = tmp_path / "budget.txt"
        txt_path.write_text("some text")

        with pytest.raises(ValueError, match="Unsupported file format"):
            budget_extractor._read_budget_file(txt_path)


class TestExtractProjectMetadata:
    """Test project metadata extraction."""

    def test_extract_metadata_with_project_in_rows(self, budget_extractor):
        """Test extracting project name from first rows."""
        df = pd.DataFrame({
            "A": ["Project Name", "01-100"],
            "B": ["South Alyssa Tower", "Site Prep"],
            "C": ["PRJ-001", "400000"],
        })

        metadata = budget_extractor._extract_project_metadata(df)

        assert "project_name" in metadata
        # Should find something with "project" in it
        assert metadata["project_name"] != "Unknown Project"

    def test_extract_metadata_no_project_uses_fallback(self, budget_extractor):
        """Test fallback when no project info found."""
        df = pd.DataFrame({
            "Cost Code": ["01-100", "05-500"],
            "Budget": [100000, 200000],
        })

        metadata = budget_extractor._extract_project_metadata(df)

        assert metadata["project_name"] == "Unknown Project"

    def test_extract_metadata_with_prj_prefix(self, budget_extractor):
        """Test finding project ID with PRJ prefix."""
        df = pd.DataFrame({
            "A": ["Cost Code", "01-100"],
            "B": ["PRJ-123 Building Project", "Site Prep"],
        })

        metadata = budget_extractor._extract_project_metadata(df)

        assert "project_name" in metadata
        # Should find the project name since row contains "project" keyword and "PRJ"
        assert metadata["project_name"] != "Unknown Project"


class TestParseBudgetLines:
    """Test parsing budget line items."""

    def test_parse_standard_format(self, budget_extractor, sample_budget_df):
        """Test parsing budget with standard column names."""
        metadata = {"project_name": "Test Project"}

        lines = budget_extractor._parse_budget_lines(sample_budget_df, metadata)

        assert len(lines) == 4
        assert lines[0]["cost_code"] == "01-100"
        assert lines[0]["description"] == "Site Prep"
        assert lines[0]["allocated"] == 400000
        assert lines[0]["spent"] == 145000
        assert lines[0]["remaining"] == 255000

    def test_parse_alternative_column_names(self, budget_extractor):
        """Test parsing with alternative column naming."""
        df = pd.DataFrame({
            "Account Code": ["01-100", "05-500"],
            "Allocated": [100000, 200000],
            "Actual": [50000, 75000],
            "Item": ["Site Work", "Steel"],
        })
        metadata = {}

        lines = budget_extractor._parse_budget_lines(df, metadata)

        assert len(lines) == 2
        assert lines[0]["cost_code"] == "01-100"
        assert lines[0]["allocated"] == 100000
        assert lines[0]["spent"] == 50000
        assert lines[0]["description"] == "Site Work"

    def test_parse_without_spent_column(self, budget_extractor):
        """Test parsing when spent column is missing."""
        df = pd.DataFrame({
            "Cost Code": ["01-100", "05-500"],
            "Budget": [100000, 200000],
        })
        metadata = {}

        lines = budget_extractor._parse_budget_lines(df, metadata)

        assert len(lines) == 2
        assert lines[0]["spent"] == 0
        assert lines[0]["remaining"] == 100000  # allocated - 0

    def test_parse_skips_total_rows(self, budget_extractor):
        """Test that rows with 'total' in cost code are skipped."""
        df = pd.DataFrame({
            "Cost Code": ["01-100", "Total", "Grand Total"],
            "Budget": [100000, 100000, 100000],
        })
        metadata = {}

        lines = budget_extractor._parse_budget_lines(df, metadata)

        # Should only have 1 line (skip the two totals)
        assert len(lines) == 1
        assert lines[0]["cost_code"] == "01-100"

    def test_parse_skips_negative_allocated(self, budget_extractor):
        """Test that negative allocated amounts are skipped."""
        df = pd.DataFrame({
            "Cost Code": ["01-100", "05-500"],
            "Budget": [100000, -50000],
        })
        metadata = {}

        lines = budget_extractor._parse_budget_lines(df, metadata)

        assert len(lines) == 1
        assert lines[0]["cost_code"] == "01-100"

    def test_parse_skips_zero_allocated(self, budget_extractor):
        """Test that zero allocated amounts are skipped."""
        df = pd.DataFrame({
            "Cost Code": ["01-100", "05-500"],
            "Budget": [100000, 0],
        })
        metadata = {}

        lines = budget_extractor._parse_budget_lines(df, metadata)

        assert len(lines) == 1

    def test_parse_handles_currency_formatting(self, budget_extractor):
        """Test parsing handles $ and comma formatting."""
        df = pd.DataFrame({
            "Cost Code": ["01-100"],
            "Budget": ["$1,250,000.00"],
            "Spent": ["$500,000"],
        })
        metadata = {}

        lines = budget_extractor._parse_budget_lines(df, metadata)

        assert len(lines) == 1
        assert lines[0]["allocated"] == 1250000.00
        assert lines[0]["spent"] == 500000

    def test_parse_validates_remaining_column(self, budget_extractor):
        """Test that provided remaining is validated against calculated."""
        df = pd.DataFrame({
            "Cost Code": ["01-100"],
            "Budget": [100000],
            "Spent": [30000],
            "Remaining": [70000],  # Correct: 100000 - 30000
        })
        metadata = {}

        # Should not raise error with correct remaining
        lines = budget_extractor._parse_budget_lines(df, metadata)
        assert lines[0]["remaining"] == 70000

    def test_parse_missing_required_columns(self, budget_extractor):
        """Test error when required columns are missing."""
        df = pd.DataFrame({
            "Description": ["Some item"],
            "Amount": [100000],
        })
        metadata = {}

        with pytest.raises(ValueError, match="Required columns not found"):
            budget_extractor._parse_budget_lines(df, metadata)


class TestValidateWithLLM:
    """Test LLM validation and project ID generation."""

    def test_validate_generates_project_id(self, budget_extractor, valid_llm_validation):
        """Test that LLM generates project_id."""
        budget_extractor.llm_client.extract_json.return_value = valid_llm_validation

        budget_lines = [
            {"cost_code": "01-100", "description": "Site", "allocated": 100000, "spent": 50000, "remaining": 50000}
        ]
        metadata = {"project_name": "Test Project"}

        result = budget_extractor._validate_with_llm(budget_lines, metadata)

        assert result["project_id"] == "PRJ-001"
        assert result["project_name"] == "South Alyssa Tower"
        assert len(result["budget_lines"]) == 1

    def test_validate_creates_budget_line_ids(self, budget_extractor, valid_llm_validation):
        """Test that budget line IDs are generated correctly."""
        budget_extractor.llm_client.extract_json.return_value = valid_llm_validation

        budget_lines = [
            {"cost_code": "01-100", "description": "Site", "allocated": 100000, "spent": 0, "remaining": 100000},
            {"cost_code": "05-500", "description": "Steel", "allocated": 200000, "spent": 0, "remaining": 200000},
        ]
        metadata = {}

        result = budget_extractor._validate_with_llm(budget_lines, metadata)

        assert result["budget_lines"][0]["id"] == "PRJ-001-BUD-001"
        assert result["budget_lines"][1]["id"] == "PRJ-001-BUD-002"

    def test_validate_calculates_totals(self, budget_extractor, valid_llm_validation):
        """Test that totals are calculated correctly."""
        budget_extractor.llm_client.extract_json.return_value = valid_llm_validation

        budget_lines = [
            {"cost_code": "01-100", "description": "Site", "allocated": 100000, "spent": 50000, "remaining": 50000},
            {"cost_code": "05-500", "description": "Steel", "allocated": 200000, "spent": 75000, "remaining": 125000},
        ]
        metadata = {}

        result = budget_extractor._validate_with_llm(budget_lines, metadata)

        assert result["metadata"]["total_allocated"] == Decimal("300000")
        assert result["metadata"]["total_spent"] == Decimal("125000")
        assert result["metadata"]["line_count"] == 2

    def test_validate_includes_warnings(self, budget_extractor):
        """Test that validation warnings are included."""
        llm_response = {
            "project_id": "PRJ-002",
            "project_name": "Test Project",
            "validation_warnings": ["Duplicate cost code 01-100", "Invalid cost code format: ABC"],
            "is_valid": False,
        }
        budget_extractor.llm_client.extract_json.return_value = llm_response

        budget_lines = [{"cost_code": "01-100", "description": "Test", "allocated": 100000, "spent": 0, "remaining": 100000}]
        metadata = {}

        result = budget_extractor._validate_with_llm(budget_lines, metadata)

        assert len(result["metadata"]["validation_warnings"]) == 2
        assert "Duplicate cost code" in result["metadata"]["validation_warnings"][0]

    def test_validate_uses_fallback_project_id(self, budget_extractor):
        """Test fallback when LLM doesn't return project_id."""
        llm_response = {
            "is_valid": True,
            "validation_warnings": [],
            # Missing project_id
        }
        budget_extractor.llm_client.extract_json.return_value = llm_response

        budget_lines = [{"cost_code": "01-100", "description": "Test", "allocated": 100000, "spent": 0, "remaining": 100000}]
        metadata = {}

        result = budget_extractor._validate_with_llm(budget_lines, metadata)

        assert result["project_id"] == "PRJ-UNKNOWN"

    def test_validate_preserves_decimal_precision(self, budget_extractor, valid_llm_validation):
        """Test that Decimal precision is maintained."""
        budget_extractor.llm_client.extract_json.return_value = valid_llm_validation

        budget_lines = [
            {"cost_code": "01-100", "description": "Test", "allocated": 123456.78, "spent": 23456.78, "remaining": 100000.00}
        ]
        metadata = {}

        result = budget_extractor._validate_with_llm(budget_lines, metadata)

        assert result["budget_lines"][0]["allocated"] == Decimal("123456.78")
        assert result["budget_lines"][0]["spent"] == Decimal("23456.78")


class TestExtractFromFile:
    """Test end-to-end file extraction pipeline."""

    def test_extract_from_csv_success(self, budget_extractor, sample_budget_df, valid_llm_validation, tmp_path):
        """Test full pipeline with CSV file."""
        csv_path = tmp_path / "budget.csv"
        sample_budget_df.to_csv(csv_path, index=False)

        budget_extractor.llm_client.extract_json.return_value = valid_llm_validation

        result = budget_extractor.extract_from_file(csv_path)

        assert result["project_id"] == "PRJ-001"
        assert result["project_name"] == "South Alyssa Tower"
        assert len(result["budget_lines"]) == 4
        assert result["metadata"]["line_count"] == 4
        assert result["metadata"]["total_allocated"] > 0

    def test_extract_from_excel_success(self, budget_extractor, sample_budget_df, valid_llm_validation, tmp_path):
        """Test full pipeline with Excel file."""
        excel_path = tmp_path / "budget.xlsx"
        sample_budget_df.to_excel(excel_path, index=False, sheet_name="Budget")

        budget_extractor.llm_client.extract_json.return_value = valid_llm_validation

        result = budget_extractor.extract_from_file(excel_path)

        assert result["project_id"] == "PRJ-001"
        assert len(result["budget_lines"]) == 4

    def test_extract_handles_file_read_error(self, budget_extractor, tmp_path):
        """Test error handling when file cannot be read."""
        bad_path = tmp_path / "nonexistent.csv"

        with pytest.raises(ValueError, match="Failed to extract budget"):
            budget_extractor.extract_from_file(bad_path)

    def test_extract_handles_llm_error(self, budget_extractor, sample_budget_df, tmp_path):
        """Test error handling when LLM validation fails."""
        csv_path = tmp_path / "budget.csv"
        sample_budget_df.to_csv(csv_path, index=False)

        budget_extractor.llm_client.extract_json.side_effect = ValueError("LLM failed")

        with pytest.raises(ValueError, match="Failed to extract budget"):
            budget_extractor.extract_from_file(csv_path)

    def test_extract_and_validate_alias(self, budget_extractor, sample_budget_df, valid_llm_validation, tmp_path):
        """Test that extract_and_validate calls extract_from_file."""
        csv_path = tmp_path / "budget.csv"
        sample_budget_df.to_csv(csv_path, index=False)

        budget_extractor.llm_client.extract_json.return_value = valid_llm_validation

        result1 = budget_extractor.extract_from_file(csv_path)
        result2 = budget_extractor.extract_and_validate(csv_path)

        # Both should return same structure
        assert result1["project_id"] == result2["project_id"]
        assert len(result1["budget_lines"]) == len(result2["budget_lines"])
