"""Small local API: the live engine is imported only when credentials are available."""
import os
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from api.demo import demo_report

load_dotenv()
app = FastAPI(title='Placewise academic demo')
pool = ThreadPoolExecutor(max_workers=1)
jobs = {}
lock = threading.Lock()

class AnalyzeRequest(BaseModel):
    location: str = Field(min_length=3, max_length=500)
    fast: bool = True
    refresh: bool = False

@app.get('/api/health')
def health():
    return {'live_available': bool((os.getenv('APIFY_API_TOKEN') or os.getenv('APify_API_TOKEN')) and os.getenv('GROQ_API_KEY'))}

@app.get('/api/demo')
def demo():
    return demo_report()

def run_job(job_id, request):
    def progress(stage, title, detail):
        with lock:
            jobs[job_id].update(stage=stage, title=title, detail=detail)
    try:
        import location
        result = location.analyze(request.location.strip(), 15 if request.fast else 40,
                                  progress_callback=progress, fast=request.fast, force_refresh=request.refresh)
        with lock:
            if result.get('error'):
                jobs[job_id].update(status='error', error=result['error'])
            else:
                jobs[job_id].update(status='complete', report=result)
    except Exception:
        with lock:
            jobs[job_id].update(status='error', error='Live analysis could not finish. Check the API credentials and provider availability, then retry or use the instant demo.')

@app.post('/api/analyze', status_code=202)
def analyze(request: AnalyzeRequest):
    if not request.location.strip() or len(request.location.strip()) < 3:
        raise HTTPException(422, 'Enter a place name and city or a Google Maps URL.')
    if not health()['live_available']:
        raise HTTPException(503, 'Live analysis needs APIFY_API_TOKEN and GROQ_API_KEY in .env. The instant demo works without keys.')
    with lock:
        now = time.time()
        for key in list(jobs):
            if now-jobs[key]['created'] > 3600 and jobs[key]['status'] != 'running':
                del jobs[key]
        if any(j['status']=='running' for j in jobs.values()):
            raise HTTPException(409, 'An analysis is already running. Please wait for it to finish.')
        job_id = uuid.uuid4().hex
        jobs[job_id] = {'status':'running','stage':1,'title':'Starting analysis','detail':'Preparing review collection…','created':now}
    pool.submit(run_job, job_id, request)
    return {'job_id':job_id}

@app.get('/api/jobs/{job_id}')
def job(job_id: str):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404, 'Analysis not found. Please start again.')
        return dict(jobs[job_id])
