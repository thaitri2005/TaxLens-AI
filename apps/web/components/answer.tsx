"use client";

import { useState } from "react";
import { ThumbDownIcon, ThumbUpIcon } from "./icons";
import { CitationLine } from "./tags";
import { request } from "../lib/api";
import type { Copy } from "../lib/copy";
import type { Answer } from "../lib/types";
export function AnswerCard({ answer, copy }: { answer: Answer; copy: Copy }) {
  const statusMessage = copy.statusMessages[answer.status];
  const body = answer.answer || answer.interpretation;
  return <div className="answer-card">
    <span className="answer-status">{answer.status}</span>
    {statusMessage && <p className="answer-note">{statusMessage}</p>}
    {body && <div className="answer-text">{body}</div>}
    {answer.confirmed_facts.length > 0 && <div className="confirmed-facts">
      <p className="eyebrow">{copy.confirmedFacts}</p>
      {answer.confirmed_facts.map((fact, index) => <p key={`${index}-${fact.text}`}>{fact.text} <span className="fact-citations">[{fact.citation_numbers.join(", ")}]</span></p>)}
    </div>}
    {answer.uncertainties.length > 0 && <div className="uncertainties">
      <strong>{copy.uncertainties}</strong><br />
      {answer.uncertainties.map(item => <span key={item}>{item}<br /></span>)}
    </div>}
    {(answer.practical_advice?.length ?? 0) > 0 && <div className="practical-advice">
      <strong>{copy.practicalAdvice}</strong>
      <ul>{answer.practical_advice?.map(item => <li key={item}>{item}</li>)}</ul>
    </div>}
    {answer.review_actions.length > 0 && <div className="review-actions">
      <strong>{copy.reviewActions}</strong>
      {answer.review_actions.map(action => <span key={action}>• {action}</span>)}
    </div>}
    {answer.citations.length > 0 && <div className="answer-citations">
      <p className="eyebrow">{copy.sources}</p>
      {answer.citations.map((citation, index) => <CitationLine key={`${citation.document_number}-${index}`} citation={citation} copy={copy} number={index + 1} />)}
    </div>}
    {answer.question_id && <AnswerFeedback questionId={answer.question_id} copy={copy} />}
    <p className="disclaimer">{answer.disclaimer}</p>
  </div>;
}

// A thumbs up or down on an answer, stored with the question for the evaluation's gold set.
export function AnswerFeedback({ questionId, copy }: { questionId: string; copy: Copy }) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function send(choice: "up" | "down", note?: string) {
    setError("");
    try {
      await request(`/questions/${questionId}/feedback`, { method: "POST", body: JSON.stringify({ rating: choice, comment: note || null }) });
      setSent(true);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : copy.feedback.failed);
    }
  }

  if (sent) return <p className="answer-feedback" role="status">{copy.feedback.thanks}</p>;
  return <div className="answer-feedback">
    <span>{copy.feedback.question}</span>
    <button type="button" aria-pressed={rating === "up"} className={rating === "up" ? "selected" : ""} onClick={() => { setRating("up"); void send("up"); }}><ThumbUpIcon /> {copy.feedback.up}</button>
    <button type="button" aria-pressed={rating === "down"} className={rating === "down" ? "selected" : ""} onClick={() => setRating("down")}><ThumbDownIcon /> {copy.feedback.down}</button>
    {rating === "down" && <form onSubmit={event => { event.preventDefault(); void send("down", comment.trim()); }}>
      <input name="comment" autoComplete="off" value={comment} maxLength={1000} aria-label={copy.feedback.placeholder} placeholder={copy.feedback.placeholder} onChange={event => setComment(event.target.value)} />
      <button type="submit">{copy.feedback.send}</button>
    </form>}
    {error && <small role="alert">{error}</small>}
  </div>;
}
