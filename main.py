from fastapi import FastAPI

app = FastAPI(title="Mi API")

@app.get("/")
def home():
    return {"message": "Servidor FastAPI funcionando"}