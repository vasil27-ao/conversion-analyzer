import type { ProblemItem } from "../types";
import { presentClientText } from "../clientLanguage";

interface ProblemsListProps {
  problems: ProblemItem[];
}

export function ProblemsList({ problems }: ProblemsListProps) {
  if (problems.length === 0) {
    return <p className="empty-note">Существенных проблем не найдено.</p>;
  }

  return (
    <ol className="problems-list">
      {problems.map((problem, index) => (
        <li key={`${problem.location}-${index}`}>
          <p className="problem-description">{presentClientText(problem.description)}</p>
          <p className="problem-location">{presentClientText(problem.location)}</p>
        </li>
      ))}
    </ol>
  );
}
