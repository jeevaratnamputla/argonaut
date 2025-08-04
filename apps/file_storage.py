import os
import json
from datetime import datetime, timezone

FS_INDEX = os.getenv("FS_INDEX", "file_index")
os.makedirs(FS_INDEX, exist_ok=True)


def _get_file_path(thread_ts):
    return os.path.join(FS_INDEX, f"{thread_ts}.json")


def ensure_index_exists(logger=None):
    """Ensure the index folder exists."""
    os.makedirs(FS_INDEX, exist_ok=True)
    if logger:
        logger.info(f"File index folder '{FS_INDEX}' ensured.")


def update_file_storage(thread_ts, role, content, logger=None):
    """Update or create a JSON file for the given thread_ts."""
    file_path = _get_file_path(thread_ts)
    new_message = {"role": role, "content": content}

    if os.path.exists(file_path):
        with open(file_path, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["messages"].append(new_message)
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
        if logger:
            logger.info(f"Thread {thread_ts} updated with message from {role}.")
    else:
        data = {
            "messages": [new_message],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if logger:
            logger.info(f"New thread {thread_ts} created with message from {role}.")


def set_summary_index(thread_ts, logger=None):
    """Set the summary_index field in the file."""
    file_path = _get_file_path(thread_ts)
    if not os.path.exists(file_path):
        if logger:
            logger.warning(f"File {file_path} not found.")
        return False

    with open(file_path, "r+", encoding="utf-8") as f:
        data = json.load(f)
        messages = data.get("messages", [])
        if not messages:
            if logger:
                logger.warning(f"No messages in thread {thread_ts}.")
            return False
        summary_index = len(messages) - 1
        data["summary_index"] = summary_index
        f.seek(0)
        json.dump(data, f, indent=2)
        f.truncate()
    if logger:
        logger.info(f"summary_index set to {summary_index} for thread {thread_ts}.")
    return True


def get_thread_messages(thread_ts, logger=None):
    """Retrieve conversation messages for a given thread_ts."""
    file_path = _get_file_path(thread_ts)
    save_token_use_summary = os.getenv("SAVE_TOKEN_USE_SUMMARY", "false").lower() == "true"

    if not os.path.exists(file_path):
        if logger:
            logger.info(f"Thread {thread_ts} not found.")
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = data.get("messages", [])
    if not save_token_use_summary:
        return messages

    summary_index = data.get("summary_index")
    if summary_index is None or summary_index >= len(messages):
        if logger:
            logger.warning(f"No valid summary_index for {thread_ts}.")
        return messages

    try:
        return [messages[0], messages[summary_index]] + messages[summary_index + 1:]
    except Exception as e:
        if logger:
            logger.error(f"Error building summary-based context: {e}")
        return messages


def update_reaction(thread_ts, reaction, logger=None):
    """Update the reaction field in the file."""
    file_path = _get_file_path(thread_ts)
    if not os.path.exists(file_path):
        if logger:
            logger.warning(f"Thread {thread_ts} not found.")
        return False

    with open(file_path, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data["reaction"] = reaction
        f.seek(0)
        json.dump(data, f, indent=2)
        f.truncate()
    if logger:
        logger.info(f"Reaction updated for thread {thread_ts}.")
    return True

def main():
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("FileStorageTest")

    thread_ts = "1234567890.123456"
    role = "user"
    content = "Hello from file storage!"

    # Ensure the index folder exists
    ensure_index_exists(logger)

    # Add a message
    update_file_storage(thread_ts, role, content, logger)

    # Set summary index
    set_summary_index(thread_ts, logger)

    # Retrieve and print messages
    messages = get_thread_messages(thread_ts, logger)
    logger.info(f"Retrieved messages for {thread_ts}: {messages}")

    # Update reaction
    update_reaction(thread_ts, "👍", logger)

    # Verify full document content
    file_path = os.path.join(FS_INDEX, f"{thread_ts}.json")
    with open(file_path, "r", encoding="utf-8") as f:
        logger.info(f"Final content of {file_path}:\n{f.read()}")

if __name__ == "__main__":
    main()
