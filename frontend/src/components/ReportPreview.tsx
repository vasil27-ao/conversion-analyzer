/** Статичный product-preview структуры отчёта на стартовом экране. */

const PREVIEW_BLOCKS = [
  { name: "Первый экран и оффер", score: "72" },
  { name: "Понятность ценности", score: "88" },
  { name: "Доверие", score: "55" },
  { name: "Форма / CTA", score: "61" },
  { name: "Мобильная версия", score: "48" },
  { name: "Отвлекающие элементы", score: "N/A" },
];

const PREVIEW_BACKLOG = [
  { task: "Поднять CTA в первый экран на mobile", priority: "высокий" },
  { task: "Сократить поля формы и пояснить назначение", priority: "высокий" },
  { task: "Усилить контакты в футере", priority: "средний" },
];

export function ReportPreview() {
  return (
    <aside className="report-preview" aria-label="Пример структуры отчёта">
      <div className="report-preview-head">
        <p className="eyebrow">
          <span className="eyebrow-index">03</span>
          Пример отчёта
        </p>
        <div className="preview-score-row">
          <div>
            <p className="micro-label">Общая оценка</p>
            <p className="preview-score">
              64.5 <span>/ 100</span>
            </p>
          </div>
          <div className="preview-level">
            <p className="micro-label">Уровень</p>
            <p>
              <em>средний</em>
            </p>
          </div>
        </div>
        <dl className="preview-stats">
          <div>
            <dt>Критериев</dt>
            <dd>19</dd>
          </div>
          <div>
            <dt>Не применимо</dt>
            <dd>1</dd>
          </div>
          <div>
            <dt>Проблем</dt>
            <dd>3</dd>
          </div>
          <div>
            <dt>Задач</dt>
            <dd>3</dd>
          </div>
        </dl>
      </div>

      <div className="preview-blocks">
        <p className="micro-label">6 блоков методики</p>
        <ul>
          {PREVIEW_BLOCKS.map((block) => (
            <li key={block.name}>
              <span>{block.name}</span>
              <strong className={block.score === "N/A" ? "is-na" : undefined}>{block.score}</strong>
            </li>
          ))}
        </ul>
      </div>

      <div className="preview-backlog">
        <p className="micro-label">План работ</p>
        <ul>
          {PREVIEW_BACKLOG.map((item) => (
            <li key={item.task}>
              <span className={`priority priority--${item.priority}`}>{item.priority}</span>
              <span>{item.task}</span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
