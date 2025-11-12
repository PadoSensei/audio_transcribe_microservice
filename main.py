import os
import whisper
import uuid
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks, Form
from fastapi.responses import JSONResponse

app = FastAPI()

print("Loading Whisper model...")
model = whisper.load_model("base")
print("Whisper model loaded successfully!")

# Background task
def process_transcription(job_id: str, temp_filename: str, chat_id: str, webhook_url: str):
    """Process transcription and send to n8n webhook"""
    print(f"[{job_id}] Starting transcription for chat {chat_id}...")
    try:
        result = model.transcribe(temp_filename, fp16=False)
        transcript = result["text"]
        print(f"[{job_id}] Transcription complete: {transcript[:50]}...")
        
        # Send to n8n webhook
        payload = {
            "job_id": job_id,
            "chat_id": chat_id,
            "transcript": transcript
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(webhook_url, json=payload)
            print(f"[{job_id}] Sent to webhook: {response.status_code}")
        
    except Exception as e:
        print(f"[{job_id}] Error: {e}")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

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
    chat_id: str = Form(...),  # NEW: Need chat_id from n8n
    webhook_url: str = Form(...),  # NEW: Need webhook URL from n8n
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
    
    # Add to background tasks with callback info
    background_tasks.add_task(process_transcription, job_id, temp_path, chat_id, webhook_url)
    
    print(f"[{job_id}] Job submitted for chat {chat_id}")
    return JSONResponse(content={
        "status": "processing",
        "job_id": job_id,
        "message": "Transcription started"
    })

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")