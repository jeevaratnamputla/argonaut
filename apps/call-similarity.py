from similarity import semantic_similarity

text1 = "Why is application APP having issues"
text2 = "Is application APP having issues"

score = semantic_similarity(text1, text2)
print(f"Semantic similarity score: {score}")
