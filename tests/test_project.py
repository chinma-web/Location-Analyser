import importlib
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from api import server
from api.demo import demo_report

client = TestClient(server.app)

@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv('APIFY_API_TOKEN', 'test-token')
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')
    import model_config
    monkeypatch.setattr(model_config, 'fetch_catalog', lambda: None)
    if 'location' not in sys.modules:
        importlib.import_module('location')
    return sys.modules['location']

def test_demo_honest_and_evidence_resolves():
    data = client.get('/api/demo').json()
    assert data['meta']['demo'] is True
    assert data['verification']['accuracy'] is None
    ids = {r['id'] for r in data['reviews']}
    for point in data['sentiment']['positive_points'] + data['sentiment']['negative_points']:
        assert set(point['evidence_review_ids']) <= ids

def test_live_missing_keys(monkeypatch):
    for name in ['APIFY_API_TOKEN','APify_API_TOKEN','GROQ_API_KEY']:
        monkeypatch.delenv(name, raising=False)
    assert client.get('/api/health').json()['live_available'] is False
    assert client.post('/api/analyze', json={'location':'Cafe, Pune'}).status_code == 503

def test_input_and_unknown_job():
    assert client.post('/api/analyze', json={'location':'a'}).status_code == 422
    assert client.get('/api/jobs/not-a-real-job').status_code == 404

def test_empty_and_unavailable_verification_never_pass(engine):
    empty = engine._enrich_verification_data({}, [], {}, {})
    assert empty['verification_status'] == 'UNKNOWN'
    assert empty['accuracy'] is None
    unavailable = engine._enrich_verification_data(engine._unavailable_verification('timeout'), [], {}, {})
    assert unavailable['verification_status'] == 'UNAVAILABLE'
    assert unavailable['evidence']['status'] == 'UNAVAILABLE'
    assert unavailable['accuracy'] is None

@pytest.mark.parametrize('url',['http://127.0.0.1','https://example.com','https://google.com.evil.com/maps','https://www.google.com/search?q=test','https://goo.gl/not-maps'])
def test_url_rejects_non_maps(engine,url):
    with pytest.raises(ValueError):
        engine.validate_maps_url(url)

def test_quick_scrape_single_place_no_geocoding(engine,monkeypatch):
    captured = {}
    def call(**kwargs):
        captured.update(kwargs['run_input'])
        return {'defaultDatasetId':'dataset'}
    monkeypatch.setattr(engine,'apify',SimpleNamespace(actor=lambda _:SimpleNamespace(call=call),dataset=lambda _:SimpleNamespace(iterate_items=lambda:iter([{'title':'Cafe','reviews':[{'text':'Lovely coffee','stars':5}]}]))))
    monkeypatch.setattr(engine,'get_place_suggestions',lambda *a,**kw:pytest.fail('Quick scan must skip geocoding'))
    reviews,_,_ = engine.scrape_reviews('Cafe, Pune',15,fast=True)
    assert captured['maxCrawledPlaces'] == 1
    assert captured['maxReviews'] == 15
    assert reviews[0]['id'] == 'r1'

def test_cache_respects_parameters_and_refresh(engine,monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    calls=[]
    fixture=demo_report()
    def scrape(location,count,fast=False):
        calls.append((count,fast))
        return fixture['reviews'],fixture['place_info'],dict(fixture['review_stats'])
    monkeypatch.setattr(engine,'scrape_reviews',scrape)
    monkeypatch.setattr(engine,'analyze_sentiment',lambda _:fixture['sentiment'])
    monkeypatch.setattr(engine,'guardrail_analysis',lambda *a:{'trust_score':.8})
    monkeypatch.setattr(engine,'verify_analysis',lambda *a:engine._unavailable_verification('test'))
    monkeypatch.setattr(engine,'generate_recommendation',lambda *a:fixture['recommendation'])
    monkeypatch.setattr(engine,'display_report',lambda *a:None)
    monkeypatch.setattr(engine,'REQUIRE_VERIFICATION',False)
    engine.analyze('Cafe, Pune',15,fast=True)
    cached=engine.analyze('Cafe, Pune',15,fast=True)
    assert cached['meta']['cached']
    assert len(calls)==1
    engine.analyze('Cafe, Pune',40,fast=False)
    engine.analyze('Cafe, Pune',15,fast=True,force_refresh=True)
    assert calls == [(15,True),(40,False),(15,True)]

def test_api_job_lifecycle(monkeypatch):
    monkeypatch.setenv('APIFY_API_TOKEN','test-token')
    monkeypatch.setenv('GROQ_API_KEY','test-key')
    def analyze(location, count, progress_callback, **kwargs):
        assert count == 15
        assert kwargs == {'fast':True,'force_refresh':False}
        progress_callback(2,'Analyzing','Test progress')
        return demo_report()
    monkeypatch.setitem(sys.modules,'location',SimpleNamespace(analyze=analyze))
    class ImmediatePool:
        def submit(self,func,*args):
            func(*args)
    monkeypatch.setattr(server,'pool',ImmediatePool())
    monkeypatch.setattr(server,'jobs',{})
    response=client.post('/api/analyze',json={'location':'Cafe, Pune'})
    assert response.status_code == 202
    result=client.get('/api/jobs/'+response.json()['job_id']).json()
    assert result['status'] == 'complete'
    assert result['report']['place_info']['name'] == 'The Courtyard Café'


def test_api_rejects_concurrent_jobs(monkeypatch):
    import time
    monkeypatch.setenv('APIFY_API_TOKEN','test-token')
    monkeypatch.setenv('GROQ_API_KEY','test-key')
    monkeypatch.setattr(server,'jobs',{'running':{'status':'running','created':time.time()}})
    assert client.post('/api/analyze',json={'location':'Cafe, Pune'}).status_code == 409


def test_suggestions_work_without_paid_credentials(monkeypatch):
    for name in ['APIFY_API_TOKEN','APify_API_TOKEN','GROQ_API_KEY']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(server.geocoding,'get_city_suggestions',lambda q,limit:['Pune, Maharashtra, India'])
    calls=[]
    def suggestions(q,city,limit):
        calls.append((q,city,limit))
        return [{'display_name':'Cafe, Pune, India','search_name':'Cafe, Pune, India','lat':18.5,'lon':73.8}]
    monkeypatch.setattr(server.geocoding,'get_place_suggestions',suggestions)
    assert client.get('/api/suggestions/cities?q=Pu').json()['items']==['Pune, Maharashtra, India']
    result=client.get('/api/suggestions/places',params={'q':'Cafe','city':'Pune','limit':4})
    assert result.status_code==200
    assert result.json()['items'][0]['lat']==18.5
    assert calls==[('Cafe','Pune',4)]
    assert client.get('/api/suggestions/cities?q=P').status_code==422
    assert client.get('/api/suggestions/places?q=Cafe&limit=100').status_code==422


def test_suggestion_provider_failure_is_not_empty_success(monkeypatch):
    def unavailable(*a):
        raise server.geocoding.GeocodingUnavailable('City lookup is temporarily unavailable.')
    monkeypatch.setattr(server.geocoding,'get_city_suggestions',unavailable)
    assert client.get('/api/suggestions/cities?q=Pu').status_code==503


def test_model_selection_respects_catalog_and_overrides(monkeypatch):
    import model_config as models
    for env in models.ENV.values():
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(models,'fetch_catalog',lambda:{'openai/gpt-oss-120b','openai/gpt-oss-20b','qwen/qwen3-32b'})
    result=models.resolve_models()
    assert result['catalog_verified']
    assert result['roles']=={'analyst':'openai/gpt-oss-120b','guardrail':'openai/gpt-oss-20b','verifier':'qwen/qwen3-32b','verdict':'openai/gpt-oss-120b'}
    monkeypatch.setenv('VERIFIER_MODEL','qwen/qwen3.8-27b')
    result=models.resolve_models()
    assert result['roles']['verifier']=='qwen/qwen3-32b'
    assert 'unavailable' in result['notes'][0]
    monkeypatch.setattr(models,'fetch_catalog',lambda:{'qwen/qwen3.8-27b','openai/gpt-oss-20b'})
    result=models.resolve_models()
    assert result['roles']['verifier']=='qwen/qwen3.8-27b'
    assert result['roles']['analyst']=='openai/gpt-oss-20b'


def test_model_catalog_failure_does_not_claim_free_access(monkeypatch):
    import model_config as models
    monkeypatch.setattr(models,'fetch_catalog',lambda:None)
    result=client.get('/api/models').json()
    assert not result['catalog_verified']
    assert 'unverified' in result['notes'][0]


def test_model_catalog_without_supported_models_fails(monkeypatch):
    import model_config as models
    for env in models.ENV.values():
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(models,'fetch_catalog',lambda:{'whisper-large-v3'})
    assert client.get('/api/models').status_code==503


def test_reasoning_model_completion_budget(engine):
    options=engine._completion_options('openai/gpt-oss-120b',1500)
    assert options['reasoning_effort']=='low'
    assert options['max_completion_tokens']>=4096
    assert options['response_format']=={'type':'json_object'}
    assert 'reasoning_effort' not in engine._completion_options('qwen/qwen3-32b',2000)
