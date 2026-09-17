#!/usr/bin/env python3
"""
ISA-JSON Validation Script

This script validates ISA-JSON files using the isatools library.
It provides CLI options for different output formats and verbosity levels.

Usage:
    python scripts/isa_json_validation.py path/to/file.json
    python scripts/isa_json_validation.py --verbose path/to/file.json
    python scripts/isa_json_validation.py --json path/to/file.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

try:
    from isatools import isajson
except ImportError:
    print("Error: isatools is not installed. Install it with: pip install isatools>=0.16.0")
    sys.exit(2)


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"


def print_colored(message: str, color: str = Colors.RESET, use_color: bool = True) -> None:
    """
    Print a colored message to stdout.

    Args:
        message: The message to print
        color: ANSI color code
        use_color: Whether to use colors (disabled with --no-color)
    """
    if use_color:
        print(f"{color}{message}{Colors.RESET}")
    else:
        print(message)


def _get_error_code(entry) -> int:
    """Extract numeric error code from an error/warning entry."""
    if hasattr(entry, "code"):
        return entry.code
    if isinstance(entry, dict):
        return entry.get("code", 0)
    return 0


def validate_file(
    file_path: Path, verbose: bool = False, ignore_codes: set = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate a single ISA-JSON file.

    Args:
        file_path: Path to the ISA-JSON file
        verbose: Whether to print verbose output
        ignore_codes: Set of error codes to ignore (e.g. {4002})

    Returns:
        Tuple of (is_valid, validation_report)
    """
    if ignore_codes is None:
        ignore_codes = set()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Use isatools to validate the ISA-JSON
            report = isajson.validate(f)
            # Check if the report contains any errors (not just that we ran successfully)
            errors = report.errors if hasattr(report, "errors") else report.get("errors", [])
            # Filter out ignored error codes
            real_errors = [e for e in errors if _get_error_code(e) not in ignore_codes]
            has_critical = any(_get_error_code(e) == 2 for e in real_errors)
            is_valid = len(real_errors) == 0 and not has_critical
            return is_valid, report
    except FileNotFoundError:
        print_colored(f"Error: File not found: {file_path}", Colors.RED)
        return False, {"error": "File not found"}
    except json.JSONDecodeError as e:
        print_colored(f"Error: Invalid JSON in {file_path}: {e}", Colors.RED)
        return False, {"error": f"Invalid JSON: {e}"}
    except Exception as e:
        print_colored(f"Error validating {file_path}: {e}", Colors.RED)
        return False, {"error": str(e)}


def format_report(report: Dict[str, Any], verbose: bool = False, use_color: bool = True) -> None:
    """
    Format and print the validation report.

    Args:
        report: Validation report from isatools
        verbose: Whether to print verbose output
        use_color: Whether to use colored output
    """
    if "error" in report:
        # Error occurred during validation (file not found, invalid JSON, etc.)
        return

    # Check if validation passed
    if report.get("passed", False):
        print_colored("✓ Validation PASSED", Colors.GREEN, use_color)
    else:
        print_colored("✗ Validation FAILED", Colors.RED, use_color)

    # Print errors if any
    errors = report.get("errors", [])
    if errors:
        print_colored(f"\n{len(errors)} Error(s) found:", Colors.RED, use_color)
        for i, error in enumerate(errors, 1):
            print_colored(f"  {i}. {error}", Colors.RED, use_color)

    # Print warnings if any
    warnings = report.get("warnings", [])
    if warnings:
        print_colored(f"\n{len(warnings)} Warning(s) found:", Colors.YELLOW, use_color)
        for i, warning in enumerate(warnings, 1):
            print_colored(f"  {i}. {warning}", Colors.YELLOW, use_color)

    # Print verbose details if requested
    if verbose:
        print_colored("\n--- Full Report ---", Colors.CYAN, use_color)
        print(json.dumps(report, indent=2))


def format_report_json(report: Dict[str, Any]) -> str:
    """
    Format the validation report as JSON.

    Args:
        report: Validation report from isatools

    Returns:
        JSON string representation of the report
    """
    return json.dumps(report, indent=2)


def main():
    """Main entry point for the validation script."""
    parser = argparse.ArgumentParser(
        description="Validate ISA-JSON files using isatools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/isa_json_validation.py investigations/inv_1/studies/study_1/study.json
    python scripts/isa_json_validation.py --verbose investigations/inv_1/studies/study_1/study.json
    python scripts/isa_json_validation.py --json investigations/inv_1/studies/study_1/study.json
    python scripts/isa_json_validation.py --no-color investigations/inv_1/studies/study_1/study.json
    python scripts/isa_json_validation.py --ignore-codes 4002 file.json
        """,
    )

    parser.add_argument("file_path", type=str, help="Path to the ISA-JSON file to validate")

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print verbose output including full validation report",
    )

    parser.add_argument(
        "--json", "-j", action="store_true", help="Output validation report in JSON format"
    )

    parser.add_argument("--no-color", action="store_true", help="Disable colored output")

    parser.add_argument(
        "--ignore-codes",
        type=int,
        nargs="*",
        default=[],
        help="Error codes to ignore during validation (e.g. --ignore-codes 4002)",
    )

    args = parser.parse_args()

    # Convert file path to Path object
    file_path = Path(args.file_path)
    ignore_codes = set(args.ignore_codes) if args.ignore_codes else set()

    # Validate the file
    is_valid, report = validate_file(file_path, args.verbose, ignore_codes)

    if not is_valid:
        # File validation failed (not the ISA-JSON validation itself)
        sys.exit(2)

    # Output the report
    if args.json:
        print(format_report_json(report))
    else:
        format_report(report, args.verbose, not args.no_color)

    # Exit with appropriate code
    # 0 = success, 1 = validation failed, 2 = file error
    if report.get("passed", False):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
