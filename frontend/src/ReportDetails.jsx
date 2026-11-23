import React, { useMemo, useState, useRef } from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from "recharts";
import {
  ArrowUpRight,
  Download,
  Info,
  ShieldCheck,
  MapPin,
  ExternalLink,
  Search,
  ChevronDown,
} from "lucide-react";
import "./report.css";

import {
  asList,
  object,
  text,
  numeric,
  percent,
  labels,
  name,
  Empty,
  Panel,
  Metrics,
  Evidence,
  Fields,
  BulletList,
  PointList,
  ReviewCounts,
} from "./ReportCommon";
const colors = [
  "#9060dc",
  "#46b694",
  "#f1b54b",
  "#e58288",
  "#69accb",
  "#b18ac9",
  "#e3945d",
];

function Chart({ children, label }) {
  const ref = useRef(null),
    [expanded, setExpanded] = useState(false);
  function exportSvg() {
    const svg = ref.current?.querySelector("svg.recharts-surface");
    if (!svg) return;
    const copy = svg.cloneNode(true);
    copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    copy.setAttribute("style", "background:white");
    saveFile(
      new XMLSerializer().serializeToString(copy),
      "image/svg+xml",
      `${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.svg`,
    );
  }
  return (
    <div className="report-chart-block">
      <div className="report-chart-tools">
        <button onClick={() => setExpanded(!expanded)}>
          {expanded ? "Compact chart" : "Expand chart"}
        </button>
        <button onClick={exportSvg}>
          <Download size={12} />
          Download chart SVG
        </button>
      </div>
      <div
        ref={ref}
        className={`report-chart ${expanded ? "expanded" : ""}`}
        role="img"
        aria-label={label}
      >
        {children}
      </div>
    </div>
  );
}
function Bars({ rows, max = 10, label }) {
  return rows.length ? (
    <>
      <Chart label={label}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            margin={{ top: 12, right: 15, left: -20, bottom: 42 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="#eee7f6"
            />
            <XAxis
              dataKey="name"
              angle={-22}
              textAnchor="end"
              interval={0}
              height={55}
              tick={{ fontSize: 10, fill: "#867095" }}
            />
            <YAxis
              domain={[0, max]}
              tick={{ fontSize: 10 }}
              allowDecimals={max === 10}
            />
            <Tooltip />
            <Bar
              isAnimationActive={false}
              dataKey="value"
              name="Score / count"
              radius={[5, 5, 0, 0]}
            >
              {rows.map((r, i) => (
                <Cell key={i} fill={colors[i % colors.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Chart>
      <details className="chart-data">
        <summary>View chart values</summary>
        <Fields data={Object.fromEntries(rows.map((r) => [r.name, r.value]))} />
      </details>
    </>
  ) : (
    <Empty />
  );
}
function DataTable({ rows, columns, caption }) {
  return (
    <div className="report-table-wrap">
      <table className="report-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map(([key, label], ci) => (
              <th key={`${key}-${ci}`} scope="col">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map(([key, , render], ci) => (
                <td key={`${key}-${ci}`}>
                  {render ? render(row[key], row) : text(row[key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <Empty>No rows available.</Empty>}
    </div>
  );
}
function TopicNarrative({ items, reviews, onEvidence, guide = false }) {
  return (
    <Panel
      title={
        guide ? "Topic-by-topic visitor guidance" : "Topic-by-topic assessment"
      }
      subtitle="Every extracted topic is retained. Counts and citations show the basis; sparse evidence is not a universal claim."
    >
      {asList(items).length ? (
        asList(items).map((item, i) => (
          <article className="report-theme" key={i}>
            <div className="report-item-heading">
              <h3>{name(item.topic || "Topic")}</h3>
              {item.generation_status && (
                <span className="report-badge">
                  {item.generation_status === "evidence_only"
                    ? "Evidence only · narrative missing"
                    : "Specific guidance not generated"}
                </span>
              )}
            </div>
            <p className="report-narrative-text">
              {text(guide ? item.advice : item.assessment)}
            </p>
            <Evidence
              ids={item.evidence_review_ids}
              reviews={reviews}
              onEvidence={onEvidence}
            />
          </article>
        ))
      ) : (
        <Empty>
          Topic-by-topic narrative was not recorded in this report. Existing
          reviews and summaries remain available.
        </Empty>
      )}
    </Panel>
  );
}

export function Executive({ report, onEvidence }) {
  const rec = object(report.recommendation),
    sent = object(report.sentiment),
    guard = object(report.guardrail),
    reviews = asList(report.reviews),
    bd = object(rec.score_breakdown);
  const scores = Object.entries(bd)
    .filter(([, v]) => numeric(v))
    .map(([key, value]) => ({ name: name(key), value }));
  for (const [key, v] of Object.entries(object(sent.aspect_scores)))
    if (numeric(v?.score))
      scores.push({ name: labels[key] || name(key), value: v.score });
  return (
    <div className="report-page">
      <Panel
        title="Balanced assessment"
        subtitle="Executive verdict · explanation model"
      >
        <Metrics
          items={[
            ["Recommendation", rec.recommendation],
            [
              "Visit score",
              numeric(rec.visit_score) ? `${rec.visit_score} / 10` : null,
            ],
            ["Confidence", percent(rec.confidence)],
            ["Data reliability", rec.data_reliability],
          ]}
        />
        <h3 className="report-lead">{text(rec.one_line_verdict)}</h3>
        <p>{text(rec.full_verdict)}</p>
        {(guard.guardrail_summary || guard.analyst_recommendation) && (
          <div className="report-callout">
            <b>Analyst note</b>
            <p>{text(guard.guardrail_summary)}</p>
            <p>{text(guard.analyst_recommendation)}</p>
          </div>
        )}
      </Panel>
      <div className="report-columns">
        <Panel title="Genuine strengths" tone="mint">
          <PointList
            items={rec.pros}
            reviews={reviews}
            onEvidence={onEvidence}
          />
        </Panel>
        <Panel title="Concerns & drawbacks" tone="peach">
          <PointList
            items={rec.cons}
            reviews={reviews}
            onEvidence={onEvidence}
          />
        </Panel>
      </div>
      <Panel
        title="Score breakdown"
        subtitle="All supplied score components and aspect scores, on a 0–10 scale."
      >
        <Bars rows={scores} label="Score breakdown chart" />
        <Fields data={report.final_scoring?.score_breakdown} />
      </Panel>
      <div className="report-columns">
        <Panel title="Standout positive quote" tone="mint">
          {sent.standout_positive_quote ? (
            <blockquote>{text(sent.standout_positive_quote)}</blockquote>
          ) : (
            <Empty />
          )}
        </Panel>
        <Panel title="Standout critical quote" tone="peach">
          {sent.standout_negative_quote ? (
            <blockquote>{text(sent.standout_negative_quote)}</blockquote>
          ) : (
            <Empty />
          )}
        </Panel>
        <Panel title="All positive points" tone="mint">
          <PointList
            items={sent.positive_points}
            reviews={reviews}
            onEvidence={onEvidence}
          />
        </Panel>
        <Panel title="All negative points" tone="peach">
          <PointList
            items={sent.negative_points}
            reviews={reviews}
            onEvidence={onEvidence}
          />
        </Panel>
      </div>
      <TopicNarrative
        items={rec.summary_sections}
        reviews={reviews}
        onEvidence={onEvidence}
      />
      <Panel title="Limitations & unknowns">
        <BulletList items={rec.limitations} />
      </Panel>
    </div>
  );
}
export function DeepSentiment({ report, onEvidence }) {
  const sent = object(report.sentiment),
    reviews = asList(report.reviews),
    emotions = Object.entries(object(sent.emotion_distribution))
      .filter(([, v]) => numeric(v) && v > 0)
      .map(([name, value]) => ({ name, value }));
  const ratingCounts = Object.fromEntries(
    [1, 2, 3, 4, 5].map((n) => [
      n,
      reviews.filter((r) => r.rating === n).length,
    ]),
  );
  const ratings = Object.entries(
    Object.keys(object(sent.rating_counts)).length
      ? sent.rating_counts
      : ratingCounts,
  )
    .sort((a, b) => Number(b[0]) - Number(a[0]))
    .map(([key, value]) => ({ name: `${key} stars`, value }));
  const aspects = Object.entries(object(sent.aspect_scores)).map(
    ([key, v]) => ({ key, ...object(v), name: labels[key] || name(key) }),
  );
  const scored = aspects.filter((a) => numeric(a.score));
  const trend = object(sent.temporal_trend),
    crowd = object(sent.crowd_profile);
  return (
    <div className="report-page">
      <Panel title="Sentiment summary">
        <Metrics
          items={[
            ["Overall sentiment", sent.overall_sentiment],
            ["Sentiment score", sent.sentiment_score, "Scale: −1 to +1"],
            ["Emotional tone", sent.emotional_tone],
            ["Review diversity", sent.review_diversity],
          ]}
        />
      </Panel>
      <div className="report-columns">
        <Panel
          title="Emotion distribution"
          subtitle="Model-classified emotions across the review sample."
        >
          {emotions.length ? (
            <>
              <Chart label="Emotion distribution donut chart">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      isAnimationActive={false}
                      data={emotions}
                      dataKey="value"
                      nameKey="name"
                      innerRadius="48%"
                      outerRadius="70%"
                      paddingAngle={3}
                    >
                      {emotions.map((e, i) => (
                        <Cell key={e.name} fill={colors[i % colors.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </Chart>
              <Fields data={sent.emotion_distribution} />
            </>
          ) : (
            <Empty>Emotion data was not supplied.</Empty>
          )}
        </Panel>
        <Panel
          title="Rating distribution"
          subtitle="Stars from the collected reviews, not all Google visitors."
        >
          <Bars
            rows={ratings}
            max={Math.max(1, ...ratings.map((r) => r.value))}
            label="Star rating distribution chart"
          />
        </Panel>
      </div>
      <Panel
        title="Aspect-based scores"
        subtitle="Radar profile, mention counts, summaries, and review evidence."
      >
        {scored.length >= 3 ? (
          <Chart label="Aspect score radar chart">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={scored} outerRadius="65%">
                <PolarGrid stroke="#e7dcef" />
                <PolarAngleAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "#816496" }}
                />
                <PolarRadiusAxis domain={[0, 10]} tick={{ fontSize: 9 }} />
                <Radar
                  isAnimationActive={false}
                  name="Aspect score"
                  dataKey="score"
                  stroke="#9464d2"
                  fill="#b38ae7"
                  fillOpacity={0.32}
                />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </Chart>
        ) : (
          <Empty>
            At least three scored aspects are needed for a radar profile.
          </Empty>
        )}
        <DataTable
          caption="Aspect scores and evidence"
          rows={aspects}
          columns={[
            ["name", "Aspect"],
            ["score", "Score / 10"],
            ["reviews_mentioning", "Mentions"],
            ["summary", "Summary"],
            [
              "evidence_review_ids",
              "Evidence",
              (ids) => (
                <Evidence ids={ids} reviews={reviews} onEvidence={onEvidence} />
              ),
            ],
          ]}
        />
      </Panel>
      <Panel
        title="Temporal sentiment trend"
        subtitle="Model interpretation of a limited sample, not a statistically validated business trend."
      >
        <Metrics
          items={[
            ["Recent sentiment", trend.recent_sentiment],
            ["Recent score", trend.recent_score],
            ["Older sentiment", trend.older_sentiment],
            ["Older score", trend.older_score],
            ["Overall trend", trend.trend],
          ]}
        />
        <p>{text(trend.trend_explanation)}</p>
      </Panel>
      <Panel title="Crowd profile">
        <Fields data={crowd} />
      </Panel>
      <Panel title="Key themes">
        {asList(sent.themes).length ? (
          asList(sent.themes).map((t, i) => (
            <article className="report-theme" key={i}>
              <div className="report-item-heading">
                <h3>{text(t.name)}</h3>
                <span className="report-badge">
                  {text(t.sentiment)} · {text(t.frequency)} mentions
                </span>
              </div>
              <p>{text(t.evidence)}</p>
              {t.representative_quote && (
                <blockquote>{text(t.representative_quote)}</blockquote>
              )}
              <Evidence
                ids={t.evidence_review_ids}
                reviews={reviews}
                onEvidence={onEvidence}
              />
            </article>
          ))
        ) : (
          <Empty />
        )}
      </Panel>
      <div className="report-columns">
        <Panel title="Positive keywords" tone="mint">
          <div className="report-chips">
            {asList(sent.positive_keywords).map((t, i) => (
              <span key={i}>{text(t)}</span>
            ))}
          </div>
          {!asList(sent.positive_keywords).length && <Empty />}
        </Panel>
        <Panel title="Negative keywords" tone="peach">
          <div className="report-chips">
            {asList(sent.negative_keywords).map((t, i) => (
              <span key={i}>{text(t)}</span>
            ))}
          </div>
          {!asList(sent.negative_keywords).length && <Empty />}
        </Panel>
      </div>
      <Panel
        title="Complete topic evidence inventory"
        subtitle="All extracted topics, including minority concerns and mixed feedback, across every successfully analyzed review."
      >
        {asList(sent.topic_inventory).length ? (
          asList(sent.topic_inventory).map((topic, i) => (
            <details className="report-disclosure" key={i}>
              <summary>
                {name(topic.topic)}{" "}
                <span className="report-badge">
                  {topic.reviews_mentioning} reviews ·{" "}
                  {asList(topic.positive_review_ids).length} positive ·{" "}
                  {asList(topic.negative_review_ids).length} negative
                </span>
              </summary>
              {asList(topic.observations).map((observation, j) => (
                <article className="report-theme" key={j}>
                  <h3>
                    {text(observation.review_id)} ·{" "}
                    {text(observation.sentiment)}
                  </h3>
                  <p>{text(observation.detail)}</p>
                  <blockquote>{text(observation.evidence_quote)}</blockquote>
                  <Evidence
                    ids={[observation.review_id]}
                    reviews={reviews}
                    onEvidence={onEvidence}
                  />
                </article>
              ))}
            </details>
          ))
        ) : (
          <Empty>
            Per-review topic extraction was not recorded for this report.
          </Empty>
        )}
      </Panel>
      <Panel title="Per-review sentiment analysis">
        <DataTable
          caption="Individual model sentiment judgments"
          rows={asList(sent.per_review)}
          columns={[
            ["id", "Review"],
            ["sentiment", "Sentiment"],
            ["score", "Score"],
            ["emotion", "Emotion"],
            ["intensity", "Intensity"],
            ["key_phrase", "Key phrase"],
            [
              "id",
              "Source",
              (id) => (
                <Evidence
                  ids={[id]}
                  reviews={reviews}
                  onEvidence={onEvidence}
                />
              ),
            ],
          ]}
        />
      </Panel>
    </div>
  );
}
export function Authenticity({ report, onEvidence }) {
  const g = object(report.guardrail),
    reviews = asList(report.reviews),
    ri = object(g.rating_integrity);
  return (
    <div className="report-page">
      <div className="report-alert">
        <Info size={16} />
        <span>
          These are model and heuristic signals, not proof of fake reviews or a
          verified “true” rating. Missing data is not a clean bill of health.
        </span>
      </div>
      <Panel title="Guardrail & authenticity">
        <Metrics
          items={[
            ["Trust score", percent(g.trust_score)],
            ["Credibility score", percent(g.credibility_score)],
            ["Estimated fake-review risk", percent(g.fake_review_probability)],
            ["Review quality", g.review_quality],
            ["Bias level", g.bias_level],
            ["Bias direction", g.bias_direction],
            [
              "Model-adjusted rating",
              numeric(ri.adjusted_true_rating)
                ? `${ri.adjusted_true_rating} / 5`
                : null,
            ],
          ]}
        />
        <p>{text(g.guardrail_summary)}</p>
        <p>{text(g.analyst_recommendation)}</p>
      </Panel>
      <Panel title="Review statistics">
        <ReviewCounts report={report} />
        <Fields data={g.heuristic_stats} />
      </Panel>
      <div className="report-columns">
        <Panel title="Linguistic analysis">
          <Fields data={g.linguistic_analysis} />
        </Panel>
        <Panel title="Rating integrity">
          <Fields
            data={Object.fromEntries(
              Object.entries(ri).filter(([k]) => k !== "anomalies"),
            )}
          />
          <h3>Anomalies</h3>
          <BulletList items={ri.anomalies} />
        </Panel>
      </div>
      <Panel title="Reviewer behaviour">
        <Fields data={g.reviewer_behavior} />
      </Panel>
      <Panel title="Contradictions in reviews">
        {asList(g.contradiction_analysis).length ? (
          asList(g.contradiction_analysis).map((c, i) => (
            <details className="report-disclosure" key={i}>
              <summary>{text(c.aspect)}</summary>
              <div className="report-columns">
                <div className="report-callout mint">
                  <b>Positive claim</b>
                  <p>{text(c.positive_claim)}</p>
                </div>
                <div className="report-callout peach">
                  <b>Negative claim</b>
                  <p>{text(c.negative_claim)}</p>
                </div>
              </div>
              <p>
                <b>Model interpretation:</b> {text(c.resolution)}
              </p>
            </details>
          ))
        ) : (
          <Empty />
        )}
      </Panel>
      <Panel title="Per-aspect credibility">
        <DataTable
          caption="Model-reported aspect credibility"
          rows={Object.entries(object(g.aspect_credibility)).map(
            ([key, v]) => ({ aspect: name(key), ...object(v) }),
          )}
          columns={[
            ["aspect", "Aspect"],
            ["credible", "Credible"],
            ["confidence", "Confidence", percent],
            ["note", "Note"],
          ]}
        />
      </Panel>
      <Panel title="Suspicious patterns">
        <BulletList
          items={g.suspicious_patterns}
          empty="No suspicious patterns were supplied. This is not proof of authenticity."
        />
      </Panel>
      <div className="report-columns">
        <Panel
          title="Genuine positives"
          subtitle="Model-reported, with supporting IDs where supplied."
          tone="mint"
        >
          <PointList
            items={g.genuine_positives}
            reviews={reviews}
            onEvidence={onEvidence}
          />
        </Panel>
        <Panel
          title="Genuine concerns"
          subtitle="Model-reported severity; investigate the source evidence."
          tone="peach"
        >
          <PointList
            items={g.genuine_concerns}
            reviews={reviews}
            onEvidence={onEvidence}
          />
        </Panel>
      </div>
      <Panel
        title="Reported facts"
        subtitle="The engine’s verified_facts field; model-generated entries are not independently confirmed."
      >
        <BulletList items={g.verified_facts} />
        <h3>Model-reported observations (not independently verified)</h3>
        <BulletList items={g.reported_observations} />
      </Panel>
    </div>
  );
}
export function VisitorGuide({ report, onEvidence }) {
  const rec = object(report.recommendation),
    crowd = object(report.sentiment?.crowd_profile);
  return (
    <div className="report-page">
      <div className="report-columns">
        <Panel title="Best for" tone="mint">
          <PointList
            items={
              asList(rec.best_for_evidence).length
                ? rec.best_for_evidence
                : rec.best_for
            }
            reviews={asList(report.reviews)}
            onEvidence={onEvidence}
          />
        </Panel>
        <Panel title="Avoid if" tone="peach">
          <PointList
            items={
              asList(rec.avoid_if_evidence).length
                ? rec.avoid_if_evidence
                : rec.avoid_if
            }
            reviews={asList(report.reviews)}
            onEvidence={onEvidence}
          />
        </Panel>
      </div>
      <Panel title="Best time to visit">
        <p className="report-lead">
          {rec.best_time || "Not determinable from available reviews."}
        </p>
        <p className="report-subtitle">
          Review-based advice; check current hours and conditions before
          visiting.
        </p>
      </Panel>
      <Panel title="Actionable visitor tips">
        <ol className="report-list numbered">
          {asList(rec.visitor_tips).map((tip, i) => (
            <li key={i}>{text(tip)}</li>
          ))}
        </ol>
        {!asList(rec.visitor_tips).length && <Empty />}
      </Panel>
      <Panel title="Visitor profile & accessibility">
        <Fields data={crowd} />
      </Panel>
      <TopicNarrative
        items={rec.guide_sections}
        reviews={asList(report.reviews)}
        onEvidence={onEvidence}
        guide
      />
      <Panel title="Planning limitations">
        <BulletList items={rec.limitations} />
      </Panel>
    </div>
  );
}
export function Audit({ report, onEvidence }) {
  const v = object(report.verification),
    reviews = asList(report.reviews),
    status = v.verification_status || v.status || "UNKNOWN";
  return (
    <div className="report-page">
      <div className="report-alert">
        <ShieldCheck size={17} />
        <span>
          {["UNKNOWN", "UNAVAILABLE"].includes(status)
            ? "Audit unavailable or incomplete. No successful verification is implied."
            : "This is a limited model-to-model audit, not independent ground-truth validation."}{" "}
          {numeric(v.coverage?.audited_review_count)
            ? `Full-review audit coverage: ${v.coverage.audited_review_count} of ${v.coverage.input_review_count} reviews.`
            : "Audit coverage was not recorded; do not assume every review was checked."}{" "}
          Reported agreement is not measured model accuracy.
        </span>
      </div>
      <Panel title="Verification & audit">
        <Metrics
          items={[
            ["Audit status", status],
            ["Model-reported agreement", percent(v.accuracy)],
            ["Hallucination flag", v.hallucination_detected],
            ["Correction proposals", asList(v.corrections).length],
            ["Corrections applied (reported)", v.corrections_count],
          ]}
        />
        {v.reason && <p>{text(v.reason)}</p>}
        <p>{text(v.verification_notes)}</p>
      </Panel>
      <Panel title="Field-by-field cross-verification">
        {["sentiment", "aspects", "keywords", "guardrail", "evidence"].map(
          (key) => {
            const f = object(v[key]);
            return (
              <details className="report-disclosure" key={key} open>
                <summary>
                  {name(key)}{" "}
                  <span className="report-badge">{f.status || "UNKNOWN"}</span>
                </summary>
                <h3>Observations</h3>
                <BulletList
                  items={f.observations}
                  empty="No observations supplied; no successful check is implied."
                />
                <h3>Flagged issues</h3>
                <BulletList items={f.issues} />
                {asList(f.unsupported_claims).length > 0 && (
                  <>
                    <h3>Unsupported claims</h3>
                    <BulletList items={f.unsupported_claims} />
                  </>
                )}
              </details>
            );
          },
        )}
      </Panel>
      <Panel
        title="Corrections detail"
        subtitle="Recorded proposals and cited evidence. Evidence IDs alone do not prove a correction was applied."
      >
        {asList(v.corrections).length ? (
          asList(v.corrections).map((c, i) => (
            <details className="report-disclosure" key={i} open>
              <summary>
                {i + 1}. {text(c.field)}
                <span className="report-badge">
                  {asList(c.evidence_review_ids).length
                    ? "Evidence supplied"
                    : "No evidence supplied"}
                </span>
              </summary>
              <div className="report-columns">
                <div className="report-callout peach">
                  <b>Original claim</b>
                  <p>{text(c.original_claim)}</p>
                </div>
                <div className="report-callout mint">
                  <b>Corrected claim</b>
                  <p>{text(c.corrected_claim)}</p>
                </div>
              </div>
              <p>
                <b>Reason:</b> {text(c.reason)}
              </p>
              <Evidence
                ids={c.evidence_review_ids}
                reviews={reviews}
                onEvidence={onEvidence}
              />
            </details>
          ))
        ) : (
          <Empty>
            No corrections recorded. This does not imply a successful audit.
          </Empty>
        )}
      </Panel>
      <div className="report-columns">
        <Panel title="Missed positive signals" tone="mint">
          <BulletList items={v.missing_positive_evidence} />
        </Panel>
        <Panel title="Missed negative signals" tone="peach">
          <BulletList items={v.missing_negative_evidence} />
        </Panel>
      </div>
    </div>
  );
}
function saveFile(content, type, filename) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function RawData({ report, onDownload }) {
  const [search, setSearch] = useState(""),
    [sort, setSort] = useState("id"),
    [ascending, setAscending] = useState(true),
    [page, setPage] = useState(0);
  const reviews = asList(report.reviews);
  const columns = [
    ...new Set([
      "id",
      "author",
      "rating",
      "text",
      "date",
      "likes",
      ...reviews.flatMap((r) => Object.keys(r)),
    ]),
  ];
  const rows = useMemo(
    () =>
      reviews
        .map((r, i) => ({ id: `r${i + 1}`, ...r }))
        .filter((r) =>
          Object.values(r).some((v) =>
            text(v).toLowerCase().includes(search.toLowerCase()),
          ),
        )
        .sort((a, b) => {
          const x = a[sort],
            y = b[sort];
          return (
            (numeric(x) && numeric(y)
              ? x - y
              : text(x).localeCompare(text(y), undefined, { numeric: true })) *
            (ascending ? 1 : -1)
          );
        }),
    [reviews, search, sort, ascending],
  );
  function csv() {
    const cell = (v) =>
      '"' +
      (v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v))
        .replaceAll('"', '""')
        .replace(/^[=+@-]/, "'$&") +
      '"';
    saveFile(
      "\uFEFF" +
        [
          columns.map(cell).join(","),
          ...rows.map((r) => columns.map((c) => cell(r[c])).join(",")),
        ].join("\r\n"),
      "text/csv;charset=utf-8",
      "placewise-reviews.csv",
    );
  }
  return (
    <div className="report-page">
      <Panel title="Review statistics">
        <ReviewCounts report={report} />
      </Panel>
      <Panel
        title="Scraped reviews"
        subtitle="Search any field, sort columns, inspect full text, and export the filtered table."
      >
        <div className="raw-controls">
          <label>
            <Search size={15} />
            <input
              aria-label="Search raw reviews"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              placeholder="Search reviews, authors, dates…"
            />
          </label>
          <button className="text-button" onClick={csv}>
            <Download size={15} />
            Download reviews CSV
          </button>
        </div>
        <div className="report-table-wrap">
          <table className="report-table">
            <caption>Scraped reviews · {rows.length} matching rows</caption>
            <thead>
              <tr>
                {columns.map((c) => (
                  <th
                    scope="col"
                    key={c}
                    aria-sort={
                      sort === c
                        ? ascending
                          ? "ascending"
                          : "descending"
                        : "none"
                    }
                  >
                    <button
                      onClick={() => {
                        setSort(c);
                        setAscending(sort === c ? !ascending : true);
                        setPage(0);
                      }}
                    >
                      {name(c)} {sort === c ? (ascending ? "↑" : "↓") : "↕"}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(page * 10, page * 10 + 10).map((r, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c}>{text(r[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && <Empty>No reviews match this search.</Empty>}
        <div className="raw-pagination">
          <span>
            {rows.length
              ? `${page * 10 + 1}–${Math.min(rows.length, page * 10 + 10)} of ${rows.length}`
              : "0 reviews"}
          </span>
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <button
            disabled={(page + 1) * 10 >= rows.length}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      </Panel>
      <Panel title="Verification JSON">
        <pre className="report-json" tabIndex={0}>
          {JSON.stringify(report.verification || {}, null, 2)}
        </pre>
      </Panel>
      <Panel
        title="Full report & export"
        subtitle="Every field from the engine is retained, including additional model output and metadata."
      >
        <button className="primary-button" onClick={onDownload}>
          <Download size={16} />
          Download full report (.json)
        </button>
        <details className="report-disclosure">
          <summary>Inspect complete report JSON</summary>
          <pre className="report-json" tabIndex={0}>
            {JSON.stringify(report, null, 2)}
          </pre>
        </details>
      </Panel>
    </div>
  );
}
export default function ReportDetails({ tab, report, onEvidence, onDownload }) {
  const props = { report, onEvidence };
  switch (tab) {
    case "verdict":
      return <Executive {...props} />;
    case "sentiment":
      return <DeepSentiment {...props} />;
    case "guardrail":
      return <Authenticity {...props} />;
    case "guide":
      return <VisitorGuide {...props} />;
    case "audit":
      return <Audit {...props} />;
    case "data":
      return <RawData report={report} onDownload={onDownload} />;
    default:
      return null;
  }
}
