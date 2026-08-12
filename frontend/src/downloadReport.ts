import type {
  AgentResult,
  BacklogItem,
  BlockResult,
  CriterionResult,
  ProblemItem,
} from "./types";
import {
  SCORE_SCALE_EXPLANATION,
  criterionScoreMeaning,
  formatCriterionScoreLabel,
  presentClientText,
} from "./clientLanguage";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatBlockScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "N/A";
  return String(score);
}

function formatCriterionScore(score: CriterionResult["score"]): string {
  return `${formatCriterionScoreLabel(score)} — ${criterionScoreMeaning(score)}`;
}

function priorityOrder(priority: BacklogItem["priority"]): number {
  if (priority === "высокий") return 0;
  if (priority === "средний") return 1;
  return 2;
}

function renderCriterion(criterion: CriterionResult): string {
  const recommendation = criterion.recommendation
    ? `<p class="criterion-rec"><span>Рекомендация</span>${escapeHtml(presentClientText(criterion.recommendation))}</p>`
    : "";
  return `
    <article class="criterion">
      <div class="criterion-top">
        <p class="criterion-id">${escapeHtml(criterion.id)}</p>
        <p class="criterion-score">${escapeHtml(formatCriterionScore(criterion.score))}</p>
      </div>
      <p class="criterion-just">${escapeHtml(presentClientText(criterion.justification))}</p>
      ${recommendation}
    </article>`;
}

function renderBlock(block: BlockResult): string {
  const scoreLabel =
    block.score === null || block.score === undefined
      ? "N/A — не применимо"
      : escapeHtml(formatBlockScore(block.score));
  const criteria = block.criteria.map(renderCriterion).join("");
  return `
    <section class="block">
      <header class="block-header">
        <h3>${escapeHtml(block.block_name)}</h3>
        <div class="block-score">
          <span class="micro-label">Оценка блока</span>
          <strong>${scoreLabel}</strong>
        </div>
      </header>
      <div class="block-analytics">
        <div>
          <span class="micro-label">Что не так</span>
          <p>${escapeHtml(presentClientText(block.what_is_wrong))}</p>
        </div>
        <div>
          <span class="micro-label">Почему важно</span>
          <p>${escapeHtml(presentClientText(block.why_it_matters))}</p>
        </div>
      </div>
      <div class="criteria">${criteria}</div>
    </section>`;
}

function renderProblems(problems: ProblemItem[]): string {
  if (problems.length === 0) {
    return '<p class="empty">Существенных проблем не найдено.</p>';
  }
  const items = problems
    .map(
      (item) => `
      <li>
        <div>
          <strong>${escapeHtml(presentClientText(item.description))}</strong>
          <p class="muted">Где: ${escapeHtml(presentClientText(item.location))}</p>
        </div>
      </li>`,
    )
    .join("");
  return `<ul class="problems">${items}</ul>`;
}

function renderPlan(backlog: BacklogItem[]): string {
  const sorted = [...backlog].sort(
    (a, b) => priorityOrder(a.priority) - priorityOrder(b.priority),
  );
  if (sorted.length === 0) {
    return '<p class="empty">Задач на улучшение пока нет.</p>';
  }
  const rows = sorted
    .map(
      (item) => `
      <article class="plan-item">
        <div class="plan-main">
          <span class="priority priority--${escapeHtml(item.priority)}">${escapeHtml(item.priority)}</span>
          <h4>${escapeHtml(presentClientText(item.task))}</h4>
        </div>
        <dl class="plan-meta">
          <div>
            <dt>Зона страницы</dt>
            <dd>${escapeHtml(presentClientText(item.zone))}</dd>
          </div>
          <div>
            <dt>Ожидаемый эффект</dt>
            <dd>${escapeHtml(presentClientText(item.expected_effect))}</dd>
          </div>
        </dl>
      </article>`,
    )
    .join("");
  return `<div class="plan-list">${rows}</div>`;
}

const REPORT_STYLES = `
  :root {
    color-scheme: light;
    --bg: #eceae4;
    --ink: #0b0b0b;
    --muted: #5f5c56;
    --line: #d2cec5;
    --line-strong: #b8b2a6;
    --surface: #fffcf7;
    --signal: #c9a227;
    --danger: #8a2f2f;
    --high: #1d4638;
    --mid: #8a5d16;
    --font-sans: "Manrope", "Segoe UI", sans-serif;
    --font-display: "Instrument Serif", Georgia, serif;
    --font-mono: "JetBrains Mono", Consolas, monospace;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: var(--font-sans);
    color: var(--ink);
    background:
      radial-gradient(circle at 12% 0%, rgba(201, 162, 39, 0.08), transparent 28%),
      linear-gradient(180deg, #f1efe9 0%, var(--bg) 42%, #e5e1d8 100%);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }
  .page {
    width: min(1120px, calc(100% - 3rem));
    margin: 0 auto;
    padding: 1.25rem 0 4rem;
  }
  .masthead {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: baseline;
    padding-bottom: 0.85rem;
    margin-bottom: 1.6rem;
    border-bottom: 1px solid var(--line-strong);
    font-size: 0.84rem;
  }
  .brand {
    font-weight: 700;
    letter-spacing: 0.01em;
  }
  .masthead-tag {
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.72rem;
    font-weight: 700;
  }
  .eyebrow, .micro-label {
    margin: 0 0 0.45rem;
    color: var(--muted);
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .hero {
    display: grid;
    grid-template-columns: minmax(0, 1.35fr) minmax(14rem, 0.75fr);
    gap: 1.6rem 2.2rem;
    padding-bottom: 1.8rem;
    margin-bottom: 1.4rem;
    border-bottom: 1px solid var(--line-strong);
  }
  .hero h1 {
    margin: 0 0 0.7rem;
    font-family: var(--font-display);
    font-size: clamp(2.2rem, 4vw, 3.1rem);
    font-weight: 400;
    letter-spacing: -0.03em;
    line-height: 1.05;
  }
  .url {
    margin: 0 0 1rem;
    color: var(--muted);
    word-break: break-all;
    font-family: var(--font-mono);
    font-size: 0.84rem;
  }
  .summary {
    margin: 0 0 0.85rem;
    max-width: 40rem;
    font-size: 1.06rem;
    line-height: 1.6;
  }
  .meta {
    margin: 0;
    color: var(--muted);
    font-size: 0.88rem;
  }
  .scoreboard {
    background: var(--ink);
    color: #f4f2ec;
    padding: 1.35rem 1.4rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 1rem;
    min-height: 12.5rem;
  }
  .scoreboard .micro-label { color: rgba(244, 242, 236, 0.62); }
  .score-value {
    margin: 0;
    font-family: var(--font-display);
    font-size: clamp(3.4rem, 7vw, 4.6rem);
    letter-spacing: -0.04em;
    line-height: 0.95;
  }
  .score-value span {
    font-family: var(--font-sans);
    font-size: 1rem;
    font-weight: 600;
    color: rgba(244, 242, 236, 0.55);
  }
  .level {
    margin: 0;
    color: rgba(244, 242, 236, 0.7);
    font-size: 0.95rem;
  }
  .level em {
    color: #fff;
    font-family: var(--font-display);
    font-style: italic;
    font-size: 1.2rem;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.75rem;
    margin: 0 0 2.6rem;
    padding: 0;
  }
  .stats > div {
    background: var(--surface);
    border: 1px solid var(--line);
    padding: 0.85rem 0.95rem;
  }
  .stats dt {
    margin: 0 0 0.35rem;
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .stats dd {
    margin: 0;
    font-family: var(--font-display);
    font-size: 1.7rem;
    letter-spacing: -0.02em;
  }
  .section {
    margin-bottom: 2.8rem;
  }
  .section-heading {
    padding-bottom: 0.85rem;
    margin-bottom: 1.1rem;
    border-bottom: 1px solid var(--line);
  }
  .section-heading h2 {
    margin: 0;
    font-family: var(--font-display);
    font-size: clamp(1.8rem, 3vw, 2.3rem);
    font-weight: 400;
    letter-spacing: -0.02em;
    line-height: 1.05;
  }
  .scale {
    margin: 0 0 1.4rem;
    padding: 0.85rem 1rem;
    background: rgba(11, 11, 11, 0.04);
    border-left: 2px solid var(--signal);
    color: var(--muted);
    font-size: 0.9rem;
    line-height: 1.5;
    max-width: 54rem;
  }
  .block {
    padding: 1.55rem 0;
    border-bottom: 1px solid var(--line);
  }
  .block:last-child { border-bottom: none; }
  .block-header {
    display: flex;
    justify-content: space-between;
    gap: 1.25rem;
    align-items: start;
    margin-bottom: 1.1rem;
  }
  .block-header h3 {
    margin: 0;
    font-family: var(--font-display);
    font-size: clamp(1.45rem, 2.4vw, 1.85rem);
    font-weight: 400;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }
  .block-score {
    text-align: right;
    min-width: 6rem;
  }
  .block-score strong {
    display: block;
    font-family: var(--font-display);
    font-size: 1.7rem;
    font-weight: 400;
    letter-spacing: -0.02em;
  }
  .block-analytics {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem 1.5rem;
    margin-bottom: 1.15rem;
  }
  .block-analytics p {
    margin: 0.2rem 0 0;
    font-size: 0.96rem;
  }
  .criteria {
    display: grid;
    gap: 0.65rem;
  }
  .criterion {
    background: var(--surface);
    border: 1px solid var(--line);
    padding: 0.9rem 1rem;
  }
  .criterion-top {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: baseline;
    margin-bottom: 0.45rem;
  }
  .criterion-id {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 0.8rem;
    font-weight: 600;
  }
  .criterion-score {
    margin: 0;
    color: var(--muted);
    font-size: 0.84rem;
    font-weight: 700;
    text-align: right;
  }
  .criterion-just {
    margin: 0;
    font-size: 0.94rem;
  }
  .criterion-rec {
    margin: 0.55rem 0 0;
    font-size: 0.92rem;
  }
  .criterion-rec span {
    display: block;
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 0.15rem;
  }
  .problems {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 0.9rem;
  }
  .problems li {
    padding: 0.95rem 0;
    border-bottom: 1px solid var(--line);
  }
  .problems li:last-child { border-bottom: none; }
  .problems strong {
    display: block;
    margin-bottom: 0.25rem;
    font-size: 1rem;
  }
  .muted {
    margin: 0;
    color: var(--muted);
    font-size: 0.88rem;
  }
  .empty {
    margin: 0;
    color: var(--muted);
  }
  .plan-list {
    display: grid;
    gap: 0.85rem;
  }
  .plan-item {
    background: var(--surface);
    border: 1px solid var(--line);
    padding: 1rem 1.05rem;
  }
  .plan-main {
    display: grid;
    gap: 0.4rem;
    margin-bottom: 0.75rem;
  }
  .plan-main h4 {
    margin: 0;
    font-family: var(--font-display);
    font-size: 1.25rem;
    font-weight: 400;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }
  .priority {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: lowercase;
    letter-spacing: 0.04em;
  }
  .priority--высокий { color: var(--danger); }
  .priority--средний { color: var(--mid); }
  .priority--низкий { color: var(--muted); }
  .plan-meta {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem 1.25rem;
    margin: 0;
  }
  .plan-meta dt {
    margin: 0 0 0.2rem;
    color: var(--muted);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .plan-meta dd {
    margin: 0;
    font-size: 0.92rem;
  }
  @media (max-width: 820px) {
    .page { width: min(100% - 1.35rem, 1120px); }
    .hero, .block-analytics, .plan-meta, .stats {
      grid-template-columns: 1fr;
    }
    .scoreboard { min-height: auto; }
    .block-header { flex-direction: column; }
    .block-score { text-align: left; }
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media print {
    body { background: #fff; }
    .page { width: 100%; padding: 0; }
    .scoreboard { break-inside: avoid; }
    .block, .plan-item, .criterion { break-inside: avoid; }
  }
`;

export function buildReportHtml(url: string, result: AgentResult): string {
  const { overall } = result;
  const generatedAt = new Date().toLocaleString("ru-RU");
  const problemsCount = result.problems.length;
  const tasksCount = result.backlog.length;

  return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Отчёт по конверсионности</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet" />
  <style>${REPORT_STYLES}</style>
</head>
<body>
  <div class="page">
    <header class="masthead">
      <span class="brand">Conversion Analyzer</span>
      <span class="masthead-tag">CRO · methodology report</span>
    </header>

    <section class="hero">
      <div>
        <p class="eyebrow">Готовый отчёт</p>
        <h1>Общая оценка страницы</h1>
        <p class="url">${escapeHtml(url)}</p>
        <p class="summary">${escapeHtml(presentClientText(overall.summary))}</p>
        <p class="meta">Сформирован: ${escapeHtml(generatedAt)}</p>
      </div>
      <aside class="scoreboard">
        <p class="micro-label">Конверсионный потенциал</p>
        <p class="score-value">${escapeHtml(String(overall.score))} <span>/ 100</span></p>
        <p class="level">Уровень <em>${escapeHtml(overall.level)}</em></p>
      </aside>
    </section>

    <dl class="stats">
      <div>
        <dt>Критериев</dt>
        <dd>${overall.applicable_count}</dd>
      </div>
      <div>
        <dt>Не применимо</dt>
        <dd>${overall.na_count}</dd>
      </div>
      <div>
        <dt>Проблем</dt>
        <dd>${problemsCount}</dd>
      </div>
      <div>
        <dt>Задач</dt>
        <dd>${tasksCount}</dd>
      </div>
    </dl>

    <section class="section">
      <div class="section-heading">
        <p class="eyebrow">Методика</p>
        <h2>Оценка по блокам</h2>
      </div>
      <p class="scale">${escapeHtml(SCORE_SCALE_EXPLANATION)}</p>
      ${result.blocks.map(renderBlock).join("")}
    </section>

    <section class="section">
      <div class="section-heading">
        <p class="eyebrow">Диагностика</p>
        <h2>Найденные проблемы</h2>
      </div>
      ${renderProblems(result.problems)}
    </section>

    <section class="section">
      <div class="section-heading">
        <p class="eyebrow">План работ</p>
        <h2>Задачи на улучшение</h2>
      </div>
      ${renderPlan(result.backlog)}
    </section>
  </div>
</body>
</html>`;
}

export function downloadReportHtml(url: string, result: AgentResult, analysisId: string): void {
  const html = buildReportHtml(url, result);
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const host = (() => {
    try {
      return new URL(url).hostname.replaceAll(".", "-");
    } catch {
      return "page";
    }
  })();
  anchor.href = objectUrl;
  anchor.download = `cro-report-${host}-${analysisId.slice(0, 8)}.html`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}
