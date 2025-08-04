from sentence_transformers import SentenceTransformer, util

# Load the model only once
_model = SentenceTransformer('all-MiniLM-L6-v2')

def semantic_similarity(text1: str, text2: str) -> float:
    """
    Returns a semantic similarity score between two texts (0 to 1).
    """
    embedding1 = _model.encode(text1, convert_to_tensor=True)
    embedding2 = _model.encode(text2, convert_to_tensor=True)
    score = util.cos_sim(embedding1, embedding2).item()
    return round(score, 4)
