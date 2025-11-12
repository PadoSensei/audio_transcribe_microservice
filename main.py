import os
import whisper
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.responses import JSONResponse

# --- Initialize FastAPI ---
app = FastAPI()

# --- Load Whisper Model ---
print("Loading Whisper model...")
model = whisper.load_model("base")
print("Whisper model loaded successfully!")

# --- Endpoints ---
@app.get("/")
async def root():
    return {"status": "ok", "message": "WhisperService is running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "ffmpeg": "available"}

@app.post("/submit_job")
async def transcribe_audio(
    file: UploadFile = File(...),
    x_service_api_key: str = Header(None, alias="X-Service-API-Key")
):
    expected_key = os.getenv("SERVICE_API_KEY", "test-key")
    if x_service_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    try:
        print(f"Transcribing {file.filename}...")
        result = model.transcribe(temp_path, fp16=False)
        transcript = result["text"]
        print(f"Transcription complete: {transcript[:50]}...")
        
        return JSONResponse(content={
            "status": "success",
            "transcript": transcript
        })
    
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# Run with port from environment
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)