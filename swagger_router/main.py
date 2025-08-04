from fastapi import FastAPI, Query
from swagger_parser import SwaggerIndex

app = FastAPI()
index = SwaggerIndex("swagger.json")

@app.get("/match")
def match_endpoint(query: str = Query(..., description="Describe the API task")):
    results = index.search(query)
    return {"matches": results[:5]}
