import json
from check_email_payload_fields import check_fields as check_email_fields
from check_slack_payload_fields import check_fields as check_slack_fields

def email_handler(payload):
    print("📩 Handling email payload")
    print("Subject:", payload.get("Subject"))
    print("From:", payload.get("From"))
    print("Snippet:", payload.get("snippet"))

def slack_handler(payload):
    print("💬 Handling Slack payload")
    event = payload.get("event", {})
    print("Slack User:", event.get("user"))
    print("Text:", event.get("text"))
    print("Timestamp:", event.get("ts"))

def check_payload_type(payload):
    """
    Determine if the payload is from email or slack based on required fields.
    Calls the appropriate handler.
    """
    email_fields_file = "check_email_payload_fields.txt"
    slack_fields_file = "check_slack_payload_fields.txt"

    email_result = check_email_fields(payload, email_fields_file)
    slack_result = check_slack_fields(payload, slack_fields_file)

    email_score = sum(email_result.values())
    slack_score = sum(slack_result.values())

    print("\nEmail Match Score:", email_score)
    print("Slack Match Score:", slack_score)
    #slack_score = 0
    if email_score > slack_score:
        email_handler(payload)
    elif slack_score > email_score:
        slack_handler(payload)
    else:
        print("❓ Unable to confidently determine source of payload.")

def main():
    import sys
    if len(sys.argv) != 2:
        print("Usage: python check_payload_type.py <payload_json_file>")
        return

    payload_file = sys.argv[1]
    with open(payload_file, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        payload = payload[0]

    check_payload_type(payload)

if __name__ == "__main__":
    main()
