from typing import Optional

from fastapi import FastAPI

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit", response_class=HTMLResponse)
async def handle_form(request: Request, answer: str = Form(...)):
    # Process the answer and generate the profile
    return templates.TemplateResponse("result.html", {"request": request, "answer": answer})