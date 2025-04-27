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
# … (imports & setup unchanged) …

@app.post("/start_session", dependencies=[Depends(authenticate)])
async def start_session():
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "history": [{"role": "system", "content": SYSTEM_PROMPT_CONTENT}],
        "turn": 0
    }
    resp = client.chat.completions.create(
        engine      = DEPLOYMENT,
        messages    = sessions[session_id]["history"] + [
            {"role": "user", "content": "Starte die Profil-Erstellung mit deiner ersten Frage."}
        ],
        temperature = 0.7
    )
    first_q = resp.choices[0].message.content
    sessions[session_id]["history"].append({"role": "assistant", "content": first_q})
    return {"session_id": session_id, "reply": first_q, "done": False}

@app.post("/message", dependencies=[Depends(authenticate)])
async def message(payload: dict):
    session_id = payload.get("session_id")
    user_input = payload.get("user_input", "").strip()
    state = sessions.get(session_id)
    if not state:
        return JSONResponse({"error": "Ungültige Session"}, status_code=400)

    state["history"].append({"role": "user", "content": user_input})
    state["turn"] += 1

    if state["turn"] < MAX_TURNS:
        resp = client.chat.completions.create(
            engine      = DEPLOYMENT,
            messages    = state["history"],
            temperature = 0.7
        )
        reply = resp.choices[0].message.content
        state["history"].append({"role": "assistant", "content": reply})
        return {"reply": reply, "done": False}

    # final summary / JSON emission
    resp = client.chat.completions.create(
        engine      = DEPLOYMENT,
        messages    = state["history"] + [
            {"role": "user", "content":
             "Bitte fasse zusammen: Wenn noch Infos fehlen, frage; "
             "ansonsten gib das Profil als JSON aus."}
        ],
        temperature = 0
    )
    raw = resp.choices[0].message.content.strip()
    try:
        profile = json.loads(raw)
        done = True
    except json.JSONDecodeError:
        profile = None
        done = False
    state["history"].append({"role": "assistant", "content": raw})
    return {"reply": raw, "done": done, "profile": profile}

