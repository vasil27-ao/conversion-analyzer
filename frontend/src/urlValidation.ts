/** Базовая клиентская валидация публичного http(s) URL. */

/** Если схемы нет (например stripe.com) — добавляем https://. */
export function normalizeUrlInput(raw: string): string {
  const value = raw.trim();
  if (!value) {
    return value;
  }
  // Уже есть схема (http:, https:, mailto: …) — не трогаем.
  if (/^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(value)) {
    return value;
  }
  return `https://${value}`;
}

export function validateUrl(raw: string): string | null {
  const value = normalizeUrlInput(raw);
  if (!value) {
    return "Введите URL страницы";
  }

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return "Некорректный URL. Пример: https://example.com/page";
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "Укажите адрес сайта в формате https://example.com";
  }

  if (!parsed.hostname) {
    return "Укажите домен страницы";
  }

  return null;
}
