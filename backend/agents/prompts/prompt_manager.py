"""
Prompt Manager - Load and render Jinja2 templates for agent prompts.

Centralizes prompt template management with caching and validation.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound
import structlog

logger = structlog.get_logger()


class PromptManager:
    """Manages loading and rendering of Jinja2 prompt templates."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize PromptManager.

        Args:
            templates_dir: Directory containing .j2 template files
                          (default: backend/agents/prompts/)
        """
        if templates_dir is None:
            templates_dir = Path(__file__).parent

        self.templates_dir = templates_dir
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )

        logger.info("prompt_manager_initialized", templates_dir=str(templates_dir))

    def render(self, template_name: str, **kwargs: Any) -> str:
        """
        Render a prompt template with given variables.

        Args:
            template_name: Template filename (e.g., "planner/analyze.j2")
            **kwargs: Variables to pass to template

        Returns:
            Rendered prompt string

        Raises:
            TemplateNotFound: If template file doesn't exist
        """
        try:
            template = self.env.get_template(template_name)
            rendered = template.render(**kwargs)

            logger.debug(
                "prompt_rendered",
                template=template_name,
                vars=list(kwargs.keys()),
                length=len(rendered),
            )

            return rendered

        except TemplateNotFound as e:
            logger.error("template_not_found", template=template_name, error=str(e))
            raise

    def render_string(self, template_string: str, **kwargs: Any) -> str:
        """
        Render a template from a string (for inline templates).

        Args:
            template_string: Jinja2 template as string
            **kwargs: Variables to pass to template

        Returns:
            Rendered prompt string
        """
        template = self.env.from_string(template_string)
        return template.render(**kwargs)


# Global prompt manager instance
_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """Get singleton PromptManager instance."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


def render_prompt(template_name: str, **kwargs: Any) -> str:
    """
    Convenience function to render a prompt template.

    Args:
        template_name: Template filename (e.g., "planner/analyze.j2")
        **kwargs: Variables to pass to template

    Returns:
        Rendered prompt string
    """
    return get_prompt_manager().render(template_name, **kwargs)
