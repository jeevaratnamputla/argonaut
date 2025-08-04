import os

# Import both storage backends
import file_storage
import elastic  # Make sure this is your elastic.py module

STORAGE_BACKENDS = os.getenv("STORAGE_BACKENDS", "file_storage").split(",")

def ensure_index_exists(logger=None):
    for backend in STORAGE_BACKENDS:
        if backend == "file_storage":
            file_storage.ensure_index_exists(logger)
        elif backend == "elasticsearch":
            elastic.ensure_index_exists(logger)

def update_message(thread_ts, role, content, logger=None):
    for backend in STORAGE_BACKENDS:
        if backend == "file_storage":
            file_storage.update_file_storage(thread_ts, role, content, logger)
        elif backend == "elasticsearch":
            es = elastic.get_es_client()
            elastic.update_elasticsearch(es, thread_ts, role, content, logger)

def set_summary_index(thread_ts, logger=None):
    for backend in STORAGE_BACKENDS:
        if backend == "file_storage":
            file_storage.set_summary_index(thread_ts, logger)
        elif backend == "elasticsearch":
            es = elastic.get_es_client()
            elastic.set_summary_index_es(es, thread_ts, logger)

def get_thread_messages(thread_ts, logger=None):
    for backend in STORAGE_BACKENDS:
        if backend == "file_storage":
            return file_storage.get_thread_messages(thread_ts, logger)
        elif backend == "elasticsearch":
            es = elastic.get_es_client()
            return elastic.get_thread_messages(es, thread_ts, logger)
    return []

def update_reaction(thread_ts, reaction, logger=None):
    for backend in STORAGE_BACKENDS:
        if backend == "file_storage":
            file_storage.update_reaction(thread_ts, reaction, logger)
        elif backend == "elasticsearch":
            es = elastic.get_es_client()
            elastic.update_reaction(es, os.getenv("es_index"), thread_ts, reaction, logger)
