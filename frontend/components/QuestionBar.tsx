"use client";

import { FormEvent, useState } from "react";
import { API_BASE } from "@/lib/api";

type Answer = { answer: string; source_ids: string[]; data_status: string; route: string };

export function QuestionBar({ enabled, disabledReason }: { enabled: boolean; disabledReason?: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || !API_BASE || !enabled) return;
    setLoading(true);
    setError("");
    setAnswer(null);
    try {
      const response = await fetch(`${API_BASE}/api/rag/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: question.trim() }) });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message ?? (response.status === 429 ? "Question limit reached. Try again in one minute." : "The answer service is unavailable."));
      }
      setAnswer(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The answer service is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="dashboard-card ask" aria-labelledby="ask-title">
      <div>
        <p className="section-label">Grounded project Q&amp;A</p>
        <h2 id="ask-title">Ask about the model or its latest error</h2>
      </div>
      <form onSubmit={submit} className="ask-form">
        <label className="sr-only" htmlFor="question">Question</label>
        <input id="question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={500} placeholder="What was yesterday's MAE?" disabled={loading} />
        <button disabled={loading || !question.trim() || !API_BASE || !enabled}>{loading ? "Checking..." : "Ask"}</button>
      </form>
      <div className="answer" aria-live="polite">
        {!enabled && disabledReason ? <p className="disabled-reason">{disabledReason}</p> : null}
        {error ? <p className="error">{error}</p> : null}
        {answer ? <><p>{answer.answer}</p><div className="evidence"><span>{answer.data_status}</span>{answer.source_ids.map((source) => <span key={source}>{source}</span>)}</div></> : null}
      </div>
    </section>
  );
}
