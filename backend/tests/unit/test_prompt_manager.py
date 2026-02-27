"""
Unit tests for PromptManager - Jinja2 template rendering.
"""

import pytest
from backend.agents.prompts.prompt_manager import PromptManager, render_prompt


class TestPromptManager:
    """Test PromptManager template loading and rendering."""

    def test_render_simple_template(self):
        """Test rendering a simple template with variables."""
        pm = PromptManager()

        result = pm.render(
            "planner/analyze.j2",
            user_message="Show me all invoices",
            history=[],
        )

        assert "Show me all invoices" in result
        assert "Available Routes:" in result
        assert "Respond in JSON:" in result

    def test_render_with_history(self):
        """Test rendering template with conversation history."""
        pm = PromptManager()

        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        result = pm.render(
            "planner/analyze.j2",
            user_message="What invoices do we have?",
            history=history,
        )

        assert "What invoices do we have?" in result
        assert "Conversation History (most recent last):" in result

    def test_render_retry_template(self):
        """Test rendering retry_with_feedback template."""
        pm = PromptManager()

        result = pm.render(
            "planner/retry_with_feedback.j2",
            user_query="Find overdue invoices",
            previous_plan={"tool": "CypherQueryTool"},
            issues=["No results found", "Query too broad"],
            retry_suggestion="Be more specific with date range",
            retry_count=0,
        )

        assert "Find overdue invoices" in result
        assert "No results found" in result
        assert "retry attempt 1 of 2" in result

    def test_render_next_step_template(self):
        """Test rendering plan_next_step template."""
        pm = PromptManager()

        completed_steps = [
            {"step": 1, "tool": "CypherQueryTool", "status": "success"}
        ]

        result = pm.render(
            "planner/plan_next_step.j2",
            user_query="Find contractor with highest variance",
            strategy="Find project → get contractors → calculate variance",
            completed_steps=completed_steps,
            current_results={"project_id": "P001"},
        )

        assert "Find contractor with highest variance" in result
        assert "Completed Steps (1):" in result
        assert "P001" in result

    def test_render_prompt_convenience_function(self):
        """Test the convenience render_prompt function."""
        result = render_prompt(
            "planner/analyze.j2",
            user_message="Test query",
            history=[],
        )

        assert "Test query" in result
        assert isinstance(result, str)

    def test_template_not_found(self):
        """Test error handling for missing template."""
        pm = PromptManager()

        with pytest.raises(Exception):  # Should raise TemplateNotFound
            pm.render(
                "nonexistent/template.j2",
                some_var="value",
            )

    def test_render_string_inline(self):
        """Test rendering inline template string."""
        pm = PromptManager()

        template_str = "Hello {{ name }}, you have {{ count }} messages."
        result = pm.render_string(template_str, name="Alice", count=5)

        assert result == "Hello Alice, you have 5 messages."

    def test_jinja_filters(self):
        """Test Jinja2 filters work correctly."""
        pm = PromptManager()

        result = pm.render(
            "planner/plan_next_step.j2",
            user_query="Test",
            strategy="Test strategy",
            completed_steps=[1, 2, 3],  # Should use |length filter
            current_results={},
        )

        # Template uses {{ completed_steps|length }}
        assert "Completed Steps (3):" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
