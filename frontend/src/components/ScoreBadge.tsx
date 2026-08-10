import type { CriterionScore } from "../types";
import { criterionScoreMeaning, formatCriterionScoreLabel } from "../clientLanguage";

interface ScoreBadgeProps {
  score: CriterionScore | number | null;
  kind?: "criterion" | "block" | "overall";
}

function toneFor(score: CriterionScore | number | null): string {
  if (score === null || score === "N/A") return "na";
  if (typeof score === "number") {
    if (score >= 75) return "high";
    if (score >= 50) return "mid";
    return "low";
  }
  if (score === 2) return "high";
  if (score === 1) return "mid";
  return "low";
}

export function ScoreBadge({ score, kind = "criterion" }: ScoreBadgeProps) {
  const tone = toneFor(score);

  if (kind === "overall" && typeof score === "number") {
    return (
      <div className={`overall-metric score-tone--${tone}`}>
        <span className="overall-metric-value">{score}</span>
        <span className="overall-metric-scale">/ 100</span>
      </div>
    );
  }

  if (kind === "block") {
    const label = score === null || score === "N/A" ? "N/A" : String(score);
    const meaning =
      score === null || score === "N/A" ? "не применимо" : undefined;
    return (
      <span
        className={`score-badge score-badge--block score-badge--${tone}`}
        title={meaning}
      >
        {label}
      </span>
    );
  }

  // Criterion scores: number + meaning for the client.
  const criterionScore = score as CriterionScore;
  const value = formatCriterionScoreLabel(criterionScore);
  const meaning = criterionScoreMeaning(criterionScore);

  return (
    <span
      className={`score-with-meaning score-badge--${tone}`}
      title={`${value} — ${meaning}`}
    >
      <span className={`score-badge score-badge--criterion score-badge--${tone}`}>
        {value}
      </span>
      <span className="score-meaning">{meaning}</span>
    </span>
  );
}
