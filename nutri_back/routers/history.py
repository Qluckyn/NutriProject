from typing import Dict, Optional
from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from services import history_service
router=APIRouter()
class Save(BaseModel): personalized_analysis: Optional[Dict[str,object]]=None
@router.get('/history')
def list_history(): return history_service.list_all()
@router.post('/history')
def save_history(payload: Save): return history_service.create(payload.personalized_analysis)
@router.get('/history/{record_id}')
def history_detail(record_id:str): return history_service.get(record_id)
@router.delete('/history/{record_id}')
def delete_history(record_id:str): return history_service.delete(record_id)
@router.get('/history/{record_id}/reports.zip')
def history_reports_archive(record_id: str):
 data = history_service.reports_archive(record_id)
 return Response(data, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="history_{record_id[:8]}_reports.zip"'})
@router.get('/history/{record_id}/reports/{filename}')
def history_report(record_id:str,filename:str):
 p=history_service.report(record_id,filename); return FileResponse(p,filename=p.name)
@router.get('/history/{record_id}/images/{view}')
def history_image(record_id: str, view: str):
 p=history_service.image(record_id, view); return FileResponse(p, media_type='image/jpeg')
