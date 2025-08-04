# elastic.py
from datetime import datetime, timezone
import os
import logging
from elasticsearch import Elasticsearch

ES_URL = os.getenv("ES_URL")
ES_USER = os.getenv("ES_USER")
ES_PWD = os.getenv("ES_PWD")
ES_CA_CERTS = os.getenv("es_ca_certs")
ES_INDEX = os.getenv("es_index")

def get_es_client():
    return Elasticsearch(
        ES_URL,
        basic_auth=(ES_USER, ES_PWD),
        verify_certs=True,
        ca_certs=ES_CA_CERTS
    )

def ensure_index_exists(logger=None):
    """Create the Elasticsearch index with mappings if it doesn't exist."""
    es = get_es_client()

    if not es.indices.exists(index=ES_INDEX):
        mappings = {
            "mappings": {
                "properties": {
                    "thread_ts": {"type": "keyword"},
                    "messages": {
                        "type": "nested",
                        "properties": {
                            "role": {"type": "keyword"},
                            "content": {"type": "text"}
                        }
                    },
                    "summary_index": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "reaction": {"type": "text"}
                }
            }
        }
        es.indices.create(index=ES_INDEX, body=mappings)
        if logger:
            logger.info(f"Index '{ES_INDEX}' created with mappings.")

def update_elasticsearch(es, thread_ts, role, content, logger=None):
    """Updates an Elasticsearch thread with a new message, or creates it if not found."""
    esresponse = es.get(index=ES_INDEX, id=thread_ts, ignore=404)

    if esresponse.get('found'):
        # Get existing messages
        thread_data = esresponse['_source']
        messages = thread_data.get('messages', [])

        # Append the new message
        new_message = {
            "role": role,
            "content": content
        }
        messages.append(new_message)

        # Update the thread
        es.update(index=ES_INDEX, id=thread_ts, body={"doc": {"messages": messages}})
        if logger:
            logger.info(f"Thread {thread_ts} updated with message from {role}.")
    else:
        if logger:
            logger.info(f"Thread {thread_ts} not found. Creating a new thread.")

        new_thread_data = {
            "messages": [{
                "role": role,
                "content": content
            }],
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        es.index(index=ES_INDEX, id=thread_ts, body=new_thread_data)
        if logger:
            logger.info(f"New thread {thread_ts} created with message from {role}.")

def set_summary_index_es(es, thread_ts, logger=None):
    """
    Set the summary_index field to the highest index in the messages array
    for the given thread_ts document in Elasticsearch.
    """
    try:
        esresponse = es.get(index=ES_INDEX, id=thread_ts, ignore=404)

        if not esresponse.get('found'):
            if logger:
                logger.warning(f"Document with thread_ts '{thread_ts}' not found.")
            return False

        thread_data = esresponse['_source']
        messages = thread_data.get("messages", [])

        if not messages:
            if logger:
                logger.warning(f"No messages found in thread '{thread_ts}'. Cannot set summary_index.")
            return False

        highest_index = len(messages) - 1

        es.update(index=ES_INDEX, id=thread_ts, body={
            "doc": {
                "summary_index": highest_index
            }
        })

        if logger:
            logger.info(f"summary_index set to {highest_index} for thread {thread_ts}.")
        return True

    except Exception as e:
        if logger:
            logger.error(f"Error setting summary_index for thread {thread_ts}: {e}")
        return False

def get_thread_messages(es, thread_ts, logger=None):
    """
    Retrieve and return conversation messages for a given thread_ts.
    If SAVE_TOKEN_USE_SUMMARY env var is 'true', return:
      - messages[0] (system)
      - messages[summary_index] (summary)
      - all messages after summary_index
    Else, return full message list.
    """
    save_token_use_summary = os.getenv("SAVE_TOKEN_USE_SUMMARY", "false").lower() == "true"
    try:
        esresponse = es.get(index=ES_INDEX, id=thread_ts, ignore=404)
    except Exception as e:
        if logger:
            logger.error(f"Error retrieving thread {thread_ts} from Elasticsearch: {e}")
        return []

    if not esresponse.get('found'):
        if logger:
            logger.info(f"Thread {thread_ts} not found.")
        return []

    thread_data = esresponse['_source']
    messages = thread_data.get('messages', [])

    if not messages:
        if logger:
            logger.info(f"Thread {thread_ts} found, but no messages are available.")
        return []

    if not save_token_use_summary:
        return messages

    summary_index = thread_data.get('summary_index')
    if summary_index is None or not isinstance(summary_index, int) or summary_index >= len(messages):
        if logger:
            logger.warning(f"No valid summary_index found for thread {thread_ts}. Returning full messages.")
        return messages

    try:
        minimal_context = [messages[0]]  # System message
        minimal_context.append(messages[summary_index])  # Summary message
        minimal_context.extend(messages[summary_index + 1:])  # Remaining messages
        if logger:
            #logger.info(f"Using compressed summary-based prompt for thread {thread_ts}.")
            logger.debug(f"Summary-based context for thread {thread_ts}: {minimal_context}")
        return minimal_context
    except Exception as e:
        if logger:
            logger.error(f"Error building summary-based context for thread {thread_ts}: {e}")
        return messages

def update_reaction(es, index_name, thread_ts, reaction, logger=None):
    try:
        result = es.update(index=index_name, id=thread_ts, body={
            "doc": {
                "reaction": reaction
            }
        }, refresh=True)

        if logger:
            logger.info("Directly updated reaction for thread_ts %s: %s", thread_ts, result)
        return result

    except Exception as e:
        if logger:
            logger.exception("Failed to update reaction for thread_ts %s: %s", thread_ts, e)
        return None
