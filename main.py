import os
import sys
import whisper
import uuid
import httpx  # A modern async HTTP client, better for this than 'requests'
import time
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY")
# N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL") # We need this to send the result back

if not SERVICE_API_KEY:
    print("FATAL ERROR: SERVICE_API_KEY environment variable not set.")
    sys.exit(1)

# --- Global Model Loading ---
print("Loading Whisper model...")
model = whisper.load_model("base")
print("Whisper model loaded.")

# --- In-Memory "Job" Storage (Simple for this use case) ---
# In a larger system, you'd use a real database like Redis or a database.
jobs = {}

# --- Initialize FastAPI ---
app = FastAPI()

# --- Background Worker Function ---
def process_transcription(job_id: str, temp_filename: str, chat_id: str):
    """
    This function runs in the background. It transcribes the audio
    and then sends the result back to n8n.
    """
    print(f"[{job_id}] Background task started.")
    
    try:
        # 1. Run the transcription (the slow part)
        result = model.transcribe(temp_filename, fp16=False)
        transcript_text = result["text"]
        print(f"[{job_id}] Transcription complete.")
        
        # 2. Store the result (optional but good practice)
        jobs[job_id] = {"status": "completed", "transcript": transcript_text}

        # 3. Send the result back to our second n8n webhook
        payload = {
            "job_id": job_id,
            "chat_id": chat_id, # CRITICAL: We need to pass this back!
            "transcript": transcript_text
        }
        
        # Use httpx for async-friendly HTTP requests
        with httpx.Client() as client:
            response = client.post(N8N_WEBHOOK_URL, json=payload)
            response.raise_for_status() # Raise an exception if the webhook fails
        
        print(f"[{job_id}] Result successfully sent back to n8n.")

    except Exception as e:
        print(f"[{job_id}] Error in background task: {e}")
        jobs[job_id] = {"status": "failed", "error": str(e)}
    
    finally:
        # 4. Clean up the temporary file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

# --- API Endpoints ---
@app.post("/submit_job")
async def submit_transcription_job(
    background_tasks: BackgroundTasks, # FastAPI injects this for us
    file: UploadFile = File(...),
    # We now need the chat_id from n8n to know who to reply to later
    chat_id: str = File(...),
    x_service_api_key: str = Header(...)
):
    if x_service_api_key != SERVICE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid Service API Key")

    job_id = str(uuid.uuid4())
    temp_filename = f"/tmp/{job_id}{os.path.splitext(file.filename)[1]}"
    
    # Save the file first
    with open(temp_filename, "wb") as buffer:
        buffer.write(await file.read())

    # Store initial job status
    jobs[job_id] = {"status": "processing", "submitted_at": time.time()}

    # THIS IS THE KEY: We add our slow function to the background tasks.
    # FastAPI will run this AFTER sending the response below.
    background_tasks.add_task(process_transcription, job_id, temp_filename, chat_id)

    # Return IMMEDIATELY with the Job ID.
    print(f"[{job_id}] Job submitted for chat_id: {chat_id}. Returning immediately.")
    return JSONResponse(content={"job_id": job_id, "status": "processing"})