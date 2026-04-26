from fastapi import APIRouter, Depends, HTTPException
from typing import Any
import pandas as pd
from pathlib import Path

router = APIRouter()

# TODO: Wire this via dependencies or env variables for the actual path.
EXPORTS_DIR = Path("C:/Users/Kushals.DESKTOP-D51MT8S/Desktop/Github/IRIS/data/exports/current/onfly")

@router.get("/overview")
async def get_dashboard_overview() -> dict[str, Any]:
    """
    Provides top-level walk-in and conversion metrics for the React frontend,
    replacing the raw data loading natively tracked in Streamlit.
    """
    walkins_path = EXPORTS_DIR / "onfly_walkin_sessions.csv"
    
    if not walkins_path.exists():
        return {
            "total_walkins": 0,
            "total_customers": 0,
            "total_staff": 0,
            "conversion_rate": "0%",
            "status": "No data available."
        }
        
    try:
        df = pd.read_csv(walkins_path)
        # Assuming typical walkin columns defined in on-fly logic.
        total_people = len(df)
        staff = len(df[df['Role'].str.upper() == 'STAFF'])
        customers = total_people - staff
        
        # Calculate naive conversions.
        conversions = len(df[df['Entry Type'].str.upper() == 'BILLING'])
        conv_rate = f"{(conversions / max(customers, 1)) * 100:.1f}%"
        
        return {
            "total_walkins": total_people,
            "total_customers": customers,
            "total_staff": staff,
            "conversion_rate": conv_rate,
            "status": "Success"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed parsing walkin exports: {str(e)}")
