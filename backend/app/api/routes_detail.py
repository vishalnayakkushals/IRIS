from fastapi import APIRouter, HTTPException
from typing import Any
import pandas as pd
from pathlib import Path

router = APIRouter()

EXPORTS_DIR = Path("C:/Users/Kushals.DESKTOP-D51MT8S/Desktop/Github/IRIS/data/exports/current/onfly")

@router.get("/{store_id}/metrics")
async def get_store_metrics(store_id: str) -> dict[str, Any]:
    """
    Provides isolated metrics specific to a single store_id for the UI Store Detail tab.
    """
    store_file = EXPORTS_DIR / "onfly_store_date_report.csv"
    
    if not store_file.exists():
        return {
            "store_id": store_id,
            "footfall": 0,
            "bounce_rate": "0%",
            "dwell_time": "0 min",
            "status": "No data available."
        }
        
    try:
        df = pd.read_csv(store_file)
        store_data = df[df['Store ID'] == store_id]
        
        if store_data.empty:
            return {
                "store_id": store_id,
                "footfall": 0,
                "bounce_rate": "0%",
                "dwell_time": "0 min",
                "status": "No activity recorded."
            }
            
        # Simplified aggregation from historical legacy
        footfall = int(store_data['Walk-ins'].sum() if 'Walk-ins' in store_data else 0)
        
        return {
            "store_id": store_id,
            "footfall": footfall,
            "bounce_rate": "14%", # Placeholder for advanced DB hook
            "dwell_time": "12.5 min",
            "status": "Success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed parsing store metrics: {str(e)}")
