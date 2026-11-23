"""Fictional, explicitly labeled fixture for offline academic presentations."""
def demo_report():
    texts = [
        (5, 'The courtyard is lovely and the coffee was excellent. A peaceful spot to read in the morning.'),
        (5, 'Loved the cold coffee and fresh sandwiches. The staff made us feel welcome.'),
        (4, 'Beautiful greenery and good coffee. A little expensive, but a nice place to catch up with friends.'),
        (3, 'We waited thirty minutes on Saturday. The coffee was good when it finally arrived.'),
        (5, 'Quiet weekday mornings, friendly staff and a beautiful courtyard. Will come back.'),
        (4, 'The sandwich was fresh and the seating comfortable. Parking outside is limited.'),
        (5, 'Excellent coffee, clean tables and a relaxed atmosphere. Great for a conversation.'),
        (2, 'Very crowded on the weekend. Service was slow and we struggled to find parking.'),
        (4, 'Friendly team and tasty food. Prices are on the higher side for the portion sizes.'),
        (5, 'The courtyard is my favourite part. Lovely light, good coffee and a calm weekday atmosphere.'),
        (4, 'Clean and welcoming, with delicious sandwiches. Would prefer more budget options.'),
        (4, 'A good place to meet friends. Arrive early on weekends to avoid a wait.'),
    ]
    reviews = [{'id':f'r{i+1}','author':f'Sample visitor {i+1}','rating':r,'text':t,'date':f'2026-11-{18-i:02d}'} for i,(r,t) in enumerate(texts)]
    aspects = {
        'ambience':(9.2,7,'A green, relaxed courtyard is the standout.', ['r1','r5','r10']),
        'food_quality':(8.7,7,'Coffee and fresh sandwiches get repeated praise.', ['r1','r2','r6']),
        'cleanliness':(8.5,2,'Clean tables and a welcoming space.', ['r7','r11']),
        'service':(7.2,5,'Friendly staff, with slower service at busy times.', ['r2','r4','r8']),
        'value_for_money':(6.8,3,'Several visitors mention premium pricing.', ['r3','r9','r11']),
        'crowd_wait_time':(5.8,3,'Weekend queues and limited parking need planning.', ['r4','r8','r12']),
    }
    report = {
        'location':'The Courtyard Café, Pune',
        'place_info':{'name':'The Courtyard Café','address':'Koregaon Park, Pune, Maharashtra','category':'Café & coffee house','google_score':4.3,'review_count':12,'price':'₹₹'},
        'reviews':reviews,
        'review_stats':{'raw_scraped_count':12,'usable_text_review_count':12,'cleaned_review_count':12,'analyzed_review_count':12},
        'sentiment':{'overall_sentiment':'Positive','per_review':[{'id':r['id'],'sentiment':'Positive' if r['rating']>=4 else 'Neutral' if r['rating']==3 else 'Negative'} for r in reviews], 'aspect_scores':{k:{'score':v[0],'reviews_mentioning':v[1],'summary':v[2],'evidence_review_ids':v[3]} for k,v in aspects.items()}, 'positive_points':[{'claim':'A calm courtyard with great coffee','evidence_review_ids':['r1','r5','r10']},{'claim':'Fresh food and a welcoming team','evidence_review_ids':['r2','r6','r9']}], 'negative_points':[{'claim':'Expect longer waits on weekends','evidence_review_ids':['r4','r8','r12']},{'claim':'Premium prices and limited parking','evidence_review_ids':['r3','r6','r9']} ]},
        'recommendation':{'recommendation':'RECOMMENDED','visit_score':7.8,'one_line_verdict':'Come for the coffee. Stay for the courtyard.','full_verdict':'A relaxed spot for a coffee catch-up or a quiet weekday morning. Visitors love the courtyard and fresh food, but weekend waits and premium prices are worth keeping in mind.','best_for':['Coffee lovers','Catching up','Quiet mornings'],'visitor_tips':['Choose a weekday morning for a quieter visit.','Allow extra time on weekends; nearby parking is limited.']},
        'verification':{'status':'DEMO','verification_status':'DEMO','accuracy':None},
        'final_scoring':{'score_breakdown':{'sentiment_comp':8.4,'aspect_comp':7.8,'rating_comp':8.6,'trust_comp':6.8,'consistency_comp':6.5,'recency_comp':7.2,'risk_penalty':0.1}},
        'meta':{'demo':True,'cached':False,'collected_at':'2026-11-18T10:00:00+00:00','elapsed_seconds':0,'notice':'Fictional place and illustrative analysis. These are not live Google Maps reviews.'}
    }

    # All additions below are fictional teaching examples, not model executions.
    report['place_info'].update(
        subtypes=['Café', 'Coffee shop', 'Sandwich shop'],
        description='A fictional neighbourhood café with a green courtyard, used only to demonstrate this project.',
        phone='Not supplied for fictional venue', website='', location_type='Café',
        opening_hours=[{'day':'Monday–Friday','hours':'08:00–21:00 (illustrative)'},
                       {'day':'Saturday–Sunday','hours':'09:00–22:00 (illustrative)'}],
        permanently_closed=False, temporarily_closed=False,
    )
    sentiment = report['sentiment']
    for result, review in zip(sentiment['per_review'], reviews):
        result.update(score=round((review['rating']-3)/2,2),
                      emotion='Happy' if review['rating']==5 else 'Satisfied' if review['rating']==4 else 'Neutral' if review['rating']==3 else 'Disappointed',
                      intensity='Medium', key_phrase=review['text'].split('.')[0])
    sentiment.update(
        sentiment_score=0.6, emotional_tone='Satisfied', review_diversity='Medium',
        emotion_distribution={emotion:sum(r['emotion']==emotion for r in sentiment['per_review'])
                              for emotion in ['Happy','Satisfied','Neutral','Disappointed']},
        rating_counts={str(n):sum(r['rating']==n for r in reviews) for n in range(1,6)},
        positive_keywords=['coffee','courtyard','fresh sandwiches','friendly staff'],
        negative_keywords=['crowded','slow service','limited parking','expensive'],
        standout_positive_quote='The courtyard is lovely and the coffee was excellent.',
        standout_negative_quote='Service was slow and we struggled to find parking.',
        crowd_profile={'dominant_visitor_type':'Friends and weekday visitors',
                       'mention_evidence':'Sample visitors mention catching up with friends and quiet mornings.',
                       'accessibility_notes':'Step-free access was not described; parking is mentioned as limited.'},
        temporal_trend={'recent_sentiment':'Positive','recent_score':0.67,
                        'older_sentiment':'Positive','older_score':0.5,'trend':'Improving',
                        'trend_explanation':'Illustrative comparison of two small halves of the fictional sample; not a statistically validated trend.'},
        themes=[
            {'name':'Courtyard atmosphere','sentiment':'Positive','frequency':4,
             'evidence':'Visitors praise the greenery and calm weekday atmosphere.',
             'representative_quote':'A peaceful spot to read in the morning.',
             'evidence_review_ids':['r1','r3','r5','r10']},
            {'name':'Weekend waits','sentiment':'Negative','frequency':3,
             'evidence':'Weekend visits include reports of crowding or a wait.',
             'representative_quote':'We waited thirty minutes on Saturday.',
             'evidence_review_ids':['r4','r8','r12']},
            {'name':'Price expectations','sentiment':'Mixed','frequency':3,
             'evidence':'Some visitors enjoy the experience but question the price or portions.',
             'representative_quote':'Prices are on the higher side for the portion sizes.',
             'evidence_review_ids':['r3','r9','r11']},
        ],
    )
    sentiment['aspect_scores']['accessibility'] = {'score':None,'reviews_mentioning':0,
                                                   'summary':'Not enough information on step-free access.',
                                                   'evidence_review_ids':[]}
    report['recommendation'].update(
        confidence=0.64, data_reliability='Limited sample (illustrative)',
        pros=[{'point':'A relaxing courtyard and enjoyable coffee','weight':'High'},
              {'point':'Fresh sandwiches and friendly staff','weight':'Medium'}],
        cons=[{'point':'Weekend waits and limited parking','weight':'High'},
              {'point':'Premium pricing for some portion sizes','weight':'Medium'}],
        avoid_if=['You need a guaranteed quick weekend stop.','You are looking for the lowest-priced option.'],
        best_time='Weekday mornings, based on the fictional sample.',
        score_breakdown={'sentiment_score':8.4,'rating_score':8.6,'trust_score':6.8,'composite':7.8},
    )
    report['guardrail'] = {
        'trust_score':0.8,'credibility_score':0.76,'fake_review_probability':0.1,
        'review_quality':'Medium','bias_level':'Medium','bias_direction':'Positive',
        'guardrail_summary':'Illustrative assessment: mostly positive feedback with recurring weekend-service concerns.',
        'analyst_recommendation':'Read the source reviews; sample size and newest-first selection limit confidence.',
        'linguistic_analysis':{'templated_language_detected':False,'copy_paste_evidence':None,
                               'vocabulary_diversity':'Medium','writing_style_consistency':'Varied',
                               'language_notes':'Fictional texts vary in length and focus; this is not a real authenticity assessment.'},
        'rating_integrity':{'distribution_natural':None,'adjusted_true_rating':4.1,
                            'inflated_stars_estimate':0,'suppressed_stars_estimate':0,
                            'anomalies':['Small sample is mostly four- and five-star reviews.'],
                            'rating_notes':'The adjusted number is an illustrative model estimate, not a true rating.'},
        'reviewer_behavior':{'sock_puppet_risk':'Not established','coordinated_posting_risk':'Not established',
                             'evidence':'No reviewer history is available in this sample.'},
        'heuristic_stats':{'total_reviews':12,'avg_rating':round(sum(r['rating'] for r in reviews)/12,2),
                           'five_star_pct':5/12,'one_star_pct':0,'unique_authors':12,'duplicate_pairs':0,
                           'avg_review_length':round(sum(len(r['text']) for r in reviews)/12),
                           'repeated_phrases':[]},
        'contradiction_analysis':[{'aspect':'Service','positive_claim':'Staff are friendly and welcoming.',
                                   'negative_claim':'Service can be slow on weekends.',
                                   'resolution':'These can both be true: friendliness and speed describe different aspects of the visit.'}],
        'aspect_credibility':{key:{'credible':True,'confidence':0.7,
                                  'note':'Illustrative support from the cited sample reviews.'}
                              for key in aspects},
        'suspicious_patterns':['A small, recent-only sample cannot establish authenticity.'],
        'genuine_positives':[{'aspect':'Atmosphere','evidence':'The courtyard is repeatedly praised.',
                              'confidence':0.8,'supporting_review_ids':['r1','r5','r10']}],
        'genuine_concerns':[{'aspect':'Wait times','evidence':'Weekend waits appear in multiple reviews.',
                             'severity':'Moderate','supporting_review_ids':['r4','r8','r12']}],
        'verified_facts':['The fictional dataset contains 12 text reviews.',
                          'Several sample reviews mention weekend waiting.'],
    }
    report['verification'].update(
        hallucination_detected=None, corrections_count=0,
        verification_notes='DEMO ONLY: no verifier was run. The field-level examples below illustrate the audit interface.',
        **{key:{'status':'DEMO','observations':['Illustrative audit observation, not an executed check.'],
                'issues':[],**({'unsupported_claims':[]} if key=='evidence' else {})}
           for key in ['sentiment','aspects','keywords','guardrail','evidence']},
        corrections=[{'field':'aspects.service','original_claim':'Service is consistently quick.',
                      'corrected_claim':'Service is friendly but can be slower on weekends.',
                      'reason':'Illustrative correction proposal based on the wait-related sample reviews; not a live-applied correction.',
                      'evidence_review_ids':['r4','r8']}],
        missing_positive_evidence=['Sample mention of comfortable seating in r6.'],
        missing_negative_evidence=['Sample parking complaint in r8.'],
    )
    report['model_info'] = {
        'model_1':{'sentiment_model':'Illustrative analyst (not run)','guardrail_model':'Illustrative guardrail (not run)'},
        'model_2':{'model':'Illustrative verifier (not run)'},
        'model_3':{'model':'Illustrative explanation (not run)'},
    }
    # Additional prewritten topic annotations demonstrate coverage; still no model calls.
    from analysis_content import build_topic_inventory
    rules = [
        ('food_quality', ('coffee','sandwich','food'), 'Positive'),
        ('staff_helpfulness', ('staff','friendly','team'), 'Positive'),
        ('ambience', ('courtyard','atmosphere','greenery','quiet','seating'), 'Positive'),
        ('pricing', ('expensive','price','budget'), 'Negative'),
        ('wait_time', ('wait','crowded','slow'), 'Negative'),
        ('parking', ('parking',), 'Negative'),
    ]
    for row, review in zip(sentiment['per_review'], reviews):
        row['topics'] = [{'topic':key,'sentiment':polarity,
                          'detail':f"{key.replace('_',' ').title()}: {review['text']}",
                          'evidence_quote':review['text']}
                         for key, words, polarity in rules if any(word in review['text'].lower() for word in words)]
    inventory = build_topic_inventory(sentiment['per_review'])
    sentiment['topic_inventory'] = inventory
    sentiment['coverage'] = {'input_review_count':12,'analyzed_review_count':12,
                             'analyzed_review_ids':[r['id'] for r in reviews],
                             'topic_count':len(inventory),'complete':True,'demo':True}
    advice = {
        'food_quality':'Coffee and fresh sandwiches are praised in this fictional sample. Choose based on your preferences and confirm the current menu rather than assuming every item is equally well reviewed.',
        'staff_helpfulness':'Visitors describe a welcoming team. Keep that praise separate from service speed: friendliness does not guarantee a short wait during busy periods.',
        'ambience':'The courtyard and quieter weekday atmosphere are recurring strengths. A weekday coffee catch-up fits these sample observations; quiet seating is not guaranteed.',
        'pricing':'Several reviews question price or portion value. Check the current menu and prices before ordering if a strict budget is important.',
        'wait_time':'The sample includes a thirty-minute Saturday wait and other busy-period concerns. Allow extra time or consider a quieter visit; no specific waiting time can be promised.',
        'parking':'Some visitors report limited parking. Check current access and parking arrangements before travelling, especially if you need a nearby space.',
    }
    report['recommendation']['full_verdict'] = (
        'The Courtyard Café is a fictional example of a relaxed coffee spot whose strongest appeal is its green courtyard and welcoming atmosphere. '
        'Coffee and fresh sandwiches receive repeated praise, making it an attractive sample choice for an unhurried catch-up. '
        'Visitors describe friendly staff, but that should not be confused with consistently quick service: the sample includes weekend queues and a thirty-minute Saturday wait. '
        'Pricing and portion value receive more mixed feedback, so budget-sensitive visitors should check the menu first. '
        'Limited parking is another practical consideration; step-free access is not established by these reviews. '
        'Taken together, the sample suggests a better fit for a flexible weekday visit than a rushed weekend stop. '
        'These are illustrative observations from twelve fictional reviews, not a verified assessment of a real business.'
    )
    report['recommendation']['summary_sections'] = [
        {'topic':t['topic'],
         'assessment':f"{t['reviews_mentioning']} of the 12 fictional reviews mention {t['topic'].replace('_',' ')}. "
                      f"This includes {len(t['positive_review_ids'])} positive and {len(t['negative_review_ids'])} negative topic observations. "
                      + advice[t['topic']],
         'evidence_review_ids':t['evidence_review_ids']} for t in inventory]
    report['recommendation']['guide_sections'] = [
        {'topic':t['topic'],'advice':advice[t['topic']],'evidence_review_ids':t['evidence_review_ids']} for t in inventory]
    report['recommendation']['content_coverage'] = {'topic_count':len(inventory),
        'summary_topics_generated':len(inventory),'guide_topics_generated':len(inventory),
        'missing_summary_topics':[],'missing_guide_topics':[],'complete':True,'demo':True}
    report['recommendation']['limitations'] = [
        'Fictional demonstration data, not a live business assessment.',
        'Twelve newest-style sample texts cannot represent all visitors.',
        'Accessibility and current facilities are not established; confirm directly.',
    ]
    report['guardrail']['coverage'] = {'input_review_count':12,'analyzed_review_count':12,'complete':True,'demo':True}
    report['verification']['coverage'] = {'input_review_count':12,'audited_review_count':0,
                                          'audited_review_ids':[],'complete':False,'demo':True}
    return report
