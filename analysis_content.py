"""Coverage-first review aggregation. No network clients or credentials required."""
from copy import deepcopy
from datetime import datetime
import math
import re

SENTIMENTS = {'Positive', 'Negative', 'Neutral', 'Mixed'}


def number(value, low=-math.inf, high=math.inf):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value <= high


def unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(deepcopy(value))
    return result


def joined(values):
    return ' '.join(unique(v.strip() for v in values if isinstance(v, str) and v.strip()))


def topic_key(value):
    return re.sub(r'[^\w]+', '_', str(value).strip().casefold()).strip('_')


def canonical_reviews(reviews):
    return [{**r, 'id': r.get('id') or f'r{i+1}'} for i, r in enumerate(reviews)]


def review_batches(reviews, max_count=15, max_chars=20000):
    """Limit batch size rather than clipping each review. A long review stays whole."""
    batch, size = [], 0
    for r in canonical_reviews(reviews):
        length = len(r.get('text', ''))
        if batch and (len(batch) >= max_count or size + length > max_chars):
            yield batch
            batch, size = [], 0
        batch.append(r)
        size += length
    if batch:
        yield batch


def validate_sentiment_batch(result, reviews):
    """A batch is complete only if every review has a valid score and grounded topics."""
    if not isinstance(result, dict) or not isinstance(result.get('per_review'), list):
        raise ValueError('Missing per-review analysis.')
    source = {r['id']: r for r in canonical_reviews(reviews)}
    rows = result['per_review']
    ids = [r.get('id') for r in rows if isinstance(r, dict)]
    if len(ids) != len(set(ids)) or set(ids) != set(source):
        raise ValueError(f'Expected all review IDs {list(source)}; received {ids}.')
    cleaned = deepcopy(result)
    for row in cleaned['per_review']:
        if row.get('sentiment') not in SENTIMENTS or not number(row.get('score'), -1, 1):
            raise ValueError(f'Invalid sentiment/score for {row["id"]}.')
        topics = row.get('topics')
        if not isinstance(topics, list) or not topics:
            raise ValueError(f'Missing topic analysis for {row["id"]}.')
        raw = ' '.join(source[row['id']]['text'].casefold().split())
        for topic in topics:
            if not isinstance(topic, dict) or not topic_key(topic.get('topic', '')) or topic.get('sentiment') not in SENTIMENTS:
                raise ValueError(f'Invalid topic in {row["id"]}.')
            quote = topic.get('evidence_quote')
            if not isinstance(quote, str) or not quote.strip() or ' '.join(quote.casefold().split()) not in raw:
                raise ValueError(f'Topic quote is not present in {row["id"]}.')
            if not isinstance(topic.get('detail'), str) or not topic['detail'].strip():
                raise ValueError(f'Missing topic explanation in {row["id"]}.')
            topic['topic'] = topic_key(topic['topic'])
    return cleaned


def evidence_items(items, valid_ids, id_field='evidence_review_ids'):
    """Do not fabricate citations or promote uncited claims into verified findings."""
    output = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        copy = deepcopy(item)
        ids = copy.get(id_field)
        if not isinstance(ids, list):
            continue
        copy[id_field] = unique(i for i in ids if i in valid_ids)
        if copy[id_field]:
            invalid = [i for i in ids if i not in valid_ids]
            if invalid:
                copy['unresolved_evidence_review_ids'] = invalid
            output.append(copy)
    return output


def sentiment_label(score):
    return 'Positive' if score >= .4 else 'Negative' if score <= -.3 else 'Neutral' if -.15 <= score <= .15 else 'Mixed'


def build_topic_inventory(per_review):
    topics = {}
    for row in per_review:
        for observation in row.get('topics', []):
            key = topic_key(observation['topic'])
            topic = topics.setdefault(key, {'topic': key, 'evidence_review_ids': [], 'observations': [],
                                           'positive_review_ids': [], 'negative_review_ids': [],
                                           'neutral_review_ids': [], 'mixed_review_ids': []})
            topic['evidence_review_ids'] = unique(topic['evidence_review_ids'] + [row['id']])
            polarity = observation['sentiment'].lower() + '_review_ids'
            topic[polarity] = unique(topic[polarity] + [row['id']])
            topic['observations'].append({'review_id': row['id'], **deepcopy(observation)})
    for topic in topics.values():
        topic['reviews_mentioning'] = len(topic['evidence_review_ids'])
    return sorted(topics.values(), key=lambda t: (-t['reviews_mentioning'], t['topic']))


def temporal_trend(reviews, per_review):
    scores = {r['id']: r['score'] for r in per_review}
    dated = []
    for r in canonical_reviews(reviews):
        try:
            day = datetime.fromisoformat(str(r.get('date', '')).replace('Z', '+00:00')).date()
        except (ValueError, TypeError):
            continue
        if r['id'] in scores:
            dated.append((day, scores[r['id']]))
    dated.sort(key=lambda r: r[0])
    if len(dated) < 6 or (dated[-1][0] - dated[0][0]).days < 7:
        return {'trend': 'Insufficient evidence', 'dated_review_count': len(dated),
                'trend_explanation': 'Need at least six dated reviews spanning seven days. No trend is inferred from a single batch.'}
    split = len(dated) // 2
    old, recent = dated[:split], dated[split:]
    old_score, new_score = sum(v for _, v in old)/len(old), sum(v for _, v in recent)/len(recent)
    change = new_score - old_score
    return {'trend': 'Improving' if change >= .15 else 'Declining' if change <= -.15 else 'Stable',
            'recent_score': round(new_score, 3), 'older_score': round(old_score, 3),
            'recent_sentiment': sentiment_label(new_score), 'older_sentiment': sentiment_label(old_score),
            'older_review_count': len(old), 'recent_review_count': len(recent),
            'date_range': [str(dated[0][0]), str(dated[-1][0])],
            'trend_explanation': 'Computed from the older and newer halves of all dated, analyzed reviews. Unequal time windows and a small newest-first sample limit interpretation; this is not statistical proof of change.'}


def merge_sentiment(results, reviews=None):
    if not results:
        return {}
    rows = [deepcopy(row) for result in results for row in result.get('per_review', [])]
    ids = {r['id'] for r in rows}
    merged = {'per_review': rows, 'positive_keywords': [], 'negative_keywords': [], 'themes': [],
              'positive_points': [], 'negative_points': [], 'emotion_distribution': {}, 'aspect_scores': {}}
    for key in ('positive_keywords', 'negative_keywords'):
        merged[key] = unique(value for result in results for value in result.get(key, []))
    for row in rows:
        emotion = row.get('emotion')
        if emotion:
            merged['emotion_distribution'][emotion] = merged['emotion_distribution'].get(emotion, 0) + 1
    if not merged['emotion_distribution']:
        for result in results:
            for key, value in result.get('emotion_distribution', {}).items():
                if number(value, 0):
                    merged['emotion_distribution'][key] = merged['emotion_distribution'].get(key, 0) + value
    for key in ('positive_points', 'negative_points'):
        merged[key] = unique(p for result in results for p in evidence_items(result.get(key, []), ids))
    themes = {}
    for result in results:
        for theme in evidence_items(result.get('themes', []), ids):
            key = topic_key(theme.get('name', ''))
            target = themes.setdefault(key, {**theme, 'evidence_review_ids': [], 'evidence': '', 'representative_quotes': []})
            target['evidence_review_ids'] = unique(target['evidence_review_ids'] + theme['evidence_review_ids'])
            target['evidence'] = joined([target['evidence'], theme.get('evidence')])
            if theme.get('representative_quote'):
                target['representative_quotes'] = unique(target['representative_quotes'] + [theme['representative_quote']])
            if target.get('sentiment') != theme.get('sentiment'):
                target['sentiment'] = 'Mixed'
    for theme in themes.values():
        theme['frequency'] = len(theme['evidence_review_ids'])
    merged['themes'] = list(themes.values())
    aspect_keys = unique(key for result in results for key in result.get('aspect_scores', {}))
    for key in aspect_keys:
        aspects = [result.get('aspect_scores', {}).get(key, {}) for result in results]
        scored = [a for a in aspects if isinstance(a, dict) and number(a.get('score'), 0, 10) and a.get('reviews_mentioning', 0) > 0]
        weight = sum(a['reviews_mentioning'] for a in scored)
        evidence = unique(i for a in scored for i in a.get('evidence_review_ids', []) if i in ids)
        merged['aspect_scores'][key] = {'score': round(sum(a['score']*a['reviews_mentioning'] for a in scored)/weight, 2) if weight else None,
            'reviews_mentioning': len(evidence) if evidence else weight,
            'summary': joined(a.get('summary') for a in aspects if isinstance(a, dict)) or None,
            'evidence_review_ids': evidence}
    valid_scores = [r['score'] for r in rows if number(r.get('score'), -1, 1)]
    # Legacy-compatible fallback is weighted by batch review counts, never batch count.
    weighted = [(r.get('sentiment_score'), len(r.get('per_review', []))) for r in results if number(r.get('sentiment_score'), -1, 1)]
    merged['sentiment_score'] = round(sum(valid_scores)/len(valid_scores), 3) if valid_scores else round(sum(s*n for s,n in weighted)/sum(n for _,n in weighted), 3) if sum(n for _,n in weighted) else 0
    merged['overall_sentiment'] = sentiment_label(merged['sentiment_score'])
    inventory = build_topic_inventory(rows)
    merged['topic_inventory'] = inventory
    # Every extracted polarity/topic survives into the points, even if a batch summary omitted it.
    for topic in inventory:
        for polarity, key in [('Positive', 'positive_points'), ('Negative', 'negative_points')]:
            observations = [o for o in topic['observations'] if o['sentiment'] == polarity]
            topic_ids = topic[polarity.lower()+'_review_ids']
            if observations:
                merged[key].append({'topic': topic['topic'], 'claim': joined(o['detail'] for o in observations),
                                    'evidence_review_ids': topic_ids, 'reviews_mentioning': len(topic_ids),
                                    'source': 'Aggregated per-review topic evidence'})
    profiles = [r.get('crowd_profile', {}) for r in results]
    visitors = unique(p.get('dominant_visitor_type') for p in profiles if p.get('dominant_visitor_type'))
    merged['crowd_profile'] = {'dominant_visitor_type': ', '.join(visitors) or 'Not established',
        'mention_evidence': joined(p.get('mention_evidence') for p in profiles),
        'accessibility_notes': joined(p.get('accessibility_notes') for p in profiles)}
    for key in ('standout_positive_quote', 'standout_negative_quote'):
        quotes = unique(r[key] for r in results if isinstance(r.get(key), str) and r[key])
        if reviews:
            quotes = [q for q in quotes if any(q.casefold() in r.get('text', '').casefold() for r in reviews)]
        merged[key] = quotes[0] if quotes else ''
        merged[key+'s'] = quotes
    merged['emotional_tone'] = max(merged['emotion_distribution'], key=merged['emotion_distribution'].get) if merged['emotion_distribution'] else 'Not established'
    merged['review_diversity'] = ', '.join(unique(r.get('review_diversity') for r in results if r.get('review_diversity'))) or 'Not established'
    merged['temporal_trend'] = temporal_trend(reviews or [], rows)
    merged['coverage'] = {'input_review_count': len(reviews) if reviews is not None else len(rows),
        'analyzed_review_count': len(ids), 'analyzed_review_ids': sorted(ids),
        'topic_count': len(inventory), 'complete': len(ids) == (len(reviews) if reviews is not None else len(rows))}
    return merged


def scoped_claims(data, batch_ids):
    """Show every claim touching this batch, with only locally checkable citations."""
    if isinstance(data, list):
        return [item for value in data if (item := scoped_claims(value, batch_ids)) is not None]
    if isinstance(data, dict):
        if 'review_id' in data and data['review_id'] not in batch_ids:
            return None
        if isinstance(data.get('id'), str) and re.fullmatch(r'r\d+', data['id']) and data['id'] not in batch_ids:
            return None
        citation_keys = [k for k in ('evidence_review_ids', 'supporting_review_ids') if k in data]
        if citation_keys and not any(set(data[k] or []) & batch_ids for k in citation_keys):
            return None
        result = {}
        for key, value in data.items():
            result[key] = [i for i in value if i in batch_ids] if key in citation_keys else scoped_claims(value, batch_ids)
        return result
    return data


def merge_guardrails(results, reviews, sentiment):
    ids = {r['id'] for r in canonical_reviews(reviews)}
    total = sum(count for _, count in results)
    merged = {}
    for key in ('trust_score', 'credibility_score', 'fake_review_probability'):
        valid = [(r[key], n) for r,n in results if number(r.get(key), 0, 1)]
        merged[key] = round(sum(v*n for v,n in valid)/sum(n for _,n in valid), 3) if valid else None
    for key in ('review_quality','bias_level','bias_direction'):
        merged[key] = ', '.join(unique(r[key] for r,_ in results if r.get(key))) or 'Unknown'
    for key in ('guardrail_summary','analyst_recommendation'):
        merged[key] = joined(r.get(key) for r,_ in results)
    for key in ('genuine_positives','genuine_concerns'):
        merged[key] = unique(p for r,_ in results for p in evidence_items(r.get(key, []), ids, 'supporting_review_ids'))
    for key in ('contradiction_analysis','suspicious_patterns'):
        merged[key] = unique(p for r,_ in results for p in r.get(key, []))
    # Keep every batch assessment instead of taking the first one.
    for key in ('linguistic_analysis','rating_integrity','reviewer_behavior'):
        sections = [r.get(key, {}) for r,_ in results]
        merged[key] = {}
        for field in unique(f for section in sections for f in section):
            values = [s[field] for s in sections if field in s and s[field] is not None]
            if not values:
                merged[key][field] = None
            elif all(isinstance(v, bool) for v in values):
                merged[key][field] = all(values) if field == 'distribution_natural' else any(values)
            elif all(isinstance(v, list) for v in values):
                merged[key][field] = unique(item for v in values for item in v)
            elif all(number(v) for v in values):
                merged[key][field] = sum(values) if field in ('inflated_stars_estimate','suppressed_stars_estimate') else round(sum(values)/len(values), 3)
            else:
                merged[key][field] = joined(str(v) for v in values)
    merged['aspect_credibility'] = {}
    for key in unique(k for r,_ in results for k in r.get('aspect_credibility', {})):
        values = [r['aspect_credibility'][key] for r,_ in results if key in r.get('aspect_credibility', {})]
        confidences = [v['confidence'] for v in values if number(v.get('confidence'), 0, 1)]
        merged['aspect_credibility'][key] = {'credible': all(v.get('credible') is True for v in values),
            'confidence': min(confidences) if confidences else None, 'note': joined(v.get('note') for v in values)}
    merged['verified_facts'] = [f'Analyzed sample contains {len(reviews)} text reviews.']
    merged['reported_observations'] = unique(p for r,_ in results for p in r.get('verified_facts', []))
    merged['coverage'] = {'input_review_count':len(reviews),'analyzed_review_count':total,'complete':total==len(reviews)}
    for target, source in [('genuine_positives','positive_points'), ('genuine_concerns','negative_points')]:
        for point in evidence_items(sentiment.get(source, []), ids):
            finding = {'aspect':point.get('topic') or point.get('aspect') or point.get('claim'),
                       'evidence':point.get('claim', ''), 'supporting_review_ids':point['evidence_review_ids'],
                       'source':'Per-review sentiment evidence; not an independent authenticity finding'}
            if target == 'genuine_concerns':
                finding['severity'] = 'Not assessed'
            else:
                finding['confidence'] = None
            if not any(p.get('evidence') == finding['evidence'] for p in merged[target]):
                merged[target].append(finding)
    merged['batch_assessments'] = [r for r,_ in results]
    return merged
