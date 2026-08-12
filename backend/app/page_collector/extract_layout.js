() => {
  const TEXT_LIMIT = 300;
  const PREVIEW_LIMIT = 500;
  const MAX_LINKS = 80;
  const MAX_IMAGES = 60;

  const viewport = {
    width: window.innerWidth,
    height: window.innerHeight,
  };

  function clip(text, limit) {
    const value = (text || "").replace(/\s+/g, " ").trim();
    if (value.length <= limit) return value;
    return value.slice(0, limit);
  }

  function isVisible(el) {
    return typeof isEffectivelyVisible === "function"
      ? isEffectivelyVisible(el)
      : false;
  }

  function inViewport(rect) {
    return (
      rect.bottom > 0 &&
      rect.right > 0 &&
      rect.top < viewport.height &&
      rect.left < viewport.width
    );
  }

  function geometry(el, textOverride) {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const visible = isVisible(el);
    return {
      tag: el.tagName.toLowerCase(),
      text: clip(
        textOverride !== undefined ? textOverride : el.innerText || el.value || "",
        TEXT_LIMIT
      ),
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      page_x: Math.round(rect.x + window.scrollX),
      page_y: Math.round(rect.y + window.scrollY),
      visible,
      in_viewport: inViewport(rect),
      display: style.display,
      position: style.position,
      z_index: style.zIndex,
      font_size: style.fontSize,
      font_weight: style.fontWeight,
      color: style.color,
      background_color: style.backgroundColor,
      opacity: style.opacity,
    };
  }

  const NAMED_BLOCK_RULES = [
    { kind: "reviews", patterns: [/отзыв/i, /review/i, /testimonial/i] },
    {
      kind: "works",
      patterns: [/наши работы/i, /наши проекты/i, /\bworks?\b/i],
    },
    {
      kind: "portfolio",
      patterns: [/портфолио/i, /portfolio/i, /галерея работ/i],
    },
    {
      kind: "cases",
      patterns: [/кейс/i, /\bcases?\b/i, /примеры работ/i, /результаты клиентов/i],
    },
    {
      kind: "guarantees",
      patterns: [/гарант/i, /guarantee/i, /warranty/i],
    },
  ];

  function classifyNamedBlock(title) {
    for (const rule of NAMED_BLOCK_RULES) {
      if (rule.patterns.some((re) => re.test(title))) {
        return rule.kind;
      }
    }
    return null;
  }

  function findSectionRoot(heading) {
    let node = heading.parentElement;
    while (node && node !== document.body) {
      const tag = node.tagName.toLowerCase();
      if (
        tag === "section" ||
        tag === "article" ||
        tag === "aside" ||
        (tag === "div" &&
          (node.id ||
            (typeof node.className === "string" && node.className.length > 0)))
      ) {
        return node;
      }
      node = node.parentElement;
    }
    return heading.parentElement || heading;
  }

  function pageY(el) {
    const rect = el.getBoundingClientRect();
    return rect.top + window.scrollY;
  }

  function ownDirectText(el) {
    let text = "";
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        text += node.textContent || "";
      }
    }
    const direct = clip(text, TEXT_LIMIT);
    if (direct) return direct;
    // У листовых span/p/div часто весь текст в одном уровне без отдельных text nodes-соседей.
    if (el.children.length === 0) {
      return clip(el.textContent || "", TEXT_LIMIT);
    }
    return "";
  }

  function looksLikeSoftHeading(el) {
    const tag = el.tagName.toLowerCase();
    if (tag !== "div" && tag !== "span" && tag !== "p") return false;
    if (!isVisible(el)) return false;
    if (el.closest("h1,h2,h3,h4,h5,h6")) return false;
    if (el.querySelector("h1,h2,h3,h4,h5,h6,form,input,textarea,select,button,img")) {
      return false;
    }
    if (el.querySelectorAll("a").length > 1) return false;

    // Берём только короткий собственный текст ярлыка, не innerText всего контейнера.
    let text = ownDirectText(el);
    if (!text && el.children.length === 0) {
      text = clip(el.textContent || "", TEXT_LIMIT);
    }
    if (!text || text.length > 90) return false;

    const kind = classifyNamedBlock(text);
    if (!kind) return false;

    const style = window.getComputedStyle(el);
    const fontSize = parseFloat(style.fontSize) || 0;
    const weightRaw = style.fontWeight;
    const weight =
      weightRaw === "bold" || weightRaw === "bolder"
        ? 700
        : parseInt(weightRaw, 10) || 400;
    const classId = `${el.getAttribute("class") || ""} ${el.id || ""}`.toLowerCase();
    const classHint = /title|heading|caption|subtitle|заголов|section-label/.test(
      classId
    );

    if (text.length <= 40) return true;
    if (fontSize >= 16 || weight >= 600 || classHint || tag === "p" || tag === "span") {
      return true;
    }
    return false;
  }

  function nearestHeadingText(el) {
    let node = el;
    while (node && node !== document.body) {
      const heading = node.querySelector && node.querySelector("h1,h2,h3,h4,h5,h6");
      if (heading && heading !== el) {
        const text = clip(heading.innerText || "", TEXT_LIMIT);
        if (text) return text;
      }
      const prev = node.previousElementSibling;
      if (prev) {
        const tag = prev.tagName.toLowerCase();
        if (/^h[1-6]$/.test(tag)) {
          const text = clip(prev.innerText || "", TEXT_LIMIT);
          if (text) return text;
        }
        const nested = prev.querySelector && prev.querySelector("h1,h2,h3,h4,h5,h6");
        if (nested) {
          const text = clip(nested.innerText || "", TEXT_LIMIT);
          if (text) return text;
        }
      }
      node = node.parentElement;
    }
    return null;
  }

  const headings = Array.from(
    document.querySelectorAll("h1,h2,h3,h4,h5,h6")
  )
    .filter((el) => isVisible(el))
    .map((el) => ({
      ...geometry(el),
      level: Number(el.tagName.substring(1)),
    }));

  const ctaSelector = [
    "button",
    "input[type='submit']",
    "input[type='button']",
    "a[role='button']",
    "[role='button']",
    "a.btn",
    "a.button",
    "a.cta",
    ".btn",
    ".button",
    ".cta",
  ].join(",");

  const ctaNodes = Array.from(document.querySelectorAll(ctaSelector));
  const seenCtas = new Set();
  const ctas = [];
  for (const el of ctaNodes) {
    if (seenCtas.has(el)) continue;
    seenCtas.add(el);
    if (!isVisible(el)) continue;
    const tag = el.tagName.toLowerCase();
    const text =
      tag === "input"
        ? el.value || el.getAttribute("aria-label") || ""
        : el.innerText || el.getAttribute("aria-label") || "";
    ctas.push({
      ...geometry(el, text),
      href: el.href || el.getAttribute("href") || null,
      role: el.getAttribute("role"),
      input_type: tag === "input" ? el.type || null : null,
    });
  }

  const links = Array.from(document.querySelectorAll("a[href]"))
    .filter((el) => isVisible(el))
    .slice(0, MAX_LINKS)
    .map((el) => ({
      ...geometry(el),
      href: el.href || el.getAttribute("href") || "",
    }));

  function fieldLabel(field) {
    if (field.id) {
      const byFor = document.querySelector(`label[for="${CSS.escape(field.id)}"]`);
      if (byFor) return clip(byFor.innerText || "", TEXT_LIMIT);
    }
    const parentLabel = field.closest("label");
    if (parentLabel) return clip(parentLabel.innerText || "", TEXT_LIMIT);
    return (
      field.getAttribute("aria-label") ||
      field.getAttribute("placeholder") ||
      null
    );
  }

  const forms = Array.from(document.querySelectorAll("form"))
    .filter((form) => isVisible(form))
    .map((form) => {
    const fields = Array.from(
      form.querySelectorAll("input, textarea, select, button")
    )
      .filter((field) => {
        const type = (field.getAttribute("type") || "").toLowerCase();
        if (type === "hidden") return false;
        return isVisible(field);
      })
      .map((field) => ({
        ...geometry(field, field.value || field.innerText || ""),
        name: field.getAttribute("name"),
        input_type:
          field.tagName.toLowerCase() === "input"
            ? field.getAttribute("type") || "text"
            : field.tagName.toLowerCase(),
        label: fieldLabel(field),
        placeholder: field.getAttribute("placeholder"),
        required: !!field.required,
      }));

    return {
      ...geometry(form),
      action: form.getAttribute("action"),
      method: (form.getAttribute("method") || "get").toLowerCase(),
      fields,
    };
  });

  const sectionByHeading = [];
  const seenTitleEls = new Set();

  function addNamedSection(titleEl, name, kind) {
    if (seenTitleEls.has(titleEl)) return;
    for (let i = sectionByHeading.length - 1; i >= 0; i--) {
      const existing = sectionByHeading[i];
      if (existing.kind !== kind) continue;
      if (existing.heading.contains(titleEl)) {
        // Более специфичный потомок вместо широкого контейнера.
        sectionByHeading.splice(i, 1);
        seenTitleEls.delete(existing.heading);
        continue;
      }
      if (titleEl.contains(existing.heading)) {
        return;
      }
      if (existing.name === name) return;
    }
    seenTitleEls.add(titleEl);
    sectionByHeading.push({
      name,
      kind,
      root: findSectionRoot(titleEl),
      heading: titleEl,
      y: pageY(titleEl),
    });
  }

  for (const heading of document.querySelectorAll("h1,h2,h3,h4,h5,h6")) {
    if (!isVisible(heading)) continue;
    const name = clip(heading.innerText || "", TEXT_LIMIT);
    if (!name) continue;
    const kind = classifyNamedBlock(name);
    if (!kind) continue;
    const root = findSectionRoot(heading);
    // Секция-оболочка нулевой высоты (виджет не раскрыт) — не считаем блоком.
    if (root instanceof Element) {
      const rootRect = root.getBoundingClientRect();
      if (rootRect.height < 1) continue;
    }
    addNamedSection(heading, name, kind);
  }

  for (const el of document.querySelectorAll("div, span, p")) {
    if (!looksLikeSoftHeading(el)) continue;
    const name =
      ownDirectText(el) || clip(el.innerText || "", TEXT_LIMIT);
    const kind = classifyNamedBlock(name);
    if (!name || !kind) continue;
    addNamedSection(el, name, kind);
  }

  sectionByHeading.sort((a, b) => a.y - b.y);

  function namedBlockFor(el) {
    if (!(el instanceof Element)) return null;
    for (const block of sectionByHeading) {
      if (block.root.contains(el) && el !== block.heading) {
        return block.name;
      }
    }

    // Рядом: изображение между этим заголовком секции и следующим по вертикали.
    const elY = pageY(el);
    for (let i = 0; i < sectionByHeading.length; i++) {
      const block = sectionByHeading[i];
      const next = sectionByHeading[i + 1];
      const start = block.y - 10;
      const end = next ? next.y : block.y + 2500;
      if (elY >= start && elY < end) {
        return block.name;
      }
    }
    return null;
  }

  function imagesForBlock(block, index) {
    const result = new Set();
    for (const img of block.root.querySelectorAll("img, [role='img']")) {
      result.add(img);
    }

    let sibling = block.heading.nextElementSibling;
    let steps = 0;
    while (sibling && steps < 10) {
      if (sibling.matches && sibling.matches("img, [role='img']")) {
        result.add(sibling);
      }
      if (sibling.querySelectorAll) {
        for (const img of sibling.querySelectorAll("img, [role='img']")) {
          result.add(img);
        }
      }
      sibling = sibling.nextElementSibling;
      steps += 1;
    }

    const next = sectionByHeading[index + 1];
    const start = block.y - 10;
    const end = next ? next.y : block.y + 2500;
    for (const img of document.querySelectorAll("img, [role='img']")) {
      const y = pageY(img);
      if (y >= start && y < end) result.add(img);
    }
    return Array.from(result);
  }

  const images = Array.from(document.querySelectorAll("img, [role='img']"))
    .filter((el) => isVisible(el))
    .slice(0, MAX_IMAGES)
    .map((el) => {
      const named = namedBlockFor(el);
      return {
        ...geometry(el, el.getAttribute("alt") || ""),
        src: el.currentSrc || el.src || el.getAttribute("src") || null,
        alt: el.getAttribute("alt") || "",
        block_context: nearestHeadingText(el),
        named_block: named,
      };
    });

  const named_blocks = sectionByHeading
    .filter((block) => {
      const target = block.root || block.heading;
      if (!(target instanceof Element)) return false;
      if (!isVisible(block.heading)) return false;
      const rootRect = (block.root || block.heading).getBoundingClientRect();
      return rootRect.height >= 1 && rootRect.width >= 1;
    })
    .map((block, index) => {
      const imgs = imagesForBlock(block, index).filter((img) => isVisible(img));
      return {
        ...geometry(block.root || block.heading),
        name: block.name,
        kind: block.kind,
        has_images: imgs.length > 0,
        image_count: imgs.length,
        text_preview: clip(
          (block.root || block.heading).innerText || "",
          PREVIEW_LIMIT
        ),
      };
    });

  return {
    viewport,
    headings,
    ctas,
    links,
    forms,
    images,
    named_blocks,
  };
}
