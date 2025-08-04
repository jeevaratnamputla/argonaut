import json
from pathlib import Path
from typing import List, Dict, Any, Union
from classify_payload_source import classify_payload_source


def load_required_fields(filename: str, payload: Dict[str, Any] = None) -> List[str]:
    """Loads field names from file or calls classify_payload_source if missing."""
    path = Path(filename)
    if not path.exists():
        print(f"⚠️ Field file not found: {filename}")
        if payload is not None:
            print("🔄 Calling classify_payload_source to generate it...")
            try:
                from classify_payload_source import classify_payload_source
                classify_payload_source(payload)
            except ImportError:
                raise ImportError("Could not import classify_payload_source.py. Make sure it's available.")
        else:
            raise FileNotFoundError("No payload provided to generate missing field file.")

        if not path.exists():
            raise FileNotFoundError(f"Still missing after generation attempt: {filename}")

    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def check_fields_exist(payload: Dict[str, Any], required_fields: List[str]) -> Dict[str, bool]:
    """Checks which required fields exist in the payload."""
    result = {}
    for field in required_fields:
        parts = field.split(".")
        current = payload
        found = True
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        result[field] = found
    return result


def check_fields(payload: Union[Dict[str, Any], List[Any]], fields_file: str) -> Dict[str, bool]:
    """Can be called from another script with payload + field file."""
    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    required_fields = load_required_fields(fields_file, payload)
    return check_fields_exist(payload, required_fields)


def main():
    import sys

    if len(sys.argv) != 3:
        print("Usage: python check_payload_fields.py <fields_file> <payload_json_file>")
        exit(1)

    fields_file = sys.argv[1]
    payload_file = sys.argv[2]

    with open(payload_file, "r", encoding="utf-8") as f:
        payload = json.load(f)

    result = check_fields(payload, fields_file)

    print("\nField Presence Report:")
    for field, exists in result.items():
        status = "✅ Found" if exists else "❌ Missing"
        print(f"{field}: {status}")


if __name__ == "__main__":
    main()
