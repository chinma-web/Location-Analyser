import React from "react";
import {
  ArrowUpRight,
  ShieldCheck,
  MapPin,
  ExternalLink,
  ChevronDown,
} from "lucide-react";
import "./report.css";

export const reportTabs = [
  ["overview", "Overview"],
  ["verdict", "Executive verdict"],
  ["sentiment", "Deep sentiment"],
  ["guardrail", "Authenticity"],
  ["guide", "Visitor guide"],
  ["audit", "Verification & audit"],
  ["data", "Raw data & export"],
];
export const sectionNames = Object.fromEntries([
  ...reportTabs,
  ["reviews", "Review explorer"],
  ["method", "How it works"],
]);
export const labels = {
  food_quality: "Food quality",
  service: "Service",
  ambience: "Ambience",
  value_for_money: "Value for money",
  cleanliness: "Cleanliness",
  accessibility: "Accessibility",
  crowd_wait_time: "Crowd / wait time",
};
export const asList = (value) => (Array.isArray(value) ? value : []);
export const object = (value) =>
  value && typeof value === "object" && !Array.isArray(value) ? value : {};
export const text = (value) =>
  value == null || value === ""
    ? "Not available"
    : typeof value === "object"
      ? JSON.stringify(value)
      : typeof value === "boolean"
        ? value
          ? "Yes"
          : "No"
        : String(value);
export const numeric = (value) =>
  typeof value === "number" && Number.isFinite(value);
export const percent = (value) =>
  numeric(value) ? `${Math.round(value * 100)}%` : "Not available";
export const name = (key) =>
  labels[key] || key.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export function Empty({
  children = "This field was not returned in the report.",
}) {
  return <p className="report-empty">{children}</p>;
}
export function Panel({
  title,
  subtitle,
  children,
  tone = "",
  className = "",
}) {
  return (
    <section className={`card report-panel ${tone} ${className}`}>
      <h2>{title}</h2>
      {subtitle && <p className="report-subtitle">{subtitle}</p>}
      <div className="report-panel-body">{children}</div>
    </section>
  );
}
export function Metrics({ items }) {
  return (
    <div className="report-metrics">
      {items.map(([label, value, detail]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{text(value)}</strong>
          {detail && <small>{detail}</small>}
        </div>
      ))}
    </div>
  );
}
export function Evidence({ ids, reviews, onEvidence }) {
  const all = asList(ids);
  const valid = all.filter((id) =>
    reviews.some((r, i) => (r.id || `r${i + 1}`) === id),
  );
  const invalid = all.filter((id) => !valid.includes(id));
  return (
    <div className="report-evidence">
      {valid.length > 0 && (
        <button onClick={() => onEvidence(valid)}>
          Read {valid.length} linked review{valid.length === 1 ? "" : "s"}{" "}
          <ArrowUpRight size={13} />
        </button>
      )}
      <span>{all.join(", ") || "No review IDs supplied"}</span>
      {invalid.length > 0 && (
        <small>Unresolved citations: {invalid.join(", ")}</small>
      )}
    </div>
  );
}
export function BulletList({ items, empty }) {
  const list = asList(items);
  return list.length ? (
    <ul className="report-list">
      {list.map((item, i) => (
        <li key={i}>{text(item)}</li>
      ))}
    </ul>
  ) : (
    <Empty>{empty || "No entries supplied."}</Empty>
  );
}
export function Fields({ data }) {
  const entries = Object.entries(object(data));
  return entries.length ? (
    <dl className="report-fields">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{name(key)}</dt>
          <dd>{text(value)}</dd>
        </div>
      ))}
    </dl>
  ) : (
    <Empty />
  );
}
function SafeLink({ url }) {
  let valid = false;
  try {
    valid = ["https:", "http:"].includes(new URL(url).protocol);
  } catch {}
  return valid ? (
    <a className="report-link" href={url} target="_blank" rel="noreferrer">
      {url}
      <ExternalLink size={12} />
    </a>
  ) : (
    <span>{text(url)}</span>
  );
}
export function PointList({ items, reviews, onEvidence }) {
  const list = asList(items);
  return list.length ? (
    <div className="report-points">
      {list.map((value, i) => {
        const p = object(value);
        return (
          <article key={i}>
            <div className="report-item-heading">
              <h3>
                {text(
                  p.claim ||
                    p.point ||
                    p.text ||
                    p.description ||
                    p.aspect ||
                    value,
                )}
              </h3>
              {(p.weight || p.severity) && (
                <span className="report-badge">
                  {text(p.weight || p.severity)}
                </span>
              )}
            </div>
            {p.evidence && <p>{text(p.evidence)}</p>}
            {p.source && <small>Source: {text(p.source)}</small>}
            {p.confidence != null && (
              <small>Model confidence: {percent(p.confidence)}</small>
            )}
            {(p.evidence_review_ids || p.supporting_review_ids) && (
              <Evidence
                ids={p.evidence_review_ids || p.supporting_review_ids}
                reviews={reviews}
                onEvidence={onEvidence}
              />
            )}
          </article>
        );
      })}
    </div>
  ) : (
    <Empty />
  );
}
export function ReviewCounts({ report }) {
  const stats = object(report.review_stats);
  return (
    <Metrics
      items={[
        ["Raw scraped", stats.raw_scraped_count],
        ["Usable text", stats.usable_text_review_count],
        ["After cleaning", stats.cleaned_review_count],
        ["Analyzed", stats.analyzed_review_count],
      ]}
    />
  );
}
export function ReportContext({ report, onAudit }) {
  const place = object(report.place_info),
    v = object(report.verification),
    m = object(report.model_info),
    rec = object(report.recommendation);
  const status = v.verification_status || v.status || "UNKNOWN";
  const models = [
    ["Analyst", m.model_1?.sentiment_model || m.model_a?.model],
    ["Guardrail", m.model_1?.guardrail_model || m.model_a?.fast_model],
    ["Verifier", m.model_2?.model || m.model_b?.model],
    ["Explanation", m.model_3?.model || m.verdict_model?.model],
  ];
  return (
    <div className="report-context">
      {(place.permanently_closed || place.temporarily_closed) && (
        <div className="report-alert">
          {place.permanently_closed
            ? "Permanently closed"
            : "Temporarily closed"}{" "}
          — check the current business status before visiting.
        </div>
      )}
      <ReviewCounts report={report} />
      <div className="report-status-strip">
        <div>
          <ShieldCheck size={17} />
          <b>Audit: {status}</b>
          <span>Model-reported agreement: {percent(v.accuracy)}</span>
          <span>Hallucination flag: {text(v.hallucination_detected)}</span>
          <span>
            Corrections recorded: {text(asList(v.corrections).length)}
          </span>
        </div>
        <button onClick={onAudit}>
          Inspect audit <ArrowUpRight size={13} />
        </button>
      </div>
      <div className="report-model-strip">
        {models.map(([role, model]) => (
          <span key={role}>
            <b>{role}</b>
            {model || "Not recorded"}
          </span>
        ))}
        <span>
          <b>Recommendation confidence</b>
          {percent(rec.confidence)}
        </span>
        <span>
          <b>Data reliability</b>
          {text(rec.data_reliability)}
        </span>
      </div>
      <details className="report-metadata">
        <summary>
          <MapPin size={16} /> Place metadata{" "}
          <span>{place.name || report.location}</span>
          <ChevronDown size={16} />
        </summary>
        <div className="report-metadata-body">
          {(place.permanently_closed || place.temporarily_closed) && (
            <div className="report-alert">
              {place.permanently_closed
                ? "Permanently closed"
                : "Temporarily closed"}{" "}
              — reported by the place data source.
            </div>
          )}
          <Fields
            data={{
              name: place.name,
              category: place.category,
              location_type: place.location_type,
              address: place.address,
              google_score: place.google_score,
              total_google_reviews: place.review_count,
              price: place.price,
              phone: place.phone,
              description: place.description,
              permanently_closed: place.permanently_closed,
              temporarily_closed: place.temporarily_closed,
            }}
          />
          <div className="report-chips">
            {asList(place.subtypes).map((s, i) => (
              <span key={i}>{text(s)}</span>
            ))}
          </div>
          <p>
            <b>Website: </b>
            {place.website ? <SafeLink url={place.website} /> : "Not available"}
          </p>
          <h3>Opening hours</h3>
          <BulletList
            items={asList(place.opening_hours).map((h) =>
              typeof h === "string"
                ? h
                : h.day
                  ? `${h.day}: ${text(h.hours)}`
                  : h,
            )}
            empty="Opening hours were not supplied."
          />
        </div>
      </details>
    </div>
  );
}

export function placeIcon(place) {
  const category =
    `${place?.category || ""} ${asList(place?.subtypes).join(" ")}`.toLowerCase();
  const icons = [
    ["restaurant|food|pizza", "🍽️"],
    ["cafe|café|coffee", "☕"],
    ["bar|pub", "🍺"],
    ["bakery", "🥐"],
    ["hotel|lodge|resort", "🏨"],
    ["mall|shopping|store|market", "🛍️"],
    ["cinema|theatre|theater|movie", "🎬"],
    ["museum|gallery|art", "🏛️"],
    ["park|garden|beach|nature", "🌿"],
    ["temple|church|mosque|religious", "🛕"],
    ["hospital|clinic|pharmacy", "🏥"],
    ["gym|fitness|sport|stadium", "💪"],
    ["spa|salon|beauty", "💆"],
    ["school|university|college", "🎓"],
    ["bank|atm", "🏦"],
    ["airport", "✈️"],
    ["station", "🚉"],
    ["amusement|zoo|aquarium", "🎡"],
    ["monument|landmark|historic", "🏛️"],
  ];
  return (
    icons.find(([pattern]) => new RegExp(pattern).test(category))?.[1] || "📍"
  );
}

export function ContentCoverage({ report }) {
  const source = object(report.meta?.analysis_coverage),
    sent = object(source.sentiment || report.sentiment?.coverage),
    guard = object(source.guardrail || report.guardrail?.coverage),
    audit = object(source.verification || report.verification?.coverage),
    narrative = object(
      source.narrative || report.recommendation?.content_coverage,
    );
  const missing = [
    ...asList(narrative.missing_summary_topics),
    ...asList(narrative.missing_guide_topics),
  ];
  return (
    <details
      className="report-metadata content-coverage"
      open={missing.length > 0}
    >
      <summary>
        <ShieldCheck size={16} />
        Review & topic coverage
        <span>
          {numeric(sent.analyzed_review_count)
            ? `${sent.analyzed_review_count} / ${sent.input_review_count} reviews analyzed`
            : "Not recorded for this report"}
        </span>
        <ChevronDown size={16} />
      </summary>
      <div className="report-metadata-body">
        <Metrics
          items={[
            [
              "Sentiment review coverage",
              numeric(sent.analyzed_review_count)
                ? `${sent.analyzed_review_count} / ${sent.input_review_count}`
                : null,
            ],
            [
              "Guardrail review coverage",
              numeric(guard.analyzed_review_count)
                ? `${guard.analyzed_review_count} / ${guard.input_review_count}`
                : null,
            ],
            [
              "Audit review coverage",
              numeric(audit.audited_review_count)
                ? `${audit.audited_review_count} / ${audit.input_review_count}`
                : null,
            ],
            ["Distinct extracted topics", sent.topic_count],
            [
              "Topics explained",
              numeric(narrative.summary_topics_generated)
                ? `${narrative.summary_topics_generated} / ${narrative.topic_count}`
                : null,
            ],
            [
              "Topics with guide sections",
              numeric(narrative.guide_topics_generated)
                ? `${narrative.guide_topics_generated} / ${narrative.topic_count}`
                : null,
            ],
          ]}
        />
        <p>
          Processing coverage is not proof of model correctness. Only collected,
          cleaned text reviews are included—not every Google Maps review.
        </p>
        {missing.length > 0 && (
          <div className="report-alert">
            Some narrative topics were not generated:{" "}
            {[...new Set(missing)].join(", ")}. Evidence-only summaries and
            explicitly missing guidance are shown instead.
          </div>
        )}
      </div>
    </details>
  );
}
