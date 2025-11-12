import os
import whisper
import uuid
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse

# --- Initialize FastAPI ---
app = FastAPI()

# --- Load Whisper Model ---
print("Loading Whisper model...")
model = whisper.load_model("base")
print("Whisper model loaded successfully!")

# --- Background Task Function ---
def process_transcription(job_id: str, temp_filename: str, webhook_url: str = None):
    """Process transcription in background and optionally send to webhook"""
    print(f"[{job_id}] Starting transcription...")
    try:
        result = model.transcribe(temp_filename, fp16=False)
        transcript = result["text"]
        print(f"[{job_id}] Transcription complete: {transcript[:50]}...")
        
        # If webhook provided, send result back
        if webhook_url:
            payload = {"job_id": job_id, "transcript": transcript}
            with httpx.Client(timeout=30.0) as client:
                response = client.post(webhook_url, json=payload)
                print(f"[{job_id}] Sent to webhook: {response.status_code}")
        
        return transcript
        
    except Exception as e:
        print(f"[{job_id}] Error: {e}")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

# --- Endpoints ---
@app.get("/")
async def root():
    return {"status": "ok", "message": "WhisperService is running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "ffmpeg": "available"}

@app.post("/submit_job")
async def submit_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_service_api_key: str = Header(None, alias="X-Service-API-Key")
):
    """Submit transcription job - returns immediately"""
    expected_key = os.getenv("SERVICE_API_KEY", "test-key")
    if x_service_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    job_id = str(uuid.uuid4())
    temp_path = f"/tmp/{job_id}_{file.filename}"
    
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Add to background tasks
    background_tasks.add_task(process_transcription, job_id, temp_path)
    
    print(f"[{job_id}] Job submitted, processing in background")
    return JSONResponse(content={
        "status": "processing",
        "job_id": job_id,
        "message": "Transcription started"
    })

@app.post("/transcribe_sync")
async def transcribe_sync(
    file: UploadFile = File(...),
    x_service_api_key: str = Header(None, alias="X-Service-API-Key")
):
    """Synchronous transcription - for testing only"""
    expected_key = os.getenv("SERVICE_API_KEY", "test-key")
    if x_service_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    try:
        print(f"Transcribing {file.filename} synchronously...")
        result = model.transcribe(temp_path, fp16=False)
        transcript = result["text"]
        
        return JSONResponse(content={
            "status": "success",
            "transcript": transcript
        })
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")