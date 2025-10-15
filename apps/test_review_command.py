# test_review_command.py
import logging
from review_argocd_command import review_command

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_review")

cmd = "argocd app get myapp"
res = review_command(cmd, logger=logger)

issues = []
issues.extend(res.get("errors", []))
issues.extend(res.get("warnings", []))
for uf in res.get("unknown_flags", []):
    issues.append(f"Unknown flag: {uf}")
for mv in res.get("missing_flag_values", []):
    issues.append(f"Missing value for flag: {mv}")

if issues:
    logger.warning("Issues: %s", issues)
else:
    logger.info("No issues found.")

if res.get("suggestions"):
    logger.info("Suggestions: %s", res["suggestions"])

corr = res.get("corrected_command")
if corr:
    logger.info("Suggested fix: %s", corr)

print("\nSubcommand-specific flags (not global):")
flags = res.get("available_flags_with_help") or []
if not flags:
    print("  (none parsed)")
else:
    for f in flags:
        names = ", ".join(f["names"])
        suffix = " (value)" if f["takes_value"] else ""
        print(f"  - {names}{suffix}: {f['desc']}")
