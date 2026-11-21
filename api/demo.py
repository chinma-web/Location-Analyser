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
    return {
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
