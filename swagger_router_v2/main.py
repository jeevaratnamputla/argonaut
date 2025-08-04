from fastapi import FastAPI, Query
from swagger_parser import SwaggerIndex

app = FastAPI()
index = SwaggerIndex("swagger.json")

@app.get("/match")
def match_endpoint(query: str = Query(...)):
    results = index.search_by_tag(query)
    return {"matches": results[:5]}
