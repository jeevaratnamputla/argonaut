# Swagger Tag Router

This script:
1. Loads swagger.json
2. Extracts API service tags
3. Matches user intent to the best tag using OpenAI (fallbacks to local logic if needed)

## Usage

1. Place your `swagger.json` inside the `swagger_tag_router` folder
2. Set your OpenAI key:
   export OPENAI_API_KEY=sk-...

3. Run:
   python parser.py
