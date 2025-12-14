from fastapi import APIRouter

router = APIRouter()

@router.get("/version")
def get_version():
    return {
        "app": "ERP-SOM",
        "latest_version": "1.0.0",
        "min_supported_version": "1.0.0",
        "force_update": False,
        "message": "Sistema actualizado",
        "download_url": None
    }
