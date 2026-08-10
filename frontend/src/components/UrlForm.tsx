interface UrlFormProps {
  value: string;
  error: string | null;
  submitting: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function UrlForm({ value, error, submitting, onChange, onSubmit }: UrlFormProps) {
  return (
    <form
      className="url-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="url-form-head">
        <p className="eyebrow">
          <span className="eyebrow-index">02</span>
          Запуск анализа
        </p>
        <h2>Вставьте URL страницы</h2>
        <p className="hint url-form-lead">
          Публичная страница по http(s). Анализ обычно занимает от нескольких секунд до пары минут.
        </p>
        <p className="hint url-form-scope">
          Первая версия предназначена для анализа лендингов.
        </p>
      </div>
      <label className="field-label" htmlFor="page-url">
        Адрес страницы
      </label>
      <div className="form-row form-row--split">
        <input
          id="page-url"
          className="url-input"
          type="url"
          name="url"
          inputMode="url"
          autoComplete="url"
          placeholder="https://example.com/landing"
          value={value}
          disabled={submitting}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? "url-error" : "url-hint"}
        />
        <button className="btn btn-primary" type="submit" disabled={submitting}>
          {submitting ? "Запуск…" : "Анализировать"}
        </button>
      </div>
      <p id="url-hint" className="sr-only">
        Публичная страница по http(s).
      </p>
      {error ? (
        <p id="url-error" className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
