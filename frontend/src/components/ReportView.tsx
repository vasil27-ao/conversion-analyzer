import type { AgentResult } from "../types";
import {
  SCORE_SCALE_EXPLANATION,
  presentClientText,
} from "../clientLanguage";
import { downloadReportHtml } from "../downloadReport";
import { BacklogTable } from "./BacklogTable";
import { BlockSection } from "./BlockSection";
import { ProblemsList } from "./ProblemsList";
import { ScoreBadge } from "./ScoreBadge";

interface ReportViewProps {
  analysisId: string;
  url: string;
  result: AgentResult;
  onNewAnalysis: () => void;
}

export function ReportView({ analysisId, url, result, onNewAnalysis }: ReportViewProps) {
  const { overall } = result;

  return (
    <section className="report">
      <header className="report-hero">
        <div className="report-hero-copy">
          <p className="eyebrow">Готовый отчёт</p>
          <h1>Общая оценка страницы</h1>
          <p className="status-url">{url}</p>
          <p className="summary">{presentClientText(overall.summary)}</p>
          <p className="meta-line">
            {`Оценено критериев: ${overall.applicable_count} · не применимо (N/A): ${overall.na_count}`}
          </p>
          <div className="actions">
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => downloadReportHtml(url, result, analysisId)}
            >
              Скачать отчёт
            </button>
            <button className="btn btn-secondary" type="button" onClick={onNewAnalysis}>
              Новый анализ
            </button>
          </div>
        </div>
        <aside className="report-scoreboard">
          <p className="scoreboard-label">Конверсионный потенциал</p>
          <ScoreBadge score={overall.score} kind="overall" />
          <p className="overall-level">
            Уровень <em>{overall.level}</em>
          </p>
        </aside>
      </header>

      <section className="report-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Методика</p>
            <h2>Оценка по блокам</h2>
          </div>
        </div>
        <p className="scale-note">{SCORE_SCALE_EXPLANATION}</p>
        <div className="blocks">
          {result.blocks.map((block) => (
            <BlockSection key={block.block_id} block={block} />
          ))}
        </div>
      </section>

      <section className="report-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Диагностика</p>
            <h2>Найденные проблемы</h2>
          </div>
        </div>
        <ProblemsList problems={result.problems} />
      </section>

      <section className="report-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">План работ</p>
            <h2>Задачи на улучшение</h2>
          </div>
        </div>
        <BacklogTable backlog={result.backlog} />
      </section>
    </section>
  );
}
