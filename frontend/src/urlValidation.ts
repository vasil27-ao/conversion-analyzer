/** Базовая клиентская валидация публичного http(s) URL. */

export function normalizeUrlInput(raw: string): string {
  return raw.trim();
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
    return "URL должен начинаться с http:// или https://";
  }

  if (!parsed.hostname) {
    return "Укажите домен страницы";
  }

  return null;
}
