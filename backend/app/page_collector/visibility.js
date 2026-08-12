/**
 * Общая проверка «реально видно пользователю» для layout и visible_text.
 * Учитывает предков, aria/hidden, opacity, collapsed absolute и т.п.
 */
function isEffectivelyVisible(el) {
  if (!(el instanceof Element)) return false;

  if (typeof el.checkVisibility === "function") {
    try {
      if (
        !el.checkVisibility({
          checkOpacity: true,
          checkVisibilityCSS: true,
          contentVisibilityAuto: true,
        })
      ) {
        return false;
      }
    } catch (_err) {
      // старые движки / частичная поддержка — ниже ручные проверки
    }
  }

  let node = el;
  while (node && node.nodeType === 1) {
    if (node.hasAttribute("hidden")) return false;
    if (node.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(node);
    if (style.display === "none") return false;
    if (style.visibility === "hidden" || style.visibility === "collapse") {
      return false;
    }
    if (parseFloat(style.opacity || "1") === 0) return false;
    if (style.contentVisibility === "hidden") return false;
    node = node.parentElement;
  }

  const rects = el.getClientRects();
  if (!rects || rects.length === 0) return false;
  const rect = el.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return false;

  // Absolute/fixed внутри схлопнутого предка (height/width ~ 0): типичный
  // SSR/виджет-placeholder (Allbirds Reviews). Визуально блок не показан.
  const selfStyle = window.getComputedStyle(el);
  if (selfStyle.position === "absolute" || selfStyle.position === "fixed") {
    let parent = el.parentElement;
    while (
      parent &&
      parent !== document.body &&
      parent !== document.documentElement
    ) {
      const parentStyle = window.getComputedStyle(parent);
      if (parentStyle.display === "contents") {
        parent = parent.parentElement;
        continue;
      }
      const parentRect = parent.getBoundingClientRect();
      if (parentRect.height < 1 || parentRect.width < 1) {
        return false;
      }
      parent = parent.parentElement;
    }
  }

  return true;
}

function collectVisibleText(root) {
  const base = root || document.body;
  if (!base) return "";
  const walker = document.createTreeWalker(base, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      const tag = parent.tagName.toLowerCase();
      if (
        tag === "script" ||
        tag === "style" ||
        tag === "noscript" ||
        tag === "template"
      ) {
        return NodeFilter.FILTER_REJECT;
      }
      if (!isEffectivelyVisible(parent)) return NodeFilter.FILTER_REJECT;
      if (!String(node.textContent || "").trim()) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const parts = [];
  let current = walker.nextNode();
  while (current) {
    const piece = String(current.textContent || "")
      .replace(/\s+/g, " ")
      .trim();
    if (piece) parts.push(piece);
    current = walker.nextNode();
  }
  return parts.join("\n");
}

/** Атрибут на корне скрытого поддерева: в сыром HTML остаётся, из LLM-skeleton убирается. */
var COLLECTOR_INVISIBLE_ATTR = "data-collector-invisible";

function markInvisibleSubtreeRoots(root) {
  const marked = [];
  function visit(el) {
    if (!(el instanceof Element)) return;
    if (!isEffectivelyVisible(el)) {
      el.setAttribute(COLLECTOR_INVISIBLE_ATTR, "");
      marked.push(el);
      return;
    }
    const children = el.children;
    for (let i = 0; i < children.length; i += 1) {
      visit(children[i]);
    }
  }
  visit(root);
  return marked;
}

/**
 * HTML-снимок с пометкой невидимых поддеревьев.
 * Сырой источник может их содержать; skeleton для LLM их вырезает.
 */
function collectHtmlWithInvisibleMarks() {
  const marked = markInvisibleSubtreeRoots(document.body);
  const doctype =
    document.doctype != null
      ? "<!DOCTYPE " + document.doctype.name + ">\n"
      : "<!DOCTYPE html>\n";
  const html = doctype + document.documentElement.outerHTML;
  for (let i = 0; i < marked.length; i += 1) {
    marked[i].removeAttribute(COLLECTOR_INVISIBLE_ATTR);
  }
  return html;
}
