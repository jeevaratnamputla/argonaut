import json
from slack import post_message_to_slack, get_bot_user_id, verify_slack_request, get_thread_ts_from_reaction
#from elastic import ensure_index_exists, get_es_client, update_elasticsearch, set_summary_index_es, get_thread_messages, update_reaction
from generic_storage import  update_message, set_summary_index, get_thread_messages
#from chatgpt import get_chatgpt_response
from call_llm import get_llm_response

def summarize_conversation(thread_ts, max_response_tokens, temperature, logger):
    role = "user"
    content = (
        "Summarize this conversation and preserve critical information"
    )

    update_message( thread_ts, role, content, logger=logger)

    messages = get_thread_messages( thread_ts, logger=logger)
    logger.debug("Summarizing: %s", json.dumps(messages))
    logger.info("Summarizing...........................................................................")

    response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
    role = "assistant"
    content = response
    update_message( thread_ts, role, content, logger=logger)
    set_summary_index(thread_ts,logger=logger)
    return response