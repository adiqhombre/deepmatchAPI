from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})
@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit", response_class=HTMLResponse)
async def handle_form(request: Request, answer: str = Form(...)):
    # Process the answer and generate the next question or profile
    return templates.TemplateResponse("result.html", {"request": request, "answer": answer})
@app.post("/submit", response_class=HTMLResponse)
async def handle_form(request: Request, answer: str = Form(...)):
    # Process the answer and generate the profile
    return templates.TemplateResponse("result.html", {"request": request, "answer": answer})