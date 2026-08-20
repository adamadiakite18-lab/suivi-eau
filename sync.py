import requests
import json
import os
from dotenv import load_dotenv
from database import SessionLocal, engine, Base
from models import Entry
from datetime import datetime

load_dotenv()

Base.metadata.create_all(bind=engine)

def fetch_entries(project_slug, form_ref):
    url = f"https://five.epicollect.net/api/export/entries/{project_slug}"
    params = {
        "form_ref": form_ref,
        "per_page": 100,
        "page": 1
    }
    
    all_entries = []
    
    while True:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"Erreur pour {project_slug}: {response.status_code}")
            break
            
        data = response.json()
        entries = data.get("data", {}).get("entries", [])
        
        if not entries:
            break
            
        all_entries.extend(entries)
        
        # Pagination
        next_page = data.get("links", {}).get("next")
        if not next_page:
            break
            
        params["page"] += 1
    
    return all_entries

def sync_all():
    db = SessionLocal()
    
    projects = [
        {
            "slug": os.getenv("EPICOLLECT_PROJECT_1"),
            "form": os.getenv("EPICOLLECT_FORM_1")
        },
        {
            "slug": os.getenv("EPICOLLECT_PROJECT_2"),
            "form": os.getenv("EPICOLLECT_FORM_2")
        }
    ]
    
    total = 0
    
    for project in projects:
        print(f"Synchronisation de {project['slug']}...")
        entries = fetch_entries(project["slug"], project["form"])
        
        for entry in entries:
            uuid = entry.get("ec5_uuid")
            if not uuid:
                continue
                
            # Vérifier si l'entrée existe déjà
            existing = db.query(Entry).filter(Entry.ec5_uuid == uuid).first()
            if existing:
                continue
                
            new_entry = Entry(
                project_slug=project["slug"],
                form_ref=project["form"],
                ec5_uuid=uuid,
                created_at=entry.get("created_at", ""),
                data=json.dumps(entry, ensure_ascii=False)
            )
            db.add(new_entry)
            total += 1
        
        db.commit()
        print(f"  → {len(entries)} entrées trouvées")
    
    db.close()
    print(f"\nSynchronisation terminée. {total} nouvelles entrées ajoutées.")

if __name__ == "__main__":
    sync_all()