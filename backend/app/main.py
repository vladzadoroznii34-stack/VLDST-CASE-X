from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .db import Base,engine
from .api import router
app=FastAPI(title='VLDST CASE X',version='1.0.0');Base.metadata.create_all(bind=engine);app.include_router(router)
front=Path(__file__).resolve().parents[2]/'frontend';app.mount('/assets',StaticFiles(directory=front/'public'),name='assets')
@app.get('/health')
def health():return {'status':'ok','service':'vldst-case-xx'}
@app.get('/')
def root():return FileResponse(front/'index.html')
