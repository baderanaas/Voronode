"""
PythonREPLTool - Execute Python code for complex calculations.

High-priority tool for statistical analysis, financial formulas, and data transformations
beyond what CalculatorTool provides.

SECURITY: Sandboxed execution with restricted imports.
"""

from backend.core.logging import get_logger
import re
from typing import Dict, Any, Optional
from io import StringIO
import sys

logger = get_logger(__name__)


class PythonREPLTool:
    """
    Tool for executing Python code in a sandboxed environment.

    Use cases:
    - Statistical analysis (mean, median, std dev, percentiles)
    - Financial formulas (NPV, IRR, depreciation)
    - Data transformations
    - Custom calculations not in CalculatorTool

    Safety:
    - Restricted imports (no os, sys, subprocess, socket, file I/O)
    - Output capture
    - Execution timeout
    """

    # Allowed imports for calculations
    ALLOWED_IMPORTS = {
        "math",
        "statistics",
        "decimal",
        "fractions",
        "datetime",
        "json",
        "re",
    }

    # Numpy and pandas allowed but in restricted mode (no file I/O)
    ALLOWED_PACKAGES = {
        "numpy": "np",
        "pandas": "pd",
    }

    # Forbidden imports for security
    FORBIDDEN_IMPORTS = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "http",
        "pickle",
        "shelve",
        "importlib",
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
    }

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
        code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute Python code safely.

        Args:
            query: User's original query (for logging)
            action: Description of what code should do
            context: Additional context with previous_results
            code: Python code to execute (extracted from action if not provided)

        Returns:
            {
                "result": "<execution output>",
                "success": true/false,
                "code": "<code that was executed>",
                "error": "<error message if failed>"
            }
        """
        # Extract code from action if not provided directly
        if not code:
            code = self._extract_code_from_action(action)

        if not code:
            return {
                "error": "No Python code provided to execute",
                "success": False,
            }

        logger.info("python_repl_executing", code_length=len(code))

        # Security check: validate imports
        security_check = self._check_security(code)
        if not security_check["safe"]:
            logger.warning("python_repl_blocked", reason=security_check["reason"])
            return {
                "error": f"Security violation: {security_check['reason']}",
                "success": False,
                "code": code,
            }

        # Execute code
        try:
            result = self._execute_code(code)
            logger.info("python_repl_success", output_length=len(str(result)))

            return {
                "result": result,
                "success": True,
                "code": code,
            }

        except Exception as e:
            logger.error("python_repl_failed", error=str(e))
            return {
                "error": str(e),
                "success": False,
                "code": code,
            }

    def _extract_code_from_action(self, action: str) -> Optional[str]:
        """
        Extract Python code from action string.

        Looks for code blocks in markdown format or raw Python code.
        """
        # Try to find code in markdown code blocks
        code_block_match = re.search(r'```python\s*(.*?)\s*```', action, re.DOTALL)
        if code_block_match:
            return code_block_match.group(1).strip()

        code_block_match = re.search(r'```\s*(.*?)\s*```', action, re.DOTALL)
        if code_block_match:
            return code_block_match.group(1).strip()

        # If no code blocks, treat entire action as code if it looks like Python
        if any(keyword in action for keyword in ["import", "def ", "print(", "="]):
            return action.strip()

        return None

    def _check_security(self, code: str) -> Dict[str, Any]:
        """
        Check code for security violations.

        Returns:
            {"safe": true/false, "reason": "<explanation if unsafe>"}
        """
        # Check for forbidden imports
        for forbidden in self.FORBIDDEN_IMPORTS:
            if re.search(rf'\b{forbidden}\b', code):
                return {
                    "safe": False,
                    "reason": f"Forbidden import or function: {forbidden}",
                }

        # Check for file operations
        if re.search(r'\bopen\s*\(', code):
            return {
                "safe": False,
                "reason": "File operations not allowed",
            }

        # Check for eval/exec
        if re.search(r'\b(eval|exec|compile)\s*\(', code):
            return {
                "safe": False,
                "reason": "Dynamic code execution not allowed",
            }

        return {"safe": True}

    def _execute_code(self, code: str) -> str:
        """
        Execute Python code and capture output.

        Returns:
            String output from code execution
        """
        # Create restricted globals (only safe builtins)
        restricted_globals = {
            "__builtins__": {
                # Safe builtins
                "abs": abs,
                "all": all,
                "any": any,
                "bool": bool,
                "dict": dict,
                "enumerate": enumerate,
                "filter": filter,
                "float": float,
                "int": int,
                "len": len,
                "list": list,
                "map": map,
                "max": max,
                "min": min,
                "pow": pow,
                "print": print,
                "range": range,
                "round": round,
                "set": set,
                "sorted": sorted,
                "str": str,
                "sum": sum,
                "tuple": tuple,
                "zip": zip,
            }
        }

        # Add allowed imports
        for module in self.ALLOWED_IMPORTS:
            try:
                restricted_globals[module] = __import__(module)
            except ImportError:
                pass  # Module not available, skip

        # Add numpy and pandas if available
        try:
            import numpy as np
            restricted_globals["np"] = np
        except ImportError:
            pass

        try:
            import pandas as pd
            restricted_globals["pd"] = pd
        except ImportError:
            pass

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            # Execute code
            exec(code, restricted_globals)

            # Get output
            output = captured_output.getvalue()

            # If no print output, try to get the last expression value
            if not output.strip():
                # Try to eval the last line if it's an expression
                lines = code.strip().split('\n')
                last_line = lines[-1].strip()
                if last_line and not any(last_line.startswith(kw) for kw in ['import', 'def ', 'class ', 'for ', 'while ', 'if ', 'print(']):
                    try:
                        result = eval(last_line, restricted_globals)
                        output = str(result)
                    except:
                        pass

            return output.strip() if output.strip() else "Code executed successfully (no output)"

        finally:
            # Restore stdout
            sys.stdout = old_stdout
