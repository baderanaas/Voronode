"""
Responder Agent - Response formatting and presentation.

Formats validated results into user-friendly responses with appropriate display formats
(text, table, chart). Separate from Validator to maintain single responsibility.
"""

from backend.core.logging import get_logger
from typing import Dict, Any

from backend.services.llm_client import OpenAIClient
from backend.agents.prompts.prompt_manager import render_prompt

logger = get_logger(__name__)


class ResponderAgent:
    """
    Agent that formats validated results into user-friendly responses.

    Responsibilities:
    1. Format execution results into natural language
    2. Determine appropriate display format (text/table/chart)
    3. Structure data for visualization
    4. Handle generic responses (greetings, clarifications, errors)
    5. Add helpful context and metadata
    """

    def __init__(self):
        """Initialize Responder with OpenAI LLM client (GPT-4o-mini)."""
        self.llm = OpenAIClient()

    def format_response(
        self,
        user_query: str,
        execution_results: Dict[str, Any],
        metadata: Dict[str, Any],
        execution_mode: str,
    ) -> Dict[str, Any]:
        """
        Format validated execution results into natural language response.

        Args:
            user_query: Original user query
            execution_results: Validated results from Executor
            metadata: Execution metadata (time, tools used, etc.)
            execution_mode: "one_way" or "react"

        Returns:
            {
                "response": "<formatted natural language response>",
                "display_format": "text" | "table" | "chart",
                "data": {  # Structured data for visualization
                    "rows": [...],  # If table
                    "chart_type": "...",  # If chart
                    "summary": "...",
                    "metadata": {...}
                }
            }
        """
        logger.debug("responder_formatting", mode=execution_mode)

        # Extract successful results
        results = execution_results.get("results", [])
        successful_results = [r for r in results if r.get("status") == "success"]

        prompt = f"""
        Format these validated tool results into a user-friendly response.

        User Question: "{user_query}"
        Execution Mode: {execution_mode}
        Successful Results: {successful_results}
        Execution Metadata: {metadata}

        Guidelines:
        1. Answer the question directly and concisely
        2. Include relevant numbers and data points
        3. Use natural, conversational language
        4. Choose the appropriate display format:
           - "text": For simple answers, narrative responses, single values
           - "table": For multiple records/rows with structured fields
           - "chart": For comparisons, trends, distributions

        5. **IMPORTANT - Avoid Duplication**:
           - If display_format is "table": Put ONLY a brief summary in "response" (e.g., "Found 4 invoices for CONTRACT-001").
             Do NOT create a markdown table in the response field. The actual table data goes in data.rows.
           - If display_format is "text": Use markdown formatting (bold, lists, code blocks, etc.) in the response field.
           - If display_format is "chart": Put only a brief summary in "response", chart data in data field.

        6. Markdown formatting (for text responses only):
           - Use **bold** for emphasis
           - Use bullet points for lists
           - Use `code` for technical terms (IDs, codes)
           - Use > blockquotes for important notes
           - Use headers (##, ###) for organizing sections
           - DO NOT use markdown tables - use display_format: "table" instead

        Respond in JSON:
        {{
            "response": "<natural language answer or brief summary>",
            "display_format": "text" | "table" | "chart",
            "data": {{
                // If display_format is "table":
                "rows": [
                    {{"column1": "value1", "column2": "value2"}},
                    ...
                ],
                "columns": ["column1", "column2"],

                // If display_format is "chart":
                "chart_type": "bar" | "line" | "pie" | "scatter",
                "x_axis": [...],
                "y_axis": [...],
                "labels": [...],

                // Always include:
                "summary": "<key takeaway in one sentence>",
                "metadata": {{
                    "execution_time": {metadata.get('execution_time', 0)},
                    "tools_used": {metadata.get('tools_used', [])},
                    "record_count": <number of records if applicable>
                }}
            }}
        }}

        Examples:

        Query: "Show me invoices over $50k"
        Result: {{
            "response": "Found **8 invoices** over $50,000, totaling **$456,789**. The largest is `INV-125` from ABC Contractors at **$125,000**.",
            "display_format": "table",
            "data": {{
                "rows": [
                    {{"invoice_id": "INV-001", "contractor": "ABC Contractors", "amount": 125000, "date": "2025-06-15"}},
                    {{"invoice_id": "INV-002", "contractor": "XYZ Corp", "amount": 98000, "date": "2025-07-20"}},
                    ...
                ],
                "columns": ["invoice_id", "contractor", "amount", "date"],
                "summary": "8 invoices totaling $456,789",
                "metadata": {{"record_count": 8}}
            }}
        }}

        Query: "What's the total retention?"
        Result: {{
            "response": "The total retention across all active contracts is **$234,567** (representing **10.2%** of total contract value).",
            "display_format": "text",
            "data": {{
                "summary": "Total retention: $234,567",
                "metadata": {{"record_count": 1}}
            }}
        }}

        Query: "Which contractor has the most violations?"
        Result: {{
            "response": "## Compliance Violations\n\n`ABC Contractors` has the most violations with **5 total**:\n\n- **3** retention calculation errors\n- **2** cost code scope violations\n\n> ⚠️ **Note:** This contractor should be flagged for additional review.",
            "display_format": "text",
            "data": {{
                "summary": "ABC Contractors: 5 violations",
                "metadata": {{"record_count": 5}}
            }}
        }}
        """

        result = self.llm.extract_json(prompt, temperature=0.3)

        logger.debug(
            "responder_formatted",
            format=result.get("display_format"),
            has_data=bool(result.get("data")),
        )

        return result

    def format_upload_response(self, execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format upload tool results into a specific, data-rich confirmation using an LLM.

        Uses a dedicated prompt that understands InvoiceUploadTool / ContractUploadTool /
        BudgetUploadTool result structures, so the LLM can mention real IDs, amounts,
        contractor names, anomalies, etc. rather than treating them as generic query rows.
        """
        logger.debug("responder_formatting_upload")

        prompt = render_prompt(
            "responder/format_upload.j2",
            results=execution_results.get("results", []),
        )

        result = self.llm.extract_json(prompt, temperature=0.2)

        logger.debug(
            "responder_upload_formatted",
            steps=len(execution_results.get("results", [])),
        )

        return result

    def format_generic_response(self) -> Dict[str, Any]:
        """
        Format generic responses (greetings, out-of-scope queries).

        Returns hardcoded helpful message.

        Returns:
            Formatted response with consistent structure
        """
        logger.debug("responder_formatting_generic")

        # Hardcoded generic response for greetings/out-of-scope
        hardcoded_message = (
            "I'm an AI assistant for financial data analysis. "
            "I can help you query invoices, contracts, budgets, and projects."
        )

        return {
            "response": hardcoded_message,
            "display_format": "text",
            "data": None,
        }

    def format_clarification_response(self, clarification_text: str) -> Dict[str, Any]:
        """
        Format clarification responses.

        Returns the planner's clarifying question to the user.

        Args:
            clarification_text: Clarification question from Planner

        Returns:
            Formatted response with clarification question
        """
        logger.debug("responder_formatting_clarification")

        return {
            "response": clarification_text,
            "display_format": "text",
            "data": None,
        }

    def format_error_response(
        self,
        user_query: str,
        issues: list,
        retry_suggestion: str,
    ) -> Dict[str, Any]:
        """
        Format error response when max retries reached.

        Args:
            user_query: Original user query
            issues: List of validation issues
            retry_suggestion: Suggestion from Validator

        Returns:
            Formatted error response
        """
        logger.debug("responder_formatting_error", issues_count=len(issues))

        # Create user-friendly error message
        error_message = (
            f"I tried multiple approaches to answer your question but encountered some challenges:\n\n"
        )

        for idx, issue in enumerate(issues, 1):
            error_message += f"{idx}. {issue}\n"

        error_message += f"\n{retry_suggestion}"

        return {
            "response": error_message,
            "display_format": "text",
            "data": {
                "summary": "Unable to complete query after multiple attempts",
                "issues": issues,
            },
        }
