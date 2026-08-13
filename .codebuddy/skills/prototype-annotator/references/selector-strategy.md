# Selector Strategy

Stable selectors are the difference between useful annotations and fragile decoration.

## Selector Priority

Use the first available stable selector:

1. `#id`
2. `[data-ann="..."]`
3. `[data-testid="..."]`
4. `[aria-label="..."]`
5. Element role plus label, such as `button[aria-label="保存"]`
6. Short structural selector with text fallback

Avoid selectors that depend on generated class names, deep utility-class chains, or purely visual wrappers.

## Recommended Prototype Attributes

When creating or modifying prototypes, add stable attributes to important elements:

```html
<button id="btn-submit-application" data-ann="submit-application">提交申请</button>
<section id="application-summary" data-ann="application-summary">...</section>
```

When selectors are already fragile, generate a reviewable anchor plan first:

```bash
python3 scripts/suggest_data_ann_anchors.py <prototype_path>
```

The script writes `prototype-annotator/data-ann-plan.json`. Treat this file
as a source-edit checklist: it recommends stable `data-ann` values for selected
annotations and fragile candidates, but it does not silently mutate application
source code.

## Fallback Text

Always store `fallbackText` for manually selected elements when visible text exists:

```json
{
  "selector": "main > section:nth-of-type(2) button",
  "fallbackText": "提交申请",
  "strategy": "path"
}
```

Runtime lookup:

1. Try `selector`.
2. If not found, search visible elements containing `fallbackText`.
3. If multiple match, prefer the same tag from `boundsHint.tag`.

## Repairing Broken Selectors

When `validate_annotations.py` reports a miss:

1. Open `prototype-annotator/page-map.json`.
2. Find a matching element by text or role.
3. Update `target.selector`.
4. Set `target.strategy` to `manual`.
5. Re-run validation.
