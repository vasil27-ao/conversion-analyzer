import type { BlockResult } from "../types";
import { presentClientText } from "../clientLanguage";
import { ScoreBadge } from "./ScoreBadge";

interface BlockSectionProps {
  block: BlockResult;
  index: number;
}

export function BlockSection({ block, index }: BlockSectionProps) {
  const number = String(index + 1).padStart(2, "0");

  return (
    <article className="block">
      <header className="block-header">
        <div className="block-title">
          <p className="block-index">{number}</p>
          <h3>{block.block_name}</h3>
        </div>
        <div className="block-score">
          <span className="micro-label">Оценка блока</span>
          <ScoreBadge score={block.score} kind="block" />
        </div>
      </header>

      <div className="block-analytics">
        <div className="analytics-col">
          <span className="micro-label">Что не так</span>
          <p>{presentClientText(block.what_is_wrong)}</p>
        </div>
        <div className="analytics-col">
          <span className="micro-label">Почему важно</span>
          <p>{presentClientText(block.why_it_matters)}</p>
        </div>
      </div>

      <div className="criteria-list">
        {block.criteria.map((criterion) => (
          <div key={criterion.id} className="criterion-row">
            <div className="criterion-top">
              <span className="criterion-id">{criterion.id}</span>
              <ScoreBadge score={criterion.score} />
            </div>
            <p className="criterion-justification">
              {presentClientText(criterion.justification)}
            </p>
            {criterion.recommendation ? (
              <p className="criterion-recommendation">
                <span className="micro-label">Рекомендация</span>
                {presentClientText(criterion.recommendation)}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </article>
  );
}
