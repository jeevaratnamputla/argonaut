
# test_review_command.py
import argparse
import json
import logging
from typing import Any, Dict, List, Optional

from review_argocd_command import review_command

def run_review(cmd: str, logger: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """Run the argocd command review and return a JSON-serializable dict.

    Parameters
    ----------
    cmd : str
        The full command string to review (e.g., "argocd app get myapp").
    logger : Optional[logging.Logger]
        A logger to use for internal debug logs (optional).
    """
    res = review_command(cmd, logger=logger)

    # Aggregate issues: errors, warnings, unknown flags, missing values
    issues: List[str] = []
    issues.extend(res.get("errors", []) or [])
    issues.extend(res.get("warnings", []) or [])
    for uf in res.get("unknown_flags", []) or []:
        issues.append(f"Unknown flag: {uf}")
    for mv in res.get("missing_flag_values", []) or []:
        issues.append(f"Missing value for flag: {mv}")

    out: Dict[str, Any] = {
        "input_command": cmd,
        "valid": bool(res.get("valid")),
        "parsed_path": res.get("parsed_path") or [],
        "issues": issues,
        "suggestions": res.get("suggestions") or [],
        "unknown_flags": res.get("unknown_flags") or [],
        "missing_flag_values": res.get("missing_flag_values") or [],
        "corrected_command": res.get("corrected_command"),
        # Subcommand-specific flags (not global), both compact and detailed forms
        "available_flags": res.get("available_flags") or [],
        "available_flags_with_help": res.get("available_flags_with_help") or [],
    }
    return out

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Review an argocd command and output JSON.")
    p.add_argument(
        "--cmd",
        help="Full argocd command string to review.",
        default="argocd app manifest --app myapp -n argocd",
    )
    p.add_argument(
        "--log-level",
        default="WARNING",
        choices=["CRITICAL","ERROR","WARNING","INFO","DEBUG"],
        help="Logging verbosity for the script itself.",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output with indentation.",
    )
    return p

if __name__ == "__main__":
    ap = _build_argparser()
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger("test_review")

    result = run_review(args.cmd, logger=logger)
    if args.pretty:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
