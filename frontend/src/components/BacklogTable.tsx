import type { BacklogItem } from "../types";
import { presentClientText } from "../clientLanguage";

interface BacklogTableProps {
  backlog: BacklogItem[];
}

function priorityRank(priority: BacklogItem["priority"]): number {
  if (priority === "высокий") return 0;
  if (priority === "средний") return 1;
  return 2;
}

export function BacklogTable({ backlog }: BacklogTableProps) {
  const sorted = [...backlog].sort(
    (a, b) => priorityRank(a.priority) - priorityRank(b.priority),
  );

  if (sorted.length === 0) {
    return <p className="empty-note">Задач на улучшение пока нет.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="backlog-table">
        <thead>
          <tr>
            <th scope="col">Задача</th>
            <th scope="col">Зона страницы</th>
            <th scope="col">Приоритет</th>
            <th scope="col">Ожидаемый эффект</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((item, index) => (
            <tr key={`${item.task}-${index}`}>
              <td data-label="Задача">{presentClientText(item.task)}</td>
              <td data-label="Зона страницы">{presentClientText(item.zone)}</td>
              <td data-label="Приоритет">
                <span className={`priority priority--${item.priority}`}>{item.priority}</span>
              </td>
              <td data-label="Ожидаемый эффект">{presentClientText(item.expected_effect)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
