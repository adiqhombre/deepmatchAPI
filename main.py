import os
import uuid
import secrets

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # ← add this import

# ————————————————————
# Authentication setup
# ————————————————————
security = HTTPBasic()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    user_ok = secrets.compare_digest(credentials.username, os.getenv("ED0_USER", ""))
    pass_ok = secrets.compare_digest(credentials.password, os.getenv("ED0_PASS", ""))
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ————————————————————
# App setup
# ————————————————————
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory session store
sessions = {}

QUESTIONS = [
    "Wie erlebst du Nähe zu anderen Menschen?",
    "Wie gehst du mit Konflikten um?",
    "Was gibt dir emotionale Stabilität?",
    # … 7 weitere Fragen …
    "Frage 10: Abschließende Gedanken?"
]

# ————————————————————
# Routes
# ————————————————————
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(authenticate)])
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/start_session", dependencies=[Depends(authenticate)])
async def start_session():
    session_id = str(uuid.uuid4())
    sessions[session_id] = {"history": [], "turn": 0}
    first_q = QUESTIONS[0]
    sessions[session_id]["history"].append({"role": "ed0", "text": first_q})
    return {"session_id": session_id, "reply": first_q, "done": False}

@app.post("/message", dependencies=[Depends(authenticate)])
async def message(payload: dict):
    session_id = payload.get("session_id")
    user_input = payload.get("user_input", "").strip()
    if session_id not in sessions:
        return JSONResponse({"error": "Invalid session_id"}, status_code=400)

    state = sessions[session_id]
    state["history"].append({"role": "user", "text": user_input})
    turn = state["turn"] + 1

    if turn < len(QUESTIONS):
        q = QUESTIONS[turn]
        state["history"].append({"role": "ed0", "text": q})
        state["turn"] = turn
        return {"reply": q, "done": False}
    else:
        profile = {
            "profil_id": session_id,
            "achsen": {
                "Nähe & Eigenständigkeit": {"wert": "hoch", "beschreibung": "…"},
                # …
            },
            "archetyp": "Sanfter Realist"
        }
        state["history"].append({"role": "ed0", "text": "Dein Profil ist fertig."})
        return {"reply": "Dein Profil ist fertig.", "done": True, "profile": profile}

@app.get("/history/{session_id}", dependencies=[Depends(authenticate)])
async def get_history(session_id: str):
    if session_id not in sessions:
        return JSONResponse({"error": "Invalid session_id"}, status_code=400)
    return {"history": sessions[session_id]["history"]}
