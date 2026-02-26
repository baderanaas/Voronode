"""
Budget Extractor Agent

Extracts budget data from Excel/CSV files and structures them for Neo4j storage.

Pipeline:
1. Read Excel/CSV file with pandas
2. Extract budget line items (cost codes, allocations)
3. Structure with Groq/Llama3 LLM for validation
4. Return Budget model
"""

import pandas as pd
import structlog
import decimal
from pathlib import Path
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from backend.services.llm_client import GroqClient
from backend.core.models import BudgetLine

logger = structlog.get_logger()


class BudgetExtractor:
    """Extract and structure budget data from Excel/CSV files."""

    def __init__(self):
        self.llm_client = GroqClient()

    def extract_from_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract budget data from Excel or CSV file.

        Args:
            file_path: Path to budget file (.xlsx, .xls, or .csv)

        Returns:
            Dictionary with:
            {
                "project_id": str,
                "budget_lines": List[BudgetLine],
                "metadata": {...}
            }
        """
        logger.info("budget_extraction_started", file_path=str(file_path))

        try:
            # Step 1: Read file with pandas
            df = self._read_budget_file(file_path)

            # Step 2: Extract project metadata
            project_metadata = self._extract_project_metadata(df)

            # Step 3: Parse budget line items
            budget_lines = self._parse_budget_lines(df, project_metadata)

            # Step 4: Validate and structure with LLM
            validated_budget = self._validate_with_llm(budget_lines, project_metadata)

            logger.info(
                "budget_extraction_complete",
                project_id=validated_budget.get("project_id"),
                line_count=len(validated_budget["budget_lines"]),
            )

            return validated_budget

        except Exception as e:
            logger.error("budget_extraction_failed", error=str(e), file_path=str(file_path))
            raise ValueError(f"Failed to extract budget from {file_path}: {e}")

    def _read_budget_file(self, file_path: Path) -> pd.DataFrame:
        """
        Read Excel or CSV file into pandas DataFrame.

        Expected columns (flexible naming):
        - Cost Code / Code / Account Code
        - Description / Item / Line Item
        - Budget / Allocated / Amount / Budget Amount
        - Spent (optional)
        - Remaining (optional)
        """
        suffix = file_path.suffix.lower()

        if suffix in [".xlsx", ".xls"]:
            # Try to read Excel, may have multiple sheets
            # Assume budget is in first sheet or sheet named "Budget"
            try:
                df = pd.read_excel(file_path, sheet_name="Budget")
            except:
                df = pd.read_excel(file_path, sheet_name=0)

        elif suffix == ".csv":
            df = pd.read_csv(file_path)

        else:
            raise ValueError(f"Unsupported file format: {suffix}. Use .xlsx, .xls, or .csv")

        # Drop completely empty rows
        df = df.dropna(how="all")

        logger.info("budget_file_read", rows=len(df), columns=list(df.columns))

        return df

    def _extract_project_metadata(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Extract project metadata from DataFrame.

        Looks for project info in first few rows or uses LLM to infer.
        """
        metadata = {}

        # Try to find project ID in first few rows (common pattern)
        first_rows = df.head(5).astype(str)

        for idx, row in first_rows.iterrows():
            row_text = " ".join(row.values).lower()

            # Look for "project" keyword
            if "project" in row_text:
                # Try to extract project ID/name
                for val in row.values:
                    val_str = str(val).strip()
                    if val_str and val_str != "nan" and len(val_str) > 3:
                        # Potential project identifier
                        if "prj" in val_str.lower() or "project" in val_str.lower():
                            metadata["project_name"] = val_str
                            break

        # Use LLM to infer project info if not found
        if not metadata.get("project_name"):
            logger.warning("project_metadata_not_found_using_llm")
            # For now, use filename as fallback
            metadata["project_name"] = "Unknown Project"

        return metadata

    def _parse_budget_lines(
        self, df: pd.DataFrame, metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Parse budget line items from DataFrame.

        Handles flexible column naming and data formats.
        """
        budget_lines = []

        # Normalize column names (lowercase, remove spaces)
        df.columns = df.columns.str.lower().str.strip().str.replace(" ", "_")

        # Find relevant columns (flexible matching)
        cost_code_col = self._find_column(
            df, ["cost_code", "code", "account_code", "csi_code", "item_code"]
        )
        description_col = self._find_column(
            df, ["description", "item", "line_item", "work_description", "scope"]
        )
        allocated_col = self._find_column(
            df, ["budget", "allocated", "amount", "budget_amount", "budgeted"]
        )
        spent_col = self._find_column(
            df, ["spent", "actual", "expended", "used", "to_date"]
        )
        remaining_col = self._find_column(df, ["remaining", "balance", "available"])

        if not cost_code_col or not allocated_col:
            raise ValueError(
                "Required columns not found. Need at least: Cost Code and Budget/Allocated columns."
            )

        logger.info(
            "columns_matched",
            cost_code=cost_code_col,
            description=description_col,
            allocated=allocated_col,
            spent=spent_col,
        )

        # Parse each row
        for idx, row in df.iterrows():
            cost_code = str(row.get(cost_code_col, "")).strip()
            allocated_val = row.get(allocated_col)

            # Skip header rows or empty cost codes
            if not cost_code or cost_code == "nan" or "total" in cost_code.lower():
                continue

            # Skip non-numeric allocated values (likely headers)
            try:
                allocated = Decimal(str(allocated_val).replace(",", "").replace("$", ""))
                if allocated <= 0:
                    continue
            except (ValueError, decimal.InvalidOperation):
                continue

            description = str(row.get(description_col, "")) if description_col else ""
            spent = Decimal(0)
            if spent_col:
                try:
                    spent = Decimal(str(row.get(spent_col, 0)).replace(",", "").replace("$", ""))
                except:
                    spent = Decimal(0)

            remaining = allocated - spent
            if remaining_col:
                try:
                    remaining_val = Decimal(
                        str(row.get(remaining_col, 0)).replace(",", "").replace("$", "")
                    )
                    # Validate calculated vs provided remaining
                    if abs(remaining - remaining_val) > Decimal("0.01"):
                        logger.warning(
                            "remaining_mismatch",
                            cost_code=cost_code,
                            calculated=float(remaining),
                            provided=float(remaining_val),
                        )
                except:
                    pass

            budget_lines.append({
                "cost_code": cost_code,
                "description": description,
                "allocated": float(allocated),
                "spent": float(spent),
                "remaining": float(remaining),
            })

        logger.info("budget_lines_parsed", count=len(budget_lines))

        return budget_lines

    def _find_column(self, df: pd.DataFrame, possible_names: List[str]) -> Optional[str]:
        """Find column name from list of possible names (case-insensitive)."""
        for col in df.columns:
            col_normalized = col.lower().strip().replace(" ", "_")
            if col_normalized in possible_names:
                return col
        return None

    def _validate_with_llm(
        self, budget_lines: List[Dict], metadata: Dict
    ) -> Dict[str, Any]:
        """
        Validate budget data with LLM and generate project_id if needed.

        LLM can:
        1. Infer project_id from project_name
        2. Validate cost codes are reasonable
        3. Check for duplicate entries
        4. Suggest corrections
        """
        prompt = f"""
        Validate this budget data and extract project information.

        Project Metadata: {metadata}
        Budget Lines (first 5): {budget_lines[:5]}
        Total Lines: {len(budget_lines)}

        Tasks:
        1. Generate a project_id (format: PRJ-XXX) based on project_name
        2. Validate cost codes look reasonable (CSI format like 01-100, 05-500)
        3. Check for obvious errors or duplicates
        4. Return validation warnings if any

        Respond in JSON:
        {{
            "project_id": "<generated project ID>",
            "project_name": "<extracted project name>",
            "validation_warnings": ["<list of warnings if any>"],
            "is_valid": true/false
        }}
        """

        validation_result = self.llm_client.extract_json(prompt)

        if not validation_result.get("is_valid", True):
            logger.warning(
                "llm_validation_warnings", warnings=validation_result.get("validation_warnings", [])
            )

        # Build final budget structure
        project_id = validation_result.get("project_id", "PRJ-UNKNOWN")
        project_name = validation_result.get("project_name", metadata.get("project_name", "Unknown"))

        # Convert to BudgetLine models
        budget_line_models = []
        for idx, line in enumerate(budget_lines):
            budget_line_models.append({
                "id": f"{project_id}-BUD-{idx+1:03d}",
                "project_id": project_id,
                "cost_code": line["cost_code"],
                "description": line["description"],
                "allocated": Decimal(str(line["allocated"])),
                "spent": Decimal(str(line["spent"])),
                "remaining": Decimal(str(line["remaining"])),
            })

        return {
            "project_id": project_id,
            "project_name": project_name,
            "budget_lines": budget_line_models,
            "metadata": {
                "total_allocated": sum(Decimal(str(line["allocated"])) for line in budget_lines),
                "total_spent": sum(Decimal(str(line["spent"])) for line in budget_lines),
                "line_count": len(budget_lines),
                "extracted_at": datetime.now().isoformat(),
                "validation_warnings": validation_result.get("validation_warnings", []),
            },
        }

    def extract_and_validate(self, file_path: Path) -> Dict[str, Any]:
        """
        Main entry point: extract budget and validate.

        Returns structured budget data ready for Neo4j insertion.
        """
        return self.extract_from_file(file_path)
