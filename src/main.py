from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.converter import revolut_to_mt940
from io import BytesIO
import tempfile

app = FastAPI()
app.mount("/static", StaticFiles(directory="src/static"), name="static")



@app.get("/", response_class=HTMLResponse)
async def index():
    with open("src/templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/convert")
async def upload_file(file: UploadFile = File(...), iban: str = Form(...)):
    contents = await file.read()

    # создаём временный файл для ответа
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as temp:
        mt940_content = revolut_to_mt940(contents.decode("utf-8"), iban)
        temp.write(mt940_content)
        temp_path = temp.name

    return FileResponse(temp_path, filename="mt940.txt", media_type="text/plain")

