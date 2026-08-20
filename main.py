from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from database import get_db, engine, Base
from models import Entry
import json
from sync import sync_all

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Suivi Ressource en Eau")

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    entries = db.query(Entry).order_by(Entry.id.desc()).limit(200).all()
    
    entries_data = []
    for e in entries:
        try:
            data = json.loads(e.data)
        except:
            data = {}
        
        clean_data = {}
        photo_url = None
        gps_info = None
        
        for key, value in data.items():
            if key in ["ec5_uuid", "created_at", "uploaded_at", "title"]:
                continue
                
            # Nettoyage du nom du champ
            clean_key = key.split("_", 1)[-1] if "_" in key else key
            clean_key = clean_key.replace("_", " ").capitalize()
            
            # Détection des photos
            if isinstance(value, str) and ("photo" in key.lower() or "image" in key.lower() or value.startswith("http") and "media" in value):
                photo_url = value
                continue
            
            # Détection du GPS
            if isinstance(value, dict) and ("latitude" in value or "lat" in value):
                lat = value.get("latitude") or value.get("lat")
                lon = value.get("longitude") or value.get("lon") or value.get("lng")
                accuracy = value.get("accuracy", "")
                gps_info = {
                    "lat": lat,
                    "lon": lon,
                    "accuracy": accuracy
                }
                continue
            
            clean_data[clean_key] = value
        
        entries_data.append({
            "id": e.id,
            "project": e.project_slug,
            "uuid": e.ec5_uuid,
            "created_at": e.created_at[:19].replace("T", " ") if e.created_at else "-",
            "data": clean_data,
            "photo": photo_url,
            "gps": gps_info
        })
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "entries": entries_data,
            "total": db.query(Entry).count()
        }
    )
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "entries": entries_data,
            "total": db.query(Entry).count()
        }
    )

@app.get("/sync")
def synchroniser():
    sync_all()
    return {"message": "Synchronisation terminée avec succès"}

@app.get("/api/entries")
def api_entries(db: Session = Depends(get_db)):
    entries = db.query(Entry).all()
    return [
        {
            "id": e.id,
            "project": e.project_slug,
            "uuid": e.ec5_uuid,
            "created_at": e.created_at,
            "data": json.loads(e.data)
        }
        for e in entries
    ]