from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import json

from engine.analyzer import analyze_campaign_data

app = FastAPI(
    title="Thai Thai Ads Agent",
    description="AI-powered analysis for Google Ads campaigns",
    version="1.0.0"
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze_endpoint(request: Request):
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data provided.")

    try:
        # Pass the raw dictionary data to the analyzer engine
        # The engine must return a python dictionary that can be converted to JSON directly
        result_dict = await analyze_campaign_data(data)
        
        # Return strict raw JSON (FastAPI's JSONResponse does this)
        return JSONResponse(content=result_dict)
    except Exception as e:
        # In a real app we'd log this properly
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
