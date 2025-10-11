import os
from openai import OpenAI
from generic_storage import get_thread_messages

# Define the base URL for Gemini's OpenAI compatibility layer
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

def get_llm_response(thread_ts, max_response_tokens, temperature, logger=None):
    """
    Get a response from the available LLM (OpenAI or Gemini) based on 
    the API keys present in the environment.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    client = None
    model_to_use = None

    # --- 1. Determine which provider to use ---
    if openai_key:
        provider = "OpenAI"
        client = OpenAI(api_key=openai_key)
        # Use an environment variable for the model, defaulting to a common OpenAI model
        model_to_use = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
    elif gemini_key:
        provider = "Gemini"
        # Initialize the client for Gemini using the OpenAI compatibility layer
        client = OpenAI(
            api_key=gemini_key,
            base_url=GEMINI_BASE_URL
        )
        # Use an environment variable for the model, defaulting to a common Gemini model
        model_to_use = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        
    else:
        # If neither key is found, log an error and return
        error_msg = "No API key found for OpenAI or Gemini. Cannot proceed."
        if logger:
            logger.error(error_msg)
        return "Error: No API key configured for any supported LLM."

    if logger:
        logger.info(f"Using provider: {provider} with model: {model_to_use}")

    # --- 2. Prepare Messages and Call the API ---
    try:
        # Retrieve previous messages (same logic as before)
        messages_from_es = get_thread_messages(thread_ts, logger=logger)

        chat_messages = []
        for msg in messages_from_es:
            chat_messages.append({
                "role": msg.get("role", ""),
                "content": msg.get("content", "")
            })

        # The core API call remains the same (due to OpenAI compatibility)
        completion = client.chat.completions.create(
            messages=chat_messages,
            model=model_to_use,
            max_tokens=max_response_tokens,
            temperature=temperature,
            # Use top_p from environment or default
            top_p=float(os.getenv("top_p", 0.5)) 
        )

        response_content = completion.choices[0].message.content

        if logger:
            logger.debug(f"{provider} completion response: %s", completion.choices[0])
            logger.info(f"{provider} responded successfully.")

        return response_content

    except Exception as e:
        if logger:
            logger.error(f"Error in get_llm_response with {provider}: {e}")
        return "Error processing your request."

# Note: Remember to update the function name everywhere it is called in your codebase.
