import type { CriterionScore } from "./types";

/** Смысл оценки критерия для клиента. */
export function criterionScoreMeaning(score: CriterionScore | null): string {
  if (score === null || score === "N/A") return "не применимо";
  if (score === 2) return "выполнено хорошо";
  if (score === 1) return "выполнено частично";
  return "не выполнено";
}

export function formatCriterionScoreLabel(score: CriterionScore): string {
  if (score === "N/A") return "N/A";
  return String(score);
}

/**
 * Убирает технические формулировки из текстов отчёта для клиентского UI.
 * Не меняет смысл, только представление.
 */
export function presentClientText(text: string): string {
  let value = text;

  const replacements: Array<[RegExp, string]> = [
    [/\bпо mock[- ]?данным\b/gi, "по данным проверки"],
    [/\bmock[- ]?данны(?:ми|х|е|м)?\b/gi, "данными проверки"],
    [/\blayout_desktop\b/gi, "отображение на компьютере"],
    [/\blayout_mobile\b/gi, "отображение на мобильной версии"],
    [/\bпо layout[- ]?данным\b/gi, "по данным отображения страницы"],
    [/\blayout[- ]?данны(?:ми|х|е|м)?\b/gi, "данным отображения страницы"],
    [/\(\s*layout[- ]?данны(?:ми|х|е|м)?\s*\)/gi, "(по отображению страницы)"],
    [/\bHTML-элемент(?:а|у|ом|е|ы|ов)?\b/gi, "элемент"],
    [/\bHTML\b/g, "код страницы"],
    [/\blayout\b/gi, "отображение страницы"],
    [/\bvisible_text\b/gi, "видимый текст"],
    [/\bDOM\b/g, "структура страницы"],
    [/\bмассив ctas\b/gi, "список кнопок действий"],
    [/\bctas\b/gi, "кнопки действий"],
    [/\bviewport\b/gi, "область экрана"],
    [/\bбеклог(?:а|у|ом|е)?\b/gi, "план работ"],
    [/\bbacklog\b/gi, "план работ"],
    [/\bна mobile\b/gi, "на мобильной версии"],
    [/\bmobile\b/gi, "мобильная версия"],
  ];

  for (const [pattern, replacement] of replacements) {
    value = value.replace(pattern, replacement);
  }

  return value
    .replaceAll("по данными проверки", "по данным проверки")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+,/g, ",")
    .trim();
}

/** Короткое пояснение шкалы и итоговой 100-балльной оценки (как считает backend). */
export const SCORE_SCALE_EXPLANATION =
  "Каждый критерий оценивается так: 2 — выполнено хорошо, 1 — выполнено частично, 0 — не выполнено, N/A — не применимо. " +
  "Итоговая оценка из 100 — это доля набранных баллов от максимума: суммируем оценки применимых критериев, делим на удвоенное их количество и переводим в проценты. " +
  "Критерии «не применимо» в расчёт не входят. Уровень: ниже 50 — низкий, от 50 до 75 — средний, от 75 — высокий.";
