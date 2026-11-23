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
    monkeypatch.setattr(engine,'analyze_sentiment',lambda *a,**kw:fixture['sentiment'])
    monkeypatch.setattr(engine,'guardrail_analysis',lambda *a:{'trust_score':.8})
    monkeypatch.setattr(engine,'verify_analysis',lambda *a:engine._unavailable_verification('test'))
    monkeypatch.setattr(engine,'generate_recommendation',lambda *a,**kw:fixture['recommendation'])
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


@pytest.mark.parametrize('count',[9,101,12])
def test_review_limit_rejects_out_of_range_or_non_step_values(count):
    assert client.post('/api/analyze',json={'location':'Cafe, Pune','max_reviews':count}).status_code==422


def test_custom_review_limit_reaches_engine(monkeypatch):
    monkeypatch.setenv('APIFY_API_TOKEN','test-token')
    monkeypatch.setenv('GROQ_API_KEY','test-key')
    captured=[]
    def analyze(location,count,**kwargs):
        captured.append(count)
        return demo_report()
    monkeypatch.setitem(sys.modules,'location',SimpleNamespace(analyze=analyze))
    class ImmediatePool:
        def submit(self,func,*args):
            func(*args)
    monkeypatch.setattr(server,'pool',ImmediatePool())
    monkeypatch.setattr(server,'jobs',{})
    response=client.post('/api/analyze',json={'location':'Cafe, Pune','max_reviews':100,'fast':True})
    assert response.status_code==202
    assert captured==[100]


def test_demo_exercises_all_legacy_sections_without_live_claims():
    data=demo_report()
    assert data['meta']['demo']
    assert data['verification']['accuracy'] is None
    assert data['verification']['status']=='DEMO'
    for key in ['emotion_distribution','rating_counts','aspect_scores','temporal_trend','crowd_profile','themes','positive_keywords','negative_keywords','per_review','standout_positive_quote','standout_negative_quote']:
        assert data['sentiment'][key]
    for key in ['linguistic_analysis','rating_integrity','reviewer_behavior','heuristic_stats','contradiction_analysis','aspect_credibility','genuine_positives','genuine_concerns','verified_facts']:
        assert data['guardrail'][key]
    for key in ['pros','cons','avoid_if','best_for','best_time','visitor_tips','score_breakdown','confidence','data_reliability']:
        assert data['recommendation'][key]
    ids={r['id'] for r in data['reviews']}
    points=data['sentiment']['themes']+data['guardrail']['genuine_positives']+data['guardrail']['genuine_concerns']+data['verification']['corrections']
    for point in points:
        assert set(point.get('evidence_review_ids',point.get('supporting_review_ids',[])))<=ids


def _content_reviews(n=31):
    return [{'id':f'r{i+1}','rating':4,'author':f'A{i}',
             'text':('Long context. '*80)+f'Review {i+1}: Helpful team. Parking access concern {i+1}.',
             'date':f'2026-10-{i%28+1:02d}'} for i in range(n)]


def _content_batch(reviews):
    return {'per_review':[{'id':r['id'],'sentiment':'Positive','score':.5,'emotion':'Satisfied',
            'topics':[{'topic':'staff_helpfulness','sentiment':'Positive','detail':f"Helpful team described in {r['id']}",'evidence_quote':'Helpful team.'},
                      {'topic':'parking','sentiment':'Negative','detail':f"Parking concern described in {r['id']}",'evidence_quote':f"Parking access concern {r['id'][1:]}."}]} for r in reviews],
            'aspect_scores':{'service':{'score':8,'reviews_mentioning':len(reviews),'summary':f"Service evidence through {reviews[-1]['id']}",'evidence_review_ids':[r['id'] for r in reviews]}},
            'positive_points':[],'negative_points':[],'themes':[],'crowd_profile':{'accessibility_notes':f"Notes through {reviews[-1]['id']}"}}


def test_all_review_sentiment_uses_full_text_and_covers_mixed_topics(engine,monkeypatch):
    import re
    reviews=_content_reviews()
    prompts=[]
    def call(prompt,**kwargs):
        prompts.append(prompt)
        ids=re.findall(r'\[(r\d+)\] rating:',prompt)
        batch=[r for r in reviews if r['id'] in ids]
        assert batch and all(r['text'] in prompt for r in batch)
        return _content_batch(batch)
    monkeypatch.setattr(engine,'call_groq',call)
    result=engine.analyze_sentiment(reviews,{'category':'Hotel'})
    assert len(prompts)==3
    assert result['coverage']['analyzed_review_count']==31
    assert result['coverage']['complete']
    assert len(result['per_review'])==31
    assert any('r31' in p['evidence_review_ids'] for p in result['negative_points'])
    assert len(result['topic_inventory'][0]['evidence_review_ids'])==31
    assert 'r31' in result['aspect_scores']['service']['summary']
    assert 'r31' in result['crowd_profile']['accessibility_notes']


def test_missing_sentiment_rows_cannot_be_reported_as_complete(engine,monkeypatch):
    monkeypatch.setattr(engine,'call_groq',lambda *a,**kw:_content_batch(_content_reviews(1)))
    with pytest.raises(RuntimeError,match='incomplete'):
        engine.analyze_sentiment(_content_reviews(2))


def test_topic_quote_must_exist_and_per_review_score_must_be_valid():
    import analysis_content as c
    reviews=_content_reviews(1)
    result=_content_batch(reviews)
    result['per_review'][0]['topics'][0]['evidence_quote']='invented quotation'
    with pytest.raises(ValueError,match='quote'):
        c.validate_sentiment_batch(result,reviews)
    result=_content_batch(reviews)
    result['per_review'][0]['score']=10
    with pytest.raises(ValueError,match='score'):
        c.validate_sentiment_batch(result,reviews)


def test_aggregation_weights_reviews_and_preserves_late_category_aspects():
    import analysis_content as c
    many=_content_batch(_content_reviews(15))
    last=_content_batch([_content_reviews(16)[-1]])
    for row in many['per_review']:
        row['score']=1
    last['per_review'][0]['score']=-1
    last['aspect_scores']['service'].update(score=2)
    last['aspect_scores']['room_cleanliness']={'score':3,'reviews_mentioning':1,'summary':'Only late review mentions a dirty room.','evidence_review_ids':['r16']}
    merged=c.merge_sentiment([many,last],_content_reviews(16))
    assert merged['sentiment_score']==.875
    assert merged['aspect_scores']['service']['score']==7.62
    assert merged['aspect_scores']['room_cleanliness']['score']==3
    assert merged['aspect_scores']['room_cleanliness']['evidence_review_ids']==['r16']


def _guard_batch(batch):
    return {'reviewed_review_ids':[r['id'] for r in batch],'trust_score':.8,'fake_review_probability':.1,
            'linguistic_analysis':{'language_notes':f"Last observed review: {batch[-1]['id']}"},
            'rating_integrity':{'rating_notes':f"Ratings through {batch[-1]['id']}"},
            'reviewer_behavior':{'evidence':f"Evidence through {batch[-1]['id']}"},
            'guardrail_summary':f"Guardrail examined through {batch[-1]['id']}",
            'genuine_positives':[],'genuine_concerns':[], 'suspicious_patterns':[]}


def test_guardrail_reads_all_batches_and_retains_late_findings(engine,monkeypatch):
    reviews=_content_reviews()
    seen=[]
    def call(batch,sentiment):
        seen.extend(r['id'] for r in batch)
        result=_guard_batch(batch)
        if batch[-1]['id']=='r31':
            result['genuine_concerns']=[{'aspect':'Late parking concern','evidence':batch[-1]['text'],'severity':'Moderate','supporting_review_ids':['r31']}]
        return result
    monkeypatch.setattr(engine,'_guardrail_batch',call)
    result=engine.guardrail_analysis(reviews,{})
    assert len(seen)==31 and seen[-1]=='r31'
    assert result['coverage']['complete']
    assert 'r31' in result['guardrail_summary']
    assert 'r31' in result['linguistic_analysis']['language_notes']
    assert result['genuine_concerns'][0]['supporting_review_ids']==['r31']


def _audit_batch(batch):
    return {'verification_status':'PASS','reviewed_review_ids':[r['id'] for r in batch],
            **{k:{'status':'PASS','observations':['Checked this batch.'],'issues':[]} for k in ['sentiment','aspects','keywords','guardrail','evidence']},
            'corrections':[],'verification_notes':'Batch checked.'}


def test_audit_covers_full_reviews_after_twentieth_and_does_not_hide_failed_batch(engine,monkeypatch):
    import json
    reviews=_content_reviews()
    seen=[]
    fail_last=[False]
    def call(system,prompt,**kw):
        batch=json.loads(prompt.split('REVIEWS: ',1)[1].split('\nCLAIMS:',1)[0])
        seen.extend(r['id'] for r in batch)
        assert all(len(r['text'])>800 for r in batch)
        if batch[-1]['id']=='r31' and fail_last[0]:
            raise RuntimeError('provider unavailable')
        return _audit_batch(batch)
    monkeypatch.setattr(engine,'call_verifier',call)
    result=engine.verify_analysis(reviews,{}, {})
    assert result['verification_status']=='PASS'
    assert result['coverage']['audited_review_count']==31
    assert 'r31' in seen
    fail_last[0]=True
    result=engine.verify_analysis(reviews,{}, {})
    assert result['verification_status']=='UNAVAILABLE'
    assert result['evidence']['status']=='UNAVAILABLE'
    assert result['coverage']['audited_review_count']==30
    assert not result['coverage']['complete']


def test_scoped_claims_do_not_leak_other_batch_reviews():
    import analysis_content as c
    data={'per_review':[{'id':'r1','text':'first'},{'id':'r31','text':'last'}],
          'topics':[{'topic':'parking','evidence_review_ids':['r1','r31'],
                     'observations':[{'review_id':'r1','detail':'first'},{'review_id':'r31','detail':'last'}]}]}
    scoped=c.scoped_claims(data,{'r31'})
    assert [r['id'] for r in scoped['per_review']]==['r31']
    assert scoped['topics'][0]['evidence_review_ids']==['r31']
    assert scoped['topics'][0]['observations']==[{'review_id':'r31','detail':'last'}]


def test_detailed_verdict_context_keeps_all_topics_and_marks_missing_narrative(engine,monkeypatch):
    import analysis_content as c
    reviews=_content_reviews(1)
    sentiment=c.merge_sentiment([_content_batch(reviews)],reviews)
    scoring={'verdict':'VISIT WITH CAUTION','score':5.5,'confidence':.3,'score_breakdown':{}}
    prompts=[]
    def call(prompt,**kw):
        prompts.append(prompt)
        return {'recommendation':'HIGHLY RECOMMENDED','visit_score':10,'full_verdict':'Detailed model assessment with an incomplete topic section.',
                'summary_sections':[{'topic':'staff_helpfulness','assessment':'Friendly team reported.','evidence_review_ids':['r1']}],
                'guide_sections':[{'topic':'staff_helpfulness','advice':'Read the service evidence before deciding.','evidence_review_ids':['r1']}],
                'pros':[],'cons':[],'best_for_evidence':[{'description':'Invented fit','evidence_review_ids':['r999']}],
                'avoid_if_evidence':[]}
    monkeypatch.setattr(engine,'call_groq',call)
    result=engine.generate_recommendation('Hotel',{'category':'Hotel'},reviews,sentiment,{},scoring)
    assert len(prompts)==2
    assert 'parking' in prompts[0] and 'Parking concern' in prompts[0]
    assert result['recommendation']=='VISIT WITH CAUTION' and result['visit_score']==5.5
    assert not result['content_coverage']['complete']
    assert 'parking' in result['content_coverage']['missing_guide_topics']
    assert next(v for v in result['summary_sections'] if v['topic']=='parking')['generation_status']=='evidence_only'
    assert any('Parking concern' in p['point'] for p in result['cons'])
    assert result['best_for']==[]


def test_empty_verdict_is_not_silently_substituted(engine,monkeypatch):
    monkeypatch.setattr(engine,'call_groq',lambda *a,**kw:{})
    with pytest.raises(RuntimeError,match='usable verdict'):
        engine.generate_recommendation('Cafe',{},_content_reviews(1),{}, {},{'verdict':'RECOMMENDED','score':7,'confidence':.3,'score_breakdown':{}})


def test_guardrail_enrichment_does_not_invent_confidence_or_citations(engine):
    result=engine._enrich_guardrail_data({},_content_reviews(1),{'positive_points':[{'claim':'Uncited claim'}]})
    assert result['genuine_positives']==[]
    assert result['genuine_concerns']==[]


def test_corrections_do_not_parse_review_counts_as_scores_or_mutate_originals(engine):
    import copy
    sentiment=_content_batch(_content_reviews(1))
    original=copy.deepcopy(sentiment)
    verification={'verification_status':'CORRECTED','corrections':[{'field':'aspects.service','original_claim':'Quick service','corrected_claim':'3 reviewers mentioned waiting.','evidence_review_ids':['r1']}]}
    updated,_=engine.apply_corrections(sentiment,{},verification)
    assert sentiment==original
    assert updated['aspect_scores']['service']['score']==8
    assert verification['corrections'][0]['applied']
    assert 'summary only' in verification['corrections'][0]['application_note']


def test_extra_unassessed_bullets_and_analyst_corrections_do_not_artificially_lower_score(engine):
    reviews=_content_reviews(1)
    sentiment=_content_batch(reviews)
    sentiment.update(sentiment_score=.5,temporal_trend={})
    base={'trust_score':.8,'fake_review_probability':.1,'genuine_concerns':[]}
    first=engine.calculate_final_score(reviews,{'google_score':4},sentiment,base,{'verification_status':'UNAVAILABLE'})
    second=engine.calculate_final_score(reviews,{'google_score':4},sentiment,{**base,'genuine_concerns':[{'aspect':'Parking','severity':'Not assessed'}]*10},{'verification_status':'UNAVAILABLE','corrections':[{'evidence_review_ids':['r1']}]*10})
    assert first['score']==second['score']


def test_topic_complete_narrative_uses_all_topics_and_explicit_best_time_evidence(engine,monkeypatch):
    import analysis_content as c
    reviews=_content_reviews(1)
    sentiment=c.merge_sentiment([_content_batch(reviews)],reviews)
    def call(prompt,**kw):
        return {'full_verdict':'A supported, detailed assessment with all extracted topics.',
                'best_time':'Invented quiet evening',
                'summary_sections':[{'topic':t['topic'],'assessment':'Evidence-aware explanation.','evidence_review_ids':t['evidence_review_ids']} for t in sentiment['topic_inventory']],
                'guide_sections':[{'topic':t['topic'],'advice':'Check the linked topic evidence before visiting.','evidence_review_ids':t['evidence_review_ids']} for t in sentiment['topic_inventory']]}
    monkeypatch.setattr(engine,'call_groq',call)
    result=engine.generate_recommendation('Hotel',{},reviews,sentiment,{}, {'verdict':'RECOMMENDED','score':7,'confidence':.3,'score_breakdown':{}})
    assert result['content_coverage']['complete']
    assert len(result['guide_sections'])==2
    assert result['best_time'] is None
