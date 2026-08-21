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
def home(
    request: Request, 
    db: Session = Depends(get_db),
    projet: str = None,
    etat: str = None,
    commune: str = None
):
    query = db.query(Entry)
    
    # On récupère toutes les entrées d'abord
    all_entries = query.order_by(Entry.id.desc()).all()
    
    entries_data = []
    alertes = []
    stats = {
        "total": 0,
        "alertes": 0,
        "par_projet": {},
        "par_etat": {},
        "par_commune": {}
    }
    
    for e in all_entries:
        try:
            data = json.loads(e.data)
        except:
            data = {}
        
        clean_data = {}
        photo_url = None
        gps_info = None
        etat_chantier = None
        date_demarrage = None
        commune_val = None
        
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
            
            if "commune" in key.lower():
                commune_val = str(value).strip()
            
            clean_data[clean_key] = value
        
        # Filtres
        if projet and e.project_slug != projet:
            continue
        if etat and etat_chantier and etat.lower() not in etat_chantier.lower():
            continue
        if commune and commune_val and commune.lower() not in commune_val.lower():
            continue
        
        # Alerte
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
        
        # Statistiques
        stats["total"] += 1
        if alerte:
            stats["alertes"] += 1
        
        stats["par_projet"][e.project_slug] = stats["par_projet"].get(e.project_slug, 0) + 1
        
        if etat_chantier:
            stats["par_etat"][etat_chantier] = stats["par_etat"].get(etat_chantier, 0) + 1
        
        if commune_val:
            stats["par_commune"][commune_val] = stats["par_commune"].get(commune_val, 0) + 1
        
        entries_data.append({
            "id": e.id,
            "project": e.project_slug,
            "uuid": e.ec5_uuid,
            "created_at": e.created_at[:19].replace("T", " ") if e.created_at else "-",
            "data": clean_data,
            "photo": photo_url,
            "gps": gps_info,
            "alerte": alerte,
            "jours": jours,
            "etat": etat_chantier,
            "commune": commune_val
        })
    
    # Listes pour les filtres
    projets = sorted(list(set([e.project_slug for e in all_entries])))
    etats = sorted(list(stats["par_etat"].keys()))
    communes = sorted(list(stats["par_commune"].keys()))
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "entries": entries_data,
            "total": stats["total"],
            "alertes": alertes,
            "stats": stats,
            "projets": projets,
            "etats": etats,
            "communes": communes,
            "filtre_projet": projet,
            "filtre_etat": etat,
            "filtre_commune": commune
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
    
    # On récupère tous les noms de champs possibles
    all_keys = set()
    parsed_entries = []
    
    for e in entries:
        try:
            data = json.loads(e.data)
        except:
            data = {}
        
        clean = {
            "ID": e.id,
            "Projet": e.project_slug,
            "UUID": e.ec5_uuid,
            "Date creation": e.created_at
        }
        
        for key, value in data.items():
            if key in ["ec5_uuid", "created_at", "uploaded_at", "title"]:
                continue
            clean_key = key.split("_", 1)[-1] if "_" in key else key
            clean_key = clean_key.replace("_", " ").capitalize()
            
            # On simplifie le GPS
            if isinstance(value, dict) and ("latitude" in value or "lat" in value):
                lat = value.get("latitude") or value.get("lat")
                lon = value.get("longitude") or value.get("lon")
                clean["Latitude"] = lat
                clean["Longitude"] = lon
                continue
            
            clean[clean_key] = value
            all_keys.add(clean_key)
        
        parsed_entries.append(clean)
    
    # En-têtes
    headers = ["ID", "Projet", "UUID", "Date creation", "Latitude", "Longitude"] + sorted(list(all_keys))
    ws.append(headers)
    
    # Données
    for row in parsed_entries:
        line = [row.get(h, "") for h in headers]
        ws.append(line)
    
    # Largeur des colonnes
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[column].width = min(max_length + 2, 40)
    
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