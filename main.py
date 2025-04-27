import os
import uuid
import secrets
import json

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from openai import AzureOpenAI

# —————————————————————————————
# Authentication
# —————————————————————————————
security = HTTPBasic()
def authenticate(creds: HTTPBasicCredentials = Depends(security)):
    user_ok = secrets.compare_digest(creds.username, os.getenv("ED0_USER", ""))
    pass_ok = secrets.compare_digest(creds.password, os.getenv("ED0_PASS", ""))
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"}
        )
    return creds.username

# —————————————————————————————
# Load system prompt from file
# —————————————————————————————
with open("ed0_system_prompt.txt", encoding="utf-8") as f:
    SYSTEM_PROMPT_CONTENT = f.read()

# —————————————————————————————
# OpenAI client
# —————————————————————————————
client = AzureOpenAI(
    api_key    = os.getenv("AZURE_OPENAI_KEY"),
    api_version= "2024-02-15-preview",
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
)
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# —————————————————————————————
# FastAPI setup
# —————————————————————————————
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# —————————————————————————————
# In-memory session store
# session_id → { history: [ {role,content} ], turn: int }
# —————————————————————————————
sessions = {}
MAX_TURNS = 10

# —————————————————————————————
# Routes
# —————————————————————————————

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(authenticate)])
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/start_session", dependencies=[Depends(authenticate)])
async def start_session():
    session_id = str(uuid.uuid4())
    # initialize with system prompt
    sessions[session_id] = {
        "history": [
            {"role": "system", "content": SYSTEM_PROMPT_CONTENT}
        ],
        "turn": 0
    }
    # ask the first question
    resp = client.chat.completions.create(
        model         = "gpt-4o",
        deployment_id = DEPLOYMENT,
        messages      = sessions[session_id]["history"] + [
            {"role": "user", "content": "Starte die Profil-Erstellung mit deiner ersten Frage."}
        ],
        temperature   = 0.7
    )
    first_q = resp.choices[0].message.content
    sessions[session_id]["history"].append({"role": "assistant", "content": first_q})
    return {"session_id": session_id, "reply": first_q, "done": False}

@app.post("/message", dependencies=[Depends(authenticate)])
async def message(payload: dict):
    session_id = payload.get("session_id")
    user_input = payload.get("user_input", "").strip()
    if session_id not in sessions:
        return JSONResponse({"error": "Ungültige Session"}, status_code=400)

    state = sessions[session_id]
    state["history"].append({"role": "user", "content": user_input})
    state["turn"] += 1

    # Turn < MAX_TURNS: ask next question
    if state["turn"] < MAX_TURNS:
        resp = client.chat.completions.create(
            model         = "gpt-4o",
            deployment_id = DEPLOYMENT,
            messages      = state["history"],
            temperature   = 0.7
        )
        reply = resp.choices[0].message.content
        state["history"].append({"role": "assistant", "content": reply})
        return {"reply": reply, "done": False}

    # Turn == MAX_TURNS: conditional summary or extra question
    summary_request = (
        "Bitte fasse alle bisherigen Antworten zusammen. "
        "Wenn dir noch Infos fehlen, stelle eine weitere Frage. "
        "Wenn du genug hast, gib das Profil im JSON-Format aus."
    )
    resp = client.chat.completions.create(
        model         = "gpt-4o",
        deployment_id = DEPLOYMENT,
        messages      = state["history"] + [
            {"role": "user", "content": summary_request}
        ],
        temperature   = 0
    )
    raw = resp.choices[0].message.content.strip()

    # Check if assistant returned JSON
    try:
        profile = json.loads(raw)
        state["history"].append({"role": "assistant", "content": "Hier ist dein Profil:"})
        done = True
    except json.JSONDecodeError:
        # Not JSON → assume another question
        profile = None
        state["history"].append({"role": "assistant", "content": raw})
        done = False

    return {
        "reply": raw,
        "done": done,
        "profile": profile
    }

@app.get("/history/{session_id}", dependencies=[Depends(authenticate)])
async def get_history(session_id: str):
    if session_id not in sessions:
        return JSONResponse({"error": "Ungültige Session"}, status_code=400)
    return {"history": sessions[session_id]["history"]}
