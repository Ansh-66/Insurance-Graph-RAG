import { useState, useEffect } from "react";
import "./App.css";

const API = "http://localhost:8000";

// Display text for each arm key the API sends back.
const ARM_INFO = {
  no_context: {
    title: "No retrieval",
    subtitle: "The LLM answers from its own training data only.",
  },
  vector: {
    title: "Vector RAG",
    subtitle: "Top-10 most similar 600-character chunks.",
  },
  graph: {
    title: "Graph RAG",
    subtitle: "Finds the companies in the question, walks two hops through the knowledge graph, and uses the evidence sentences on those edges.",
  },
};

// fetch() only rejects on network failure, so a 404 or 500 still "succeeds".
// This turns a bad status into an Error, which .catch() below then handles.
function parseJson(res) {
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
  return res.json();
}

function AnswerCard({ arm, data }) {
  const [showAll, setShowAll] = useState(false)
  const cited = data.passages.filter((p) => data.cited.includes(p.n));
  const shown = showAll ? data.passages : cited
  // Live answers have no score, so data.score is undefined and no badge renders.
  const hasVerdict = data.score && (data.score.correct === "Y" || data.score.correct === "N");
  return (
    <article className="card">
      <h3>{ARM_INFO[arm].title}</h3>
      <p className="card-subtitle">{ARM_INFO[arm].subtitle}</p>
      {hasVerdict && (
        <div>
          <span className={data.score.correct === "Y" ? "badge badge-correct" : "badge badge-wrong"}>
            {data.score.correct === "Y" ? "Correct" : "Wrong"}
          </span>
          {data.score.correct === "Y" && data.score.grounded === "Y" && (
            <span className="badge badge-neutral">grounded</span>
          )}
          {data.score.comment && <p className="score-comment">{data.score.comment}</p>}
        </div>
      )}
      <p className="answer">{data.answer}</p>
      {arm === "graph" && (
        data.seeds.length > 0 ? (
          <p className="seeds">
            Started from:{" "}
            {data.seeds.map((id) => (
              <span key={id} className="seed-tag">{id}</span>
            ))}
          </p>
        ) : (
          <p className="seeds">No company in the question matched a graph node.</p>
        )
      )}
      {/* data.path is built by the backend: the route from the seeds to each cited edge */}
      {arm === "graph" && data.path.length > 0 && (
        <div>
          <p className="eyebrow">PATH</p>
          <ul className="path">
            {data.path.map((e) => (
              // Edges that were walked through but not cited are muted; the label says so too
              <li key={e.id} className={e.cited.length === 0 ? "path-traversed" : undefined}>
                {e.src_name} --{e.relation}--&gt; {e.dst_name}
                {e.status !== "asserted" && ` (${e.status})`}
                {" "}
                {e.cited.length === 0
                  ? "[traversed, not cited]"
                  : `[cited ${e.cited.length === 1 ? "passage" : "passages"} ${e.cited.join(", ")}]`}
              </li>
            ))}
          </ul>
        </div>
      )}
      {shown.map((p) => (
        <div key={p.n} className="passage">
          <p className="passage-text">
            <span className="passage-num">[{p.n}]</span> {p.text}
          </p>
          <a href={p.url} target="_blank" rel="noopener noreferrer">Source</a>
        </div>
      ))}
      {cited.length === 0 && <p className="passage-empty">No sources cited.</p>}
      {data.passages.length > 0 && (
        <button onClick={() => setShowAll(!showAll)}>{showAll ? "Show cited only" : `Show all ${data.passages.length} passages`}</button>)}
    </article>
  );
}

export default function App() {
  const [mode, setMode] = useState("demo");
  const [question, setQuestion] = useState("");
  const [demo, setDemo] = useState(null);
  const [examples, setExamples] = useState([]);
  const [qid, setQid] = useState("q01")
  const [live, setLive] = useState(null);
  const [asking, setAsking] = useState(false);
  // Three separate errors, so one failure does not take down the whole page:
  const [examplesError, setExamplesError] = useState(null); // examples list failed to load
  const [demoFailure, setDemoFailure] = useState(null);     // { qid, message } of the last failed demo fetch
  const [askError, setAskError] = useState(null);           // a live question failed

  useEffect(() => {
    // Guard against stale responses. Every time qid changes, React first runs the
    // cleanup function returned below for the OLD effect, which sets that
    // effect's own `ignore` to true. If the old request finishes late (click q03,
    // then q05 quickly), its .then sees ignore === true and drops the result,
    // so q03 can never overwrite q05.
    let ignore = false;
    fetch(`${API}/api/demo/${qid}`)
      .then(parseJson)
      .then((data) => { if (!ignore) setDemo(data) })
      .catch((err) => { if (!ignore) setDemoFailure({ qid, message: `Could not load ${qid}: ${err.message}` }) })
    return () => { ignore = true };
  }, [qid]);

  useEffect(() => {
    let ignore = false; // same stale-response guard as above
    fetch(`${API}/api/examples`)
      .then(parseJson)
      .then((data) => { if (!ignore) setExamples(data) })
      .catch((err) => { if (!ignore) setExamplesError(err.message) })
    return () => { ignore = true };
  }, []);

  // Loading and error are worked out from the data instead of being stored:
  // we are loading while the demo we hold is not the one selected, unless that
  // selection already failed. The error disappears when another question is picked.
  const demoFailed = demoFailure !== null && demoFailure.qid === qid;
  const demoLoading = (demo === null || demo.id !== qid) && !demoFailed;
  const demoError = demoFailed ? demoFailure.message : null;

  // Page-level error: only when the starting data cannot load. A demo failure
  // counts only while demo is still null, i.e. before the first success.
  if (examplesError || (demo === null && demoError)) {
    return (
      <div className="page">
        <p role="alert" className="inline-error">Can&apos;t reach the backend at {API}. Is uvicorn running?</p>
        <p className="inline-error">{examplesError || demoError}</p>
      </div>
    );
  }
  if (demo === null) return <div className="page"><p>Loading...</p></div>

  function ask() {
    setAsking(true);
    setAskError(null);
    // Previous live results are kept: they are only replaced when a new answer arrives.
    fetch(`${API}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question }),
    })
      .then(parseJson)
      .then((data) => setLive(data))
      .catch((err) => {
        // "Server returned 500" is an HTTP error; anything else means no response at all
        const hint = err.message.startsWith("Server returned")
          ? "The Groq rate limit may have been hit; wait a minute and try again."
          : "Is uvicorn running?";
        setAskError(`Request failed: ${err.message}. ${hint}`);
      })
      .finally(() => setAsking(false))
  }
  return (
    <div className="page">
      <header className="page-header">
        <div className="title-row">
          <h1>Insurance Graph RAG</h1>
          <button onClick={() => setMode(mode === "demo" ? "live" : "demo")}>
            {mode === "demo" ? "Switch to live mode" : "Switch to demo mode"}
          </button>
        </div>
        <p className="lead">Same question, three ways to answer it: no retrieval, vector search over article chunks, and a knowledge graph built from Indian insurance news.</p>
      </header>
      {/* One ternary picks which block of the page exists; the other is not rendered at all. */}
      {mode === "demo" ? (
        <main>
          <div className="picker">
            {examples.map((q) => (
              // aria-pressed tells screen readers (and our CSS) which button is selected
              <button key={q.id} onClick={() => setQid(q.id)} aria-pressed={q.id === qid}>
                <span>{q.id}</span> <span className="picker-type">{q.type}</span>
              </button>
            ))}
          </div>
          {/* aria-live makes screen readers announce the text when it appears */}
          <p className="status" aria-live="polite">{demoLoading ? `Loading ${qid}...` : ""}</p>
          {/* The previous question stays on screen, dimmed, until the new data arrives */}
          <div className={demoLoading ? "is-loading" : undefined}>
            <h2>{demo.question}</h2>
            <div className="gold">
              <p className="eyebrow">GOLD ANSWER</p>
              <p>{demo.gold_answer}</p>
            </div>
            {demoError && <p role="alert" className="inline-error">{demoError}</p>}
            <div className="cards cards-demo">
              <AnswerCard arm="no_context" data={demo.arms.no_context} ></AnswerCard>
              <AnswerCard arm="vector" data={demo.arms.vector} ></AnswerCard>
              <AnswerCard arm="graph" data={demo.arms.graph} ></AnswerCard>
            </div>
          </div>
        </main>
      ) : (
        <main>
          <div className="ask-row">
            <label htmlFor="question" className="visually-hidden">Question</label>
            <input
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question"
              aria-invalid={askError ? "true" : undefined}
              aria-describedby={askError ? "ask-error" : undefined}
            />
            <button className="button-primary" onClick={ask} disabled={asking || question.trim() === ""} >{asking ? "Asking..." : "Ask"}</button>
          </div>
          {askError && <p id="ask-error" role="alert" className="inline-error ask-error">{askError}</p>}
          {live && (
            <section className={asking ? "is-loading" : undefined}>
              {/* Keeps the heading order h1 > h2 > h3 for screen readers; not visible. */}
              <h2 className="visually-hidden">Live answers</h2>
              <div className="cards cards-live">
                <AnswerCard arm="vector" data={live.arms.vector}></AnswerCard>
                <AnswerCard arm="graph" data={live.arms.graph}></AnswerCard>
              </div>
            </section>
          )}
        </main>
      )}
    </div>
  );
}
