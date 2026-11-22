export function Heading({ eyebrow, title, chip }: { eyebrow: string; title: string; chip: string }) {
  return <div className="section-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div><span className="chip">{chip}</span></div>;
}

export function Empty({ title, text }: { title: string; text: string }) {
  return <div className="empty-state"><span className="empty-icon">⌁</span><h3>{title}</h3>{text && <p>{text}</p>}</div>;
}

export function ResultState({ error, hasResults, emptyTitle, emptyText }: { error: string; hasResults: boolean; emptyTitle: string; emptyText: string }) {
  if (error) return <div className="error-state">{error}</div>;
  return hasResults ? null : <Empty title={emptyTitle} text={emptyText} />;
}
