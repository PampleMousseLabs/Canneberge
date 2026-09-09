# Open Issues Audit: PampleMousseLabs/ProjectCanneberge

## #33: y finance / Stock analysis/marketscreener
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/33

### Description
can any of these handle non-us lookups?

EuronextParis: MC
KRX: 005930


---

## #32: desktop -> web -> desktop
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/32

### Description
Need to update the desktop -> web -> desktop capabilities so saving inputs and save states are transferrable between web and desktop versions. 

Additionally, we extracted some math from some pages into Canneberge/Calculations so we could run the math there instead of in web pages (DCF, GT NWC, debt_schedule). 

We need to update those pages /Ui pages to point to /Calculations for their math too so consistency can be made for save states and for everything else consistency wise. 

Right now, desktop app's pages that can run math inside of them do, they aren't pointed to /Calculations like web app's are. 

---

## #31: Input field focus/lag/cursor returns home
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/31

### Description
Delete `focus_keeper.js`. It cannot reliably solve this because it reacts **after** Dash has already destroyed the focused input. The VS Code terminal crash was probably unrelated—the script runs in the browser—but there is no reason to keep it.

You’re also right that converting everything to `DataTable` is not an appropriate blanket solution. These pages contain mixed controls, dynamic rows, section headers, calculated cells, and special formatting. It would be another large rewrite without addressing the actual architectural mistake.

## The actual problem

Several callbacks return a newly constructed table containing the inputs themselves.

For example, Projection Module does this on every blur:

```python
Output("proj-modal-grid-container", "children", allow_duplicate=True)
```

Then:

```python
table, status, ... = build_table(...)
return table, ...
```

So pressing Tab does this:

1. Browser moves focus into the next input.
2. Previous input fires its debounced callback.
3. Python recalculates.
4. Callback replaces the **entire table**.
5. React destroys the next input you just focused.
6. Browser focus falls back to the page.
7. Queued callbacks make this appear delayed or inconsistent.

`debounce=True` is not intentionally postponing the calculation until you type again. You are seeing server callback lag, queued changes, and repeated table remounts.

## The correct fix

We need to stop remounting input-bearing containers during ordinary calculation updates.

The architecture should be:

### Structural render

Build or replace the table only when its structure changes:

- modal opens;
- number of years changes;
- row count changes;
- basis changes where different controls are genuinely required.

### Calculation update

When an ordinary cell is committed with Tab/Enter:

- preserve the existing table;
- recalculate through the shared Python engine;
- update only calculated text/component properties;
- update only the derived counterpart input when required;
- never return a new table.

Dynamic cells do **not** need hundreds of individually written callbacks. They can retain pattern IDs:

```python
{
    "type": "proj-calc",
    "field": "ebitda",
    "period": "NFY+3",
}
```

The server can loop over fields and periods and update those properties with Dash’s `set_props`. That preserves your string-based row dynamics and does not remount the input DOM.

For Revenue/Growth two-way binding:

- editing Revenue updates the Growth input’s `value`;
- editing Growth updates Revenue’s `value`;
- the active input itself is not rewritten;
- neither input is destroyed.

## Pages currently affected

### Projection Module — worst offender

`live_recalc()` rebuilds the entire grid after every input blur. This should be fixed first.

### GPC

Typing selected multiples writes `session-store`; callbacks listening to the entire store may then rebuild Selected Multiples or Weighting. Those input-bearing sections need to stop using broad `session-store` updates as a self-render trigger.

### NWC

Changing a selector/percentage persists to `session-store`, which causes the full input table to render again.

### DCF

The table, TV panel, and sensitivity grid contain inputs but are returned from calculation callbacks. This is why sensitivity fields are particularly vulnerable to cursor loss and stale-looking updates.

### WACC

Its primary user inputs are mostly in the static layout, so it is structurally closer to correct. It may still recompute more often than necessary, but it should require less work.

### Home

Most inputs are static and should not remount during autosync. It may have isolated issues, but it is not built around the same full-table replacement mistake.

## Performance problem

The broad `session-store` dependency also causes duplicate work:

```text
input blur
→ persistence callback recalculates
→ writes session-store
→ render callback sees session-store
→ recalculates again
→ replaces the table
```

On DCF, that can include:

- WACC recomputation;
- NWC recomputation;
- subject financial resolution;
- DCF waterfall;
- 25-cell sensitivity evaluation;
- multiple full HTML table constructions.

We should change current-page render callbacks so that `session-store` is used as:

- a `State` during normal edits;
- an `Input` only through a dedicated hydration signal such as `session-load-timestamp`, navigation, or a local calculation store.

That removes the duplicate render/recompute cycle while preserving Save Session behavior.

## Recommended next action

Pause further feature work and fix **Projection Module first** as the proof case. It is the clearest reproduction and the most important rapid-entry surface.

Please send the **current post-edit**:

```text
web/components/projection_modal.py
```

I will make a precise conversion with these constraints:

1. Grid builds only on open/year-count changes.
2. `live_recalc` no longer outputs `proj-modal-grid-container.children`.
3. Calculated cells receive pattern IDs.
4. Results update in place through component properties.
5. Revenue/Growth counterparts update without replacing either input.
6. Save commits the current draft without rebuilding the grid.
7. Tab performs one blur recalculation while focus remains in the next field.

Once that behavior is verified in the browser, we can apply the same pattern to GPC, NWC, and DCF instead of gambling on a global JavaScript patch or an unsuitable DataTable conversion.

---

## #30: web app DCF page
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/30

### Description
sensitivity table doesnt update based on projection toggles and +/- don't change when toggled to other basis of value. 

APP WIDE - Generally speaking, things aren't auto calculating 1. fast, or 2. at all 

---

## #29: web app reverse DCF
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/29

### Description
need reverse dcf

---

## #28: GPC page
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/28

### Description
need multiples candlestick chart

---

## #27: GPC page
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/27

### Description
need bridge labels updating for BEV or Equity conclusion

---

## #26: web WACC page
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/26

### Description
two input boxes not right aligned in their column

---

## #25: Update live marks refresh
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/25

### Description
check on the market cap calculation, large differences between SA pull (~5%)

Does Y finance print market cap? Or do we multiply price *shares, or vice versa. 

What should we do for the lite refresh? 

Need to update 2(3) places,
* Dash
* 4_application desktop app
*(3_code-migration .... I think this can stay stale, need to remember to only run from 4_application now. Need to keep EVERYTHING in 4_application, not just web. DO NOT DELETE any of the /Canneberge/)

---

## #24: Refresh message - bottom left of window
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/24

### Description
Does this work on all pages (aka main window)

Right now on completion stops at "StockAnalysis complete. xxxx rows." 

Need to update that either to all complete or list all methods with a checkmark when complete or something else

---

## #22: Dashboard page FV reconciliations
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/22

### Description
For BEV, need to go through the full bridge. Right now, reconciliation values from GPC page are right after weighting section, need to be after full GPC bridge section. 

For equity this is not the case, can stop after weighting section


In general - GPC page bridge section needs to be cleaned up now that we have the hidden dashboard bridge too. 

---

## #15: Analytics
- **State:** open
- **URL:** https://github.com/PampleMousseLabs/ProjectCanneberge/issues/15

### Description
Always be thinking of items to add into this section

Implemented:


Ideas:
* PVGO was a good idea, is there a way to identify actual $s vs implied GOs or ltgr to identify somehow mispriced or expensive growth cash flows?
* Maybe CSRP on DCF can be another dimension on some sort of chart. Maybe target range Min CSRP to Max CSRP?
* Historical multiples for subject create trend line over time, measure against trend line for GPCs/industry multiples at same period. 


Scrapped ideas:
Present Value of Growth Opps (PVGO): used GG model to identify FCFE0/(disc) vs FCFE1/(disc. - growth) to calculate growth cash flow attributed to total equity value. Scrapped as this is just the same as reverse_dcf modules implied ltgr. 

Residual equity vs BEV derived equity as a function of debt as % of TIC: scrapped as shape remained identical across GPCs, no true insight given to due half baked/non-realistic assumptions

---

