import os
import uuid
import secrets
import json

from db_models import QA_Pair, Profile, Base
from pydantic_models import StartSessionResponse, MessageRequest, MessageResponse
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from sqlalchemy.orm import Session
from db_setup import get_db
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
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-12-01-preview",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)
DEPLOYMENT = "gpt-4o"

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

@app.get("/chat", response_class=HTMLResponse, dependencies=[Depends(authenticate)])
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/api/start", response_model=StartSessionResponse, dependencies=[Depends(authenticate)])
async def start_session(db: Session = Depends(get_db)):
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "history": [{"role": "system", "content": SYSTEM_PROMPT_CONTENT}],
        "turn": 0
    }
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=sessions[session_id]["history"] + [
            {"role": "user", "content": "Starte die Profil-Erstellung mit deiner ersten Frage."}
        ],
        temperature=0.7
    )
    first_q = resp.choices[0].message.content
    sessions[session_id]["history"].append({"role": "assistant", "content": first_q})

    qa_entry = QA_Pair(session_id=session_id, question="Starte die Profil-Erstellung mit deiner ersten Frage.", answer=first_q)
    db.add(qa_entry)
    db.commit()

    return {"session_id": session_id, "reply": first_q, "done": False}

@app.post("/api/message", response_model=MessageResponse, dependencies=[Depends(authenticate)])
async def message(payload: MessageRequest, db: Session = Depends(get_db)):
    session_id = payload.session_id
    user_input = payload.user_input.strip()
    state = sessions.get(session_id)
    if not state:
        raise HTTPException(status_code=400, detail="Ungültige Session")

    state["history"].append({"role": "user", "content": user_input})
    state["turn"] += 1

    if state["turn"] < MAX_TURNS:
        resp = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=state["history"],
            temperature=0.7
        )
        reply = resp.choices[0].message.content
        state["history"].append({"role": "assistant", "content": reply})

        qa_entry = QA_Pair(session_id=session_id, question=user_input, answer=reply)
        db.add(qa_entry)
        db.commit()

        return {"reply": reply, "done": False, "profile": None}

    # final summary / JSON emission
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=state["history"] + [
            {"role": "user", "content":
             "Bitte fasse zusammen: Wenn noch Infos fehlen, frage; "
             "ansonsten gib das Profil als JSON aus."}
        ],
        temperature=0
    )
    raw = resp.choices[0].message.content.strip()
    try:
        profile = json.loads(raw)
        done = True
    except json.JSONDecodeError:
        profile = None
        done = False
    state["history"].append({"role": "assistant", "content": raw})

    if profile:
        profile_entry = Profile(session_id=session_id, profile_data=profile)
        db.add(profile_entry)
        db.commit()

    return {"reply": raw, "done": done, "profile": profile}