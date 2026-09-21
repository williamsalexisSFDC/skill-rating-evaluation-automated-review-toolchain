"""
Shared Bryntum grid utilities for org62 Playwright scripts.

The Mass Approve page renders its grid inside a Web Component with Shadow DOM
(c-bryntum-widget-host). All grid interaction requires shadow-DOM-aware JS.
"""

from playwright.sync_api import Page

# ---------------------------------------------------------------------------
# JS helpers (shadow-DOM aware)
# ---------------------------------------------------------------------------

# Traverses shadow roots to locate an element matching `sel`.
_FIND_EL_FN = """
function findEl(root, sel) {
    const found = root.querySelector(sel);
    if (found) return found;
    for (const el of root.querySelectorAll('*')) {
        if (el.shadowRoot) {
            const r = findEl(el.shadowRoot, sel);
            if (r) return r;
        }
    }
    return null;
}
"""

# Waits for the Bryntum host to appear anywhere in the shadow tree.
WAIT_FOR_GRID_JS = (
    "() => { "
    + _FIND_EL_FN
    + " return !!findEl(document, 'c-bryntum-widget-host'); }"
)

# Collects all visible rows and their cell data from the grid, scrolling to get
# virtual rows.  Returns [{id, col-pse__resource__r_name, col-pse__skill_certification__r_name, ...}].
GET_ALL_ROWS_JS = (
    "async () => { "
    + _FIND_EL_FN
    + """
    const host = findEl(document, 'c-bryntum-widget-host');
    if (!host) return { error: 'no-host' };
    const sr = host.shadowRoot;
    const scroller = sr.querySelector('.b-grid-body-container');
    if (!scroller) return { error: 'no-scroller' };

    function collectRows() {
        return [...sr.querySelectorAll('.b-grid-row')].map(row => {
            const record = { id: row.dataset.id };
            for (const cell of row.querySelectorAll('.b-grid-cell')) {
                const col = cell.dataset.columnId;
                if (col) record[col] = cell.textContent?.trim() ?? '';
            }
            return record;
        });
    }

    const seen = new Map();
    collectRows().forEach(r => { if (r.id) seen.set(r.id, r); });

    const totalHeight = scroller.scrollHeight;
    const step = Math.max(scroller.clientHeight, 100);
    let pos = step;
    while (pos <= totalHeight + step) {
        scroller.scrollTop = pos;
        await new Promise(res => setTimeout(res, 400));
        collectRows().forEach(r => { if (r.id) seen.set(r.id, r); });
        pos += step;
    }
    scroller.scrollTop = 0;
    return { rows: [...seen.values()] };
}"""
)

# Selects every row whose data-id is in the provided array.
# Strategy A: Bryntum widget programmatic API (grid._instance.selectRecords).
# Strategy B (fallback): click .b-check-cell — Bryntum's CSS class for the
# selection-column cell.  querySelector returns the FIRST .b-check-cell in the
# row, which is the row-selection column; the Aspiration column also renders as
# .b-check-cell but appears later in the DOM so it is never matched first.
# Returns { selected: N, missing: [id, ...] }.
SELECT_BY_IDS_JS = (
    "async (recordIds) => { "
    + _FIND_EL_FN
    + """
    const host = findEl(document, 'c-bryntum-widget-host');
    if (!host) return { error: 'no-host' };
    const sr = host.shadowRoot;
    const scroller = sr.querySelector('.b-grid-body-container');
    if (!scroller) return { error: 'no-scroller' };

    const toSelect = new Set(recordIds);

    // --- Strategy A: Bryntum widget programmatic API ---
    const gridEl = sr.querySelector('.b-gridbase');
    const grid = gridEl && (gridEl._instance || gridEl._widget || gridEl.widget);
    if (grid && grid.store && typeof grid.selectRecords === 'function') {
        const records = (grid.store.records || []).filter(r => toSelect.has(String(r.id)));
        grid.selectRecords(records);
        await new Promise(r => setTimeout(r, 300));
        const selectedIds = new Set((grid.selectedRecords || []).map(r => String(r.id)));
        return {
            selected: selectedIds.size,
            missing: recordIds.filter(id => !selectedIds.has(id))
        };
    }

    // --- Strategy B: DOM click on .b-check-cell (row-selection column) ---
    const selected = new Set();

    function clickVisible() {
        for (const row of sr.querySelectorAll('.b-grid-row[data-id]')) {
            const id = row.dataset.id;
            if (!toSelect.has(id) || selected.has(id)) continue;
            // First .b-check-cell in the row is always the selection column
            const cell = row.querySelector('.b-check-cell') ||
                         row.querySelectorAll('.b-grid-cell')[0];
            if (cell) {
                const inner = cell.querySelector('input[type=checkbox]') ||
                              cell.querySelector('.b-checkbox');
                (inner || cell).click();
                selected.add(id);
            }
        }
    }

    clickVisible();
    const step = Math.max(scroller.clientHeight, 100);
    let pos = step;
    while (pos <= scroller.scrollHeight + step && selected.size < toSelect.size) {
        scroller.scrollTop = pos;
        await new Promise(res => setTimeout(res, 300));
        clickVisible();
        pos += step;
    }
    scroller.scrollTop = 0;
    return {
        selected: selected.size,
        missing: recordIds.filter(id => !selected.has(id))
    };
}"""
)

# Clears the current selection.  Same two-strategy pattern as SELECT_BY_IDS_JS.
CLEAR_SELECTION_JS = (
    "() => { "
    + _FIND_EL_FN
    + """
    const host = findEl(document, 'c-bryntum-widget-host');
    if (!host) return;
    const sr = host.shadowRoot;

    // Strategy A: Bryntum widget API
    const gridEl = sr.querySelector('.b-gridbase');
    const grid = gridEl && (gridEl._instance || gridEl._widget || gridEl.widget);
    if (grid && typeof grid.deselectAll === 'function') {
        grid.deselectAll();
        return;
    }

    // Strategy B: click .b-check-cell on each selected row to deselect
    for (const row of sr.querySelectorAll('.b-grid-row.b-selected, .b-grid-row[aria-selected="true"]')) {
        const cell = row.querySelector('.b-check-cell') ||
                     row.querySelectorAll('.b-grid-cell')[0];
        if (cell) {
            const inner = cell.querySelector('input[type=checkbox]') ||
                          cell.querySelector('.b-checkbox');
            (inner || cell).click();
        }
    }
}"""
)


# ---------------------------------------------------------------------------
# Python wrappers
# ---------------------------------------------------------------------------

def wait_for_grid(page: Page) -> None:
    """Wait until the Bryntum grid host appears anywhere in the shadow tree."""
    page.wait_for_function(WAIT_FOR_GRID_JS, timeout=60_000)
    page.wait_for_timeout(2_000)


def get_all_rows(page: Page) -> list[dict]:
    """
    Return all grid rows as a list of dicts keyed by column ID.
    Scrolls through virtual rows to collect all records.
    """
    result = page.evaluate(GET_ALL_ROWS_JS)
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"get_all_rows failed: {result['error']}")
    return result.get("rows", [])


def select_rows_by_ids(page: Page, record_ids: list[str]) -> dict:
    """
    Select grid rows matching the given record IDs.
    Returns dict: {selected: int, missing: list[str]}.
    """
    result = page.evaluate(SELECT_BY_IDS_JS, list(record_ids))
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"select_rows_by_ids failed: {result['error']}")
    return result


def clear_selection(page: Page) -> None:
    """Deselect all currently selected rows."""
    page.evaluate(CLEAR_SELECTION_JS)
