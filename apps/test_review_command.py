import logging
from execute_run_command import execute_run_command
from review_argocd_command import review_command
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_review")
# assuming execute_run_command(cmd, logger) exists


cmd = "argocd app manifest --app myapp -n argocd"
res = review_command(cmd, logger=logger)

if not res["valid"]:
    logger.warning("Issues: %s", res["errors"] or res["warnings"])
    if res.get("corrected_command"):
        logger.info("Suggested fix: %s", res["corrected_command"])
else:
    logger.info("Command looks good.")
