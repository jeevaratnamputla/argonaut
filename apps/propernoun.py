import spacy

# Load the English language model once
nlp = spacy.load("en_core_web_sm")

def replace_proper_nouns(sentence):
    doc = nlp(sentence)

    # Contextual common noun map
    common_noun_context = {
        "application": "APP",
        "namespace": "NS",
        "cluster": "CLUSTER",
        "repository": "REPO",
        "branch": "BRANCH",
        "path": "PATH",
        "software": "ITEM",
        "": "ENTITY"
    }

    common_nouns = set(common_noun_context.keys())
    modified_sentence = sentence
    replacements = []

    i = 0
    while i < len(doc) - 1:
        token = doc[i]
        token_lower = token.text.lower()

        if token.pos_ == "NOUN" and token_lower in common_nouns:
            replacement = common_noun_context.get(token_lower, "ENTITY")
            start_idx = i + 1
            end_idx = start_idx

            # If the value is in quotes (single or double)
            if doc[start_idx].text[0] in {'"', "'"}:
                quote_char = doc[start_idx].text[0]
                full_quote = [doc[start_idx].text]
                end_idx += 1
                while end_idx < len(doc):
                    full_quote.append(doc[end_idx].text)
                    if doc[end_idx].text.endswith(quote_char):
                        break
                    end_idx += 1
                start = doc[start_idx].idx
                end = doc[end_idx].idx + len(doc[end_idx])
                replacements.append((start, end, replacement))
                i = end_idx + 1
                continue

            # Handle paths or plain spans
            proper_noun_parts = []
            while end_idx < len(doc):
                next_token = doc[end_idx]
                if next_token.pos_ in {"AUX", "VERB", "PUNCT"}:
                    break
                if next_token.pos_ in {"NOUN", "PROPN", "NUM", "VERB", "ADV"} or \
                   next_token.text in {"-", "/", "."} or \
                   next_token.text.startswith("/") or \
                   (next_token.pos_ == "ADP" and next_token.text in {"for", "in", "on"}) or \
                   next_token.text.isalnum():
                    proper_noun_parts.append(next_token.text)
                    end_idx += 1
                else:
                    break

            if proper_noun_parts:
                span_text = doc[start_idx:end_idx].text
                start = doc[start_idx].idx
                end = doc[end_idx - 1].idx + len(doc[end_idx - 1])
                has_trailing_space = end < len(sentence) and sentence[end] == " "
                if has_trailing_space:
                    replacement += " "
                replacements.append((start, end, replacement))
                i = end_idx
            else:
                i += 1
        else:
            i += 1

    # Apply replacements in reverse order
    for start, end, replacement in reversed(replacements):
        modified_sentence = modified_sentence[:start] + replacement + modified_sentence[end:]

    return modified_sentence
