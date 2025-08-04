from propernoun import replace_proper_nouns

text = 'The repository "for-testing" is available but branch "main" is too. The path "/app/dest" is missing'
modified = replace_proper_nouns(text)
print("Modified Output:", modified)
