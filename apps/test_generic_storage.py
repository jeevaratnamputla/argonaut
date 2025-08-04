from generic_storage import ensure_index_exists, update_message, set_summary_index, get_thread_messages, update_reaction

def main():
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("GenericStorage")

    thread_ts = "1234567890.123456"
    update_message(thread_ts, "user", "Generic message", logger)
    set_summary_index(thread_ts, logger)
    update_reaction(thread_ts, "✅", logger)
    messages = get_thread_messages(thread_ts, logger)
    logger.info(messages)

if __name__ == "__main__":
    main()
