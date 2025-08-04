import os
from openai import OpenAI
#from elastic import get_thread_messages  # adjust if the function is elsewhere
from generic_storage import get_thread_messages 
def get_chatgpt_response(thread_ts, max_response_tokens, temperature, logger=None):
    """
    Get a response from ChatGPT based on the conversation stored in Elasticsearch.
    """
    try:
        # Retrieve previous messages from Elasticsearch
        messages_from_es = get_thread_messages(thread_ts, logger=logger)

        chat_messages = []
        for msg in messages_from_es:
            chat_messages.append({
                "role": msg.get("role", ""),
                "content": msg.get("content", "")
            })

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        completion = client.chat.completions.create(
            messages=chat_messages,
            model=os.getenv("model", "gpt-4.1"),
            max_tokens=max_response_tokens,
            temperature=temperature,
            top_p=float(os.getenv("top_p", 0.5))
        )

        response_content = completion.choices[0].message.content

        if logger:
            logger.debug("ChatGPT response: %s", completion.choices[0])
            logger.info("ChatGPT responded")

        return response_content

    except Exception as e:
        if logger:
            logger.error(f"Error in get_chatgpt_response: {e}")
        return "Error processing your request."
