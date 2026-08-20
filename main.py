from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from database import get_db, engine, Base
from models import Entry
import json
from sync import sync_all
from datetime import datetime
from openpyxl import Workbook
from io import BytesIO

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Suivi Ressource en Eau")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    entries = db.query(Entry).order_by(Entry.id.desc()).limit(200).all()
    
    entries_data = []
    alertes = []
    
    for e in entries:
        try:
            data = json.loads(e.data)
        except:
            data = {}
        
        clean_data = {}
        photo_url = None
        gps_info = None
        etat_chantier = None
        date_demarrage = None
        
        for key, value in data.items():
            if key in ["ec5_uuid", "created_at", "uploaded_at", "title"]:
                continue
                
            clean_key = key.split("_", 1)[-1] if "_" in key else key
            clean_key = clean_key.replace("_", " ").capitalize()
            
            if isinstance(value, str) and ("photo" in key.lower() or "image" in key.lower() or (value.startswith("http") and "media" in value)):
                photo_url = value
                continue
            
            if isinstance(value, dict) and ("latitude" in value or "lat" in value):
                lat = value.get("latitude") or value.get("lat")
                lon = value.get("longitude") or value.get("lon") or value.get("lng")
                accuracy = value.get("accuracy", "")
                gps_info = {"lat": lat, "lon": lon, "accuracy": accuracy}
                continue
            
            if "etat" in key.lower() and "chantier" in key.lower():
                etat_chantier = str(value).strip()
            
            if "date" in key.lower() and "demarrage" in key.lower():
                date_demarrage = str(value).strip()
            
            clean_data[clean_key] = value
        
        alerte = False
        jours = None
        if etat_chantier and "travaux en cours" in etat_chantier.lower() and date_demarrage:
            try:
                d = None
                for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                    try:
                        d = datetime.strptime(date_demarrage, fmt)
                        break
                    except:
                        pass
                if d:
                    jours = (datetime.now() - d).days
                    if jours > 80:
                        alerte = True
                        alertes.append({
                            "id": e.id,
                            "project": e.project_slug,
                            "jours": jours,
                            "date_demarrage": date_demarrage
                        })
            except:
                pass
        
        entries_data.append({
            "id": e.id,
            "project": e.project_slug,
            "uuid": e.ec5_uuid,
            "created_at": e.created_at[:19].replace("T", " ") if e.created_at else "-",
            "data": clean_data,
            "photo": photo_url,
            "gps": gps_info,
            "alerte": alerte,
            "jours": jours
        })
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "entries": entries_data,
            "total": db.query(Entry).count(),
            "alertes": alertes
        }
    )

@app.get("/sync")
def synchroniser():
    sync_all()
    return {"message": "Synchronisation terminée avec succès"}

@app.get("/export")
def export_excel(db: Session = Depends(get_db)):
    entries = db.query(Entry).order_by(Entry.id.desc()).all()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Donnees Epicollect"
    
    headers = ["ID", "Projet", "UUID", "Date creation", "Donnees"]
    ws.append(headers)
    
    for e in entries:
        try:
            data = json.loads(e.data)
            data_str = " | ".join([f"{k}: {v}" for k, v in data.items() if k not in ["ec5_uuid", "created_at", "uploaded_at"]])
        except:
            data_str = ""
        
        ws.append([
            e.id,
            e.project_slug,
            e.ec5_uuid,
            e.created_at,
            data_str
        ])
    
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 40
    ws.column_dimensions['D'].width = 22
    ws.column_dimensions['E'].width = 80
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=suivi_eau_export.xlsx"}
    )

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