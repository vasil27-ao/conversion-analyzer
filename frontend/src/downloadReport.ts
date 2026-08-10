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
  if (score === null || score === undefined) return "N/A — не применимо";
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
    ? `<p><strong>Рекомендация:</strong> ${escapeHtml(presentClientText(criterion.recommendation))}</p>`
    : "";
  return `
    <tr>
      <td>${escapeHtml(criterion.id)}</td>
      <td class="score">${escapeHtml(formatCriterionScore(criterion.score))}</td>
      <td>
        <p>${escapeHtml(presentClientText(criterion.justification))}</p>
        ${recommendation}
      </td>
    </tr>`;
}

function renderBlock(block: BlockResult): string {
  const criteria = block.criteria.map(renderCriterion).join("");
  return `
    <section class="block">
      <h3>${escapeHtml(block.block_name)}
        <span class="muted">· оценка блока: ${escapeHtml(formatBlockScore(block.score))}</span>
      </h3>
      <p><strong>Что не так:</strong> ${escapeHtml(presentClientText(block.what_is_wrong))}</p>
      <p><strong>Почему важно:</strong> ${escapeHtml(presentClientText(block.why_it_matters))}</p>
      <table>
        <thead>
          <tr>
            <th>Критерий</th>
            <th>Оценка</th>
            <th>Обоснование / рекомендация</th>
          </tr>
        </thead>
        <tbody>${criteria}</tbody>
      </table>
    </section>`;
}

function renderProblems(problems: ProblemItem[]): string {
  if (problems.length === 0) {
    return "<p>Существенных проблем не найдено.</p>";
  }
  const items = problems
    .map(
      (item) => `
      <li>
        <strong>${escapeHtml(presentClientText(item.description))}</strong>
        <div class="muted">Где: ${escapeHtml(presentClientText(item.location))}</div>
      </li>`,
    )
    .join("");
  return `<ul>${items}</ul>`;
}

function renderBacklog(backlog: BacklogItem[]): string {
  const sorted = [...backlog].sort(
    (a, b) => priorityOrder(a.priority) - priorityOrder(b.priority),
  );
  if (sorted.length === 0) {
    return "<p>Задач на улучшение пока нет.</p>";
  }
  const rows = sorted
    .map(
      (item) => `
      <tr>
        <td>${escapeHtml(presentClientText(item.task))}</td>
        <td>${escapeHtml(presentClientText(item.zone))}</td>
        <td>${escapeHtml(item.priority)}</td>
        <td>${escapeHtml(presentClientText(item.expected_effect))}</td>
      </tr>`,
    )
    .join("");
  return `
    <table>
      <thead>
        <tr>
          <th>Задача</th>
          <th>Зона страницы</th>
          <th>Приоритет</th>
          <th>Ожидаемый эффект</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

export function buildReportHtml(url: string, result: AgentResult): string {
  const { overall } = result;
  const generatedAt = new Date().toLocaleString("ru-RU");
  return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Отчёт по конверсионности</title>
  <style>
    body { font-family: Georgia, "Times New Roman", serif; color: #1c1c1c; max-width: 920px; margin: 0 auto; padding: 24px; line-height: 1.45; }
    h1, h2, h3 { font-family: system-ui, sans-serif; }
    h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
    .meta { color: #555; margin-bottom: 1.5rem; }
    .muted { color: #666; font-weight: 400; }
    .score { font-weight: 700; white-space: nowrap; }
    .scale { margin: 0.75rem 0 1.25rem; padding: 0.75rem 0.9rem; background: #f5f5f5; }
    table { width: 100%; border-collapse: collapse; margin: 0.75rem 0 1.5rem; font-size: 0.95rem; }
    th, td { border: 1px solid #ccc; padding: 8px 10px; text-align: left; vertical-align: top; }
    th { background: #f3f3f3; }
    section { margin-bottom: 1.75rem; }
    ul { padding-left: 1.2rem; }
    li { margin-bottom: 0.6rem; }
    @media (max-width: 640px) {
      body { padding: 16px; }
      table, thead, tbody, th, td, tr { display: block; }
      thead { display: none; }
      tr { border: 1px solid #ccc; margin-bottom: 0.75rem; padding: 0.5rem; }
      td { border: none; padding: 0.25rem 0; }
      td::before { content: attr(data-label); font-weight: 600; display: block; color: #555; }
    }
  </style>
</head>
<body>
  <h1>Отчёт по конверсионности страницы</h1>
  <div class="meta">
    <div>URL: ${escapeHtml(url)}</div>
    <div>Сформирован: ${escapeHtml(generatedAt)}</div>
  </div>

  <section>
    <h2>Общая оценка</h2>
    <p class="score">${escapeHtml(String(overall.score))} / 100 · уровень: ${escapeHtml(overall.level)}</p>
    <p>${escapeHtml(presentClientText(overall.summary))}</p>
    <p class="muted">Оценено критериев: ${overall.applicable_count}, не применимо (N/A): ${overall.na_count}</p>
  </section>

  <section>
    <h2>Оценка по блокам методики</h2>
    <p class="scale">${escapeHtml(SCORE_SCALE_EXPLANATION)}</p>
    ${result.blocks.map(renderBlock).join("")}
  </section>

  <section>
    <h2>Найденные проблемы</h2>
    ${renderProblems(result.problems)}
  </section>

  <section>
    <h2>Задачи на улучшение</h2>
    ${renderBacklog(result.backlog)}
  </section>
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
