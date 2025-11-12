import os
import sys
import whisper
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# --- Step 1: Load Environment Variables ---
load_dotenv()

# --- Step 2: Configuration and Security ---
# This is OUR OWN secret key to protect OUR service. It is NOT an OpenAI key.
# We will set this in the Railway dashboard for our production deployment.
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY")

if not SERVICE_API_KEY:
    print("FATAL ERROR: SERVICE_API_KEY environment variable not set.")
    sys.exit(1)

# --- Step 3: Global Model Loading ---
# This runs only ONCE when your service starts.
print("Loading Whisper model...")
try:
    model = whisper.load_model("base")
    print("Whisper model loaded successfully.")
except Exception as e:
    print(f"Error loading Whisper model: {e}")
    sys.exit(1)

# --- Step 4: Initialize the FastAPI Web Server ---
app = FastAPI()

# --- Step 5: Define the API Endpoint ---
@app.post("/transcribe")
async def transcribe_audio_endpoint(
    file: UploadFile = File(...),
    # The header name should be clear and custom.
    x_service_api_key: str = Header(...)
):
    # --- Security Check ---
    # Check if the key sent by the client (n8n) matches our secret.
    if x_service_api_key != SERVICE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid Service API Key")

    temp_filename = f"/tmp/{uuid.uuid4()}{os.path.splitext(file.filename)[1]}"

    try:
        with open(temp_filename, "wb") as buffer:
            buffer.write(await file.read())

        print(f"Starting transcription for: {file.filename}")
        result = model.transcribe(temp_filename, fp16=False)
        print("Transcription complete.")
        
        return JSONResponse(content={"transcript": result["text"]})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)