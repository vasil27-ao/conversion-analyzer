import type { AnalysisStatus } from "../types";

interface WaitingStateProps {
  url: string;
  status: AnalysisStatus;
}

const STATUS_TEXT: Record<"pending" | "running", string> = {
  pending: "Анализ в очереди",
  running: "Идёт разбор страницы",
};

export function WaitingState({ url, status }: WaitingStateProps) {
  const title =
    status === "pending" || status === "running" ? STATUS_TEXT[status] : "Ожидание результата";
  const phase = status === "pending" ? 1 : 2;

  return (
    <section className="state waiting" aria-live="polite">
      <div className="state-rail" aria-hidden="true">
        <span className={`rail-dot ${phase >= 1 ? "is-on" : ""}`} />
        <span className="rail-line" />
        <span className={`rail-dot ${phase >= 2 ? "is-on" : ""}`} />
        <span className="rail-line" />
        <span className="rail-dot" />
      </div>
      <p className="eyebrow">В процессе</p>
      <h1>{title}</h1>
      <p className="status-url">{url}</p>
      <p className="lede">
        Собираем данные страницы и оцениваем её по 6 блокам методики. Анализ обычно занимает
        1–2 минуты, сложные страницы могут занять больше времени. Вкладку можно не закрывать —
        отчёт появится здесь.
      </p>
      <div className="waiting-bar" aria-hidden="true">
        <span />
      </div>
    </section>
  );
}
