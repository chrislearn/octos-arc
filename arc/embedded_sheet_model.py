"""Sheet business contracts, grounded in atomic and inherited requirements.

This is semantic app-design input. It deliberately leaves routes, transport,
storage engine, rendering framework and internal identifiers unspecified.
"""


def design():
    return {
        "data_model": {
            "Workbook": {
                "identity": "implementation-defined stable workbook identity",
                "name": "non-empty string after trimming leading/trailing spaces",
                "last_updated": "implementation-defined display value used consistently in home record and editor",
                "worksheet_order": "ordered worksheet identities",
                "last_active_worksheet": "identity of an existing worksheet",
                "visible_editor_state": "implementation-defined directly revisitable browser state identifying this workbook",
            },
            "Worksheet": {
                "identity": "worksheet identity scoped to its workbook",
                "name": "trimmed non-empty string unique within its workbook",
                "cells": "coordinate -> Cell state; independent of other worksheets",
                "selection": "most recently confirmed complete rectangular selection and current cell",
                "validation_rules": "range-scoped ValidationRule states",
                "filter_views": "range-scoped FilterView states",
                "pivot_state": "on a pivot result worksheet, the persistent configuration, source worksheet link, last successful result and refresh validity; source worksheets remain independently editable",
            },
            "Cell": {
                "coordinate": "same-worksheet A1-style coordinate",
                "original_content": "ordinary input text or original submitted/adjusted formula expression",
                "displayed_value": "ordinary original value, current calculated result, or stable formula error",
                "formula_dependencies": "same-worksheet references implied by the current original formula",
            },
            "Selection": {
                "rectangle": "complete contiguous rectangle bounded by two cell coordinates",
                "current_cell": "confirmed selected cell in the active worksheet",
                "aria_selected_cells": "exactly the cells in the selected rectangle; all others false",
            },
            "ValidationRule": {
                "worksheet": "owning worksheet identity",
                "range": "constrained cell rectangle that follows originally constrained cells on structural changes",
                "kind": "Dropdown | Number range",
                "allowed_values": "for Dropdown: comma-separated items trimmed of leading/trailing spaces",
                "minimum": "for Number range: inclusive numeric lower bound",
                "maximum": "for Number range: inclusive numeric upper bound",
            },
            "FilterView": {
                "worksheet": "owning worksheet identity",
                "source_range": "exact selected data region with header row; follows structural changes",
                "criteria": "per-column distinct-value selections or supported conditions, combined across columns with AND",
                "visible_rows": "matching source rows without deleting or reordering source records",
            },
            "PivotTable": {
                "source_worksheet": "source worksheet identity",
                "source_range": "selected header-containing range adjusted by source row/column changes",
                "result_worksheet": "separate worksheet identity named with first unused PivotN at creation",
                "row_field": "selected available source header, tracked when its source column moves",
                "column_field": "optional selected available source header, tracked when its source column moves",
                "value_field": "selected available source header, tracked when its source column moves",
                "summarize_by": "SUM | COUNT | AVERAGE",
                "last_successful_result": "complete ordered summary, field layout, aggregation and grand totals",
                "refresh_validity": "whether current source range/selected fields can produce a valid replacement",
            },
            "TransferOperation": {
                "worksheet": "same worksheet for source and target; cross-worksheet transfer is outside required scope",
                "source_rectangle": "exact selected source rectangle for copy/cut",
                "target_rectangle": "complete two-dimensional target footprint",
                "mode": "external paste | copy | cut",
                "pending_cut": "source remains intact until a complete successful target commit",
            },
            "UndoHistory": {
                "scope": "current workbook session, isolated from other workbooks",
                "undo_operations": "successful recent cell edits, bulk pastes, range moves and row/column changes in reverse order",
                "redo_operations": "undone complete operations; discarded by a new successful modification",
                "restored_state": "values, formulas, rule ranges, structure, pivot-result validity and calculation results",
                "lifetime": "history may be empty after reopening; visible undo/redo result itself is persisted",
            },
        },
        "routes": [],
        "pages": [],
        "modules": [],
        "domain_contracts": [
            {
                "entity": "Workbook",
                "identity": "The home link, observed editor browser state, refresh and later browser session resolve the same current workbook identity; its entry format is implementation-defined.",
                "storage": "Successful workbook state persists through refresh, home reopening and direct observed editor-state revisits. No storage engine is prescribed.",
                "producers": ["Create blank workbook", "Import CSV", "Rename workbook", "Successful worksheet/data/analysis mutations"],
                "consumers": ["Home workbook records", "Open workbook", "Direct observed editor-state revisit", "Editor title and Last updated label"],
                "requirements": ["REQ-1-1-1", "REQ-1-2-1", "REQ-1-2-2", "REQ-1-3-1", "REQ-1-3-2"],
            },
            {
                "entity": "Worksheet",
                "identity": "A named tab represents one worksheet in one workbook. Worksheet order and active state identify the most recent successful state without leaking another worksheet's values, formulas, rules, filters or pivot state.",
                "storage": "Names, order, last active sheet, complete selections, values/formulas, rules, filters and pivot configuration/results are persistent per worksheet.",
                "producers": ["Create/import workbook", "Add worksheet", "Rename worksheet", "Delete worksheet", "Successful cell/range/structure/analysis operations"],
                "consumers": ["ARIA tab bar", "Worksheet grid", "Formula bar", "Validation/filter controls", "Pivot table editor/results", "CSV export"],
                "requirements": ["REQ-2-1-1", "REQ-2-1-2", "REQ-2-1-3", "REQ-2-1-4", "REQ-2-2-1", "REQ-2-2-2"],
            },
            {
                "entity": "Cell",
                "identity": "A coordinate identifies a cell in the current worksheet; source and target positions adjust consistently when records or structure move.",
                "storage": "Persist original ordinary text or formula expressions together with results consistent with current source values. The formula bar is the observable original-content projection; CSV export uses displayed values/results.",
                "producers": ["Grid/Formula bar commit", "External paste", "Copy/cut paste", "Insert/delete rows or columns", "Sort range", "Undo/Redo", "Formula recalculation"],
                "consumers": ["Named ARIA gridcell", "Formula bar", "Dependent formulas", "CSV export", "Filters", "Pivot aggregation"],
                "requirements": ["REQ-3-1-1", "REQ-3-1-2", "REQ-3-2-1", "REQ-3-2-2", "REQ-4-1-1", "REQ-4-1-2", "REQ-4-2-1", "REQ-4-2-2", "REQ-5-1-1"],
            },
            {
                "entity": "Selection",
                "identity": "The selected rectangle belongs to one worksheet; current-cell selection is a one-cell rectangle and subsequent range operations use the exact rectangle.",
                "storage": "Persist the complete most recently confirmed rectangle per worksheet, including cells inside/outside ARIA state, through switching and reopening.",
                "producers": ["Select cell", "Drag either rectangle corner to the opposite corner", "Open a first-time worksheet"],
                "consumers": ["aria-selected states", "Formula bar", "Paste/Copy/Cut", "Sort/Filter/Validation/Pivot range entry"],
                "requirements": ["REQ-1-2-1", "REQ-2-1-1", "REQ-2-1-2", "REQ-3-1-3"],
            },
            {
                "entity": "ValidationRule",
                "identity": "A dropdown or inclusive numeric constraint belongs to a selected worksheet range. Its range follows originally constrained cells; deleted target rules are removed.",
                "storage": "Persist effective type, original covered range and parameters; selecting an interior cell reopens that containing rule with its saved parameters and Delete rule control. Modification and deletion affect the full original range.",
                "producers": ["Save/modify/delete Data validation rule", "Insert/delete rows or columns", "Undo/Redo structure operations"],
                "consumers": ["Grid commit", "Formula bar commit", "External rectangle paste", "Copy/cut target validation", "Dropdown options", "Data validation editor"],
                "requirements": ["REQ-5-2-1", "REQ-2-2-1", "REQ-2-2-2", "REQ-3-1-1", "REQ-3-1-2", "REQ-3-2-1", "REQ-3-2-2"],
            },
            {
                "entity": "FilterView",
                "identity": "A filter is scoped to the user's selected header-containing source region; per-column conditions combine with AND and never become implicit filters on adjacent data or another worksheet.",
                "storage": "Persist source region and criteria/visibility. Source records retain their original values and order, including hidden rows consumed by export and pivot.",
                "producers": ["Create filter", "Apply distinct-value filter", "Apply condition", "Clear filter", "Source row/column changes"],
                "consumers": ["Filter header buttons", "Visible grid rows", "CSV export", "Pivot source aggregation", "Worksheet switching/reopening"],
                "requirements": ["REQ-5-1-2", "REQ-5-1-1", "REQ-2-2-1", "REQ-2-2-2", "REQ-1-3-2", "REQ-5-3-1"],
            },
            {
                "entity": "PivotTable",
                "identity": "A pivot associates a current source worksheet/range and selected source fields with a separate result worksheet; source fields track structural movement, while a deleted selected field becomes unavailable.",
                "storage": "The result worksheet owns the persistent field layout, source link, summarization method, refresh validity and complete last successful result. Source edits/structure changes do not replace this result until explicit successful refresh; deleting a selected source field retains the result and marks refresh invalid.",
                "producers": ["Create pivot table", "Apply pivot configuration", "Refresh pivot table", "Delete pivot-result worksheet", "Source structural changes", "Undo/Redo validity restoration"],
                "consumers": ["Pivot table editor", "Pivot result grid", "Refresh action", "Source worksheet deletion guard", "Worksheet switching/reopening"],
                "requirements": ["REQ-5-3-1", "REQ-2-1-4", "REQ-2-2-1", "REQ-2-2-2", "REQ-3-2-2"],
            },
            {
                "entity": "TransferOperation",
                "identity": "A complete external-paste or copy/cut transfer has one target rectangle in the current worksheet; copy/cut source and target belong to that same worksheet.",
                "storage": "Persist the complete successful source/target and affected-formula state. A pending cut remains uncommitted and retains its original source until the complete target commit; no clipboard serialization or pending-transfer persistence is prescribed.",
                "producers": ["External paste", "Copy", "Cut", "Paste transfer"],
                "consumers": ["Source/target cells", "Target validation", "Affected formula results", "Undo/Redo operation restoration"],
                "requirements": ["REQ-3-1-2", "REQ-3-2-1", "REQ-3-2-2"],
            },
            {
                "entity": "UndoHistory",
                "identity": "Undo/redo history belongs to the current workbook session and never acquires authority to mutate another workbook.",
                "storage": "Persist the complete visible result of every successful undo/redo. The operation history itself is session-scoped and may be empty after reopening; no persistent-history representation is required.",
                "producers": ["Successful cell edit", "Successful bulk paste", "Successful range move", "Successful row/column structure change", "Undo", "Redo", "New successful modification after Undo"],
                "consumers": ["Undo/Redo controls and keyboard actions", "Restored source/target values and original formulas", "Restored rule ranges and row/column structure", "Restored pivot-result validity and calculation results"],
                "requirements": ["REQ-3-2-2"],
            },
        ],
        "contracts": [
            {
                "requirements": ["REQ-1-1-1", "REQ-1-2-1", "REQ-1-2-2", "REQ-1-3-1", "REQ-2-1-1", "REQ-2-1-2", "REQ-2-1-3", "REQ-2-1-4"],
                "invariants": [
                    "Home is the visible workbook entry; successful open/create/import enter the same editor behavior and stable workbook state.",
                    "Home workbook name/Last updated agree with the corresponding editor; worksheet order and last active sheet remain consistent after reopening.",
                    "Only the opened workbook and current target worksheet may be modified; unrelated workbooks/worksheets preserve their successful state.",
                    "Creation starts with only blank Sheet1 active and A1 selected. Adding a sheet uses first unused SheetN, becomes active at A1, and inherits no analysis/rules/data.",
                    "Workbook and worksheet names trim boundary spaces and reject empty names; worksheet names are unique only within the same workbook.",
                    "The final worksheet cannot be deleted. A pivot source cannot be deleted while dependent pivot results remain; deleting a result releases its source dependency.",
                    "Every successful worksheet deletion activates an actual adjacent survivor, including when the deleted worksheet was not active.",
                ],
            },
            {
                "requirements": ["REQ-1-1-1", "REQ-2-1-2", "REQ-3-1-3"],
                "invariants": [
                    "Tabs use ARIA tab role and active aria-selected=true. Active grid is named Worksheet grid, exposes grid role and aria-multiselectable=true.",
                    "Cells use gridcell role and their coordinates as accessible names; exactly all selected-rectangle cells are aria-selected=true and all outside cells false.",
                    "Selecting a cell/range replaces previous selection. Complete per-sheet rectangles survive refresh/reopening/switching; first-time sheets select A1.",
                    "Row/column headers use rowheader decimal number and columnheader letter names. Named menu commands use menuitem roles; named combo options use visible option names.",
                ],
            },
            {
                "requirements": ["REQ-1-3-1", "REQ-1-3-2", "REQ-3-1-1", "REQ-3-1-2", "REQ-3-2-1", "REQ-5-2-1"],
                "invariants": [
                    "Ordinary original text and formula expressions are distinct from formula displayed results; imported numeric text retains its original text.",
                    "Import preserves complete ordered CSV rows/columns, empty fields, Unicode, quoted commas/escaped quotes/embedded newlines and ordinary first-row data.",
                    "Unclosed CSV quoted fields reject the import with no partial workbook or matching home link. Imported names remove only the final .csv extension.",
                    "Export is a browser download ending in .csv with UTF-8 ordered current-sheet values, used-range empty cells and proper escaping; formulas export calculated results.",
                    "Export includes filtered hidden source rows and preserves active sheet, filter view, grid values, selection and formula-bar content.",
                    "Enter or selecting another cell commits; Escape cancels pending content. A rejected commit leaves original grid/formula-bar content and dependent results intact.",
                    "Explicitly submitting imported formula text interprets it as a formula even when its characters have not changed; focusing and blurring untouched imported text does not itself submit a formula.",
                    "A rectangle paste/transfer is one atomic operation: every target and affected dependency updates, or every source/target/dependent state stays unchanged. Cut clears source only after target completion.",
                ],
            },
            {
                "requirements": ["REQ-2-2-1", "REQ-2-2-2", "REQ-3-2-2", "REQ-4-1-2", "REQ-4-2-1", "REQ-5-1-1", "REQ-5-2-1", "REQ-5-3-1"],
                "invariants": [
                    "Row/column insertion moves complete subsequent data, rule ranges and formula references together; deletion removes target data/rules and shifts survivors without partial movement.",
                    "Adjusted formula expressions and results remain consistent; invalid direct references show explicit errors, including #REF! for deleted source columns.",
                    "Coordinate conversion must round-trip A1-style names, including Z/AA boundaries. Keep the index origin consistent across consumers; insert-right/below uses the position after the chosen header, preserving references before that insertion and the untouched axis.",
                    "Filter regions continue to address original data after structure changes, and pivot source ranges/fields track those changes while last successful results await refresh.",
                    "A source structure operation updates every dependent pivot configuration by source worksheet identity, even though each configuration and last result belongs to a separate result worksheet. Deleting a selected field invalidates it; an adjacent identical header does not acquire the deleted field's identity.",
                    "Sorting affects exactly the selected rectangle, preserves declared header, compares numeric/date/text values by type, preserves equal-key order and moves full records/formulas consistently.",
                    "Equal typed sort keys remain equal despite different source spellings such as 2, 02 and 2.0; do not apply a lexical tie-break after numeric or date equality.",
                    "Undo/redo restores/reapplies whole operations including values, original formulas, rule ranges, structure, pivot validity and results; new successful modifications discard redo branches.",
                ],
            },
            {
                "requirements": ["REQ-4-1-1", "REQ-4-1-2", "REQ-4-2-1", "REQ-4-2-2"],
                "invariants": [
                    "Required formula grammar includes numeric constants, parentheses, + - * /, same-sheet A1 references and contiguous-range SUM/AVERAGE/COUNT/MIN/MAX; function names are case-insensitive.",
                    "Aggregate functions ignore blanks; COUNT counts numeric cells only and numeric aggregation ignores text, including boolean-looking ordinary text TRUE/FALSE, without treating blanks as zero.",
                    "Copied relative row/column references follow offset while absolute references stay fixed. A relative reference shifted out of worksheet bounds yields original target formula =#REF! and displayed #REF!.",
                    "For mixed references such as $A1 and A$1, preserve the absolute axis and shift only the relative axis; use the same reference transformation contract for copy, structural edits and sorted formulas.",
                    "Successful source edits/pastes/moves/structure changes recalculate direct/transitive dependencies in order; unrelated cells/worksheets remain usable and unchanged.",
                    "Stable errors are #DIV/0! for division by zero, #REF! for invalid/circular references, #NAME? for unsupported functions, #ERROR! for malformed expressions; original submitted expression persists.",
                    "Fixing a formula restores its current result and dependent results through reopening; an error in one formula does not block unrelated editing or recalculation.",
                ],
            },
            {
                "requirements": ["REQ-5-1-2", "REQ-5-2-1", "REQ-5-3-1"],
                "invariants": [
                    "Filter values are distinct displayed source values. Supported conditions are Text contains, Greater than, Before, Is empty and Is not empty; only the first three require a Value.",
                    "Different-column filters use AND, hide nonmatching rows without deletion/reordering, and Clear filter restores original records without changing formulas/rules.",
                    "Dropdown allowed items are trimmed; numeric limits are inclusive. Grid, formula bar, paste and range move all enforce the same saved rule and reject the entire bulk operation when any target is invalid.",
                    "Dropdown rejection shows Please select one of the following values: <comma-separated allowed values>; numeric rejection shows Please enter a number between <minimum> and <maximum>, with Please enter a number from 0 to 100 in the specified persisted B3/structural boundary scenarios.",
                    "Existing validation editor restores type/parameters and offers Delete rule; successful save/modification/deletion closes it without modifying existing cell values.",
                    "Selecting a cell inside an existing validation range must reopen that containing rule, not require selection of its exact full rectangle.",
                    "Pivot reads all qualifying source records including hidden rows and never edits/reorders source data. SUM/AVERAGE consume parseable numbers; COUNT counts non-empty value records including text.",
                    "Pivot groups and column-field values follow first source appearance. No-column headers are row field and <method> of <value field>; optional-column layout adds a final Grand Total column; every layout has a final Grand Total row.",
                    "Blank row or column group values still represent source records. Ordinary group text such as constructor or __proto__ must aggregate as data rather than collide with implementation properties.",
                    "COUNT missing/empty-value combinations display 0. SUM/AVERAGE fields with no parseable numbers reject visibly with Value field requires numeric values and preserve the last successful result/source.",
                    "Refresh fully replaces old results only on success. Deleted selected headers show Pivot field is no longer available. Select a new field.; invalid range/field refresh preserves source and last successful result.",
                ],
            },
        ],
        "commands": _commands(),
        "notes": (
            "Derived from all 24 Sheet atomic descriptions and inherited parent contracts. "
            "The supplied scenarios contain repeated non-actionable requested workflow placeholders, "
            "so precise atomic prose controls semantic obligations. Routes/pages/modules are deliberately "
            "empty: no URL syntax, API endpoint, internal database identifier, storage engine, framework "
            "or unsupported control label is prescribed. Entity fields describe observable shared state, "
            "not a mandatory serialization format. The required scope is unauthenticated workbook use; "
            "sharing/collaboration, advanced styling/charts/macros, cross-sheet formula references and "
            "cross-sheet range transfer are outside core required scope. Requirements do not define "
            "generic infrastructure-failure injection, empty-group AVERAGE formatting, displayed numeric "
            "precision, or undo-history persistence after reopening; implementations must satisfy stated "
            "success/rejection invariants without inventing those as official constraints. This model and "
            "the paired tests were source-reviewed; no generated full Sheet product was available for "
            "end-to-end execution."
        ),
    }


def _command(name, requirements, preconditions, effects, rejected_effects, transitions, persistence):
    return {
        "name": name,
        "requirements": requirements,
        "preconditions": preconditions,
        "effects": effects,
        "rejected_effects": rejected_effects,
        "state_transitions": transitions,
        "permissions": [],
        "persistence": persistence,
    }


def _commands():
    saved = "The most recent successful visible workbook/worksheet state persists through refresh and reopening; other workbooks/worksheets remain unchanged."
    atomic = "On rejection show the requirement's visible error, preserve all pre-operation state immediately and after refresh, and retain a retryable control state."
    return [
        _command("View and open workbook", ["REQ-1-1-1"], ["Start at home and use the workbook-name link or revisit the observed editor state."], ["Show corresponding title/Last updated, ordered tabs, last active sheet, structure, cells, formulas, filters, validation entry and pivot state."], ["Do not display another workbook's grid or a temporary blank workbook for the same saved editor state."], ["Home record -> corresponding stable editor; observed editor state -> most recent successful same-workbook state."], saved),
        _command("Create blank workbook", ["REQ-1-2-1"], ["Home New blank workbook button opens creation page; submit via Create."], ["Create one workbook with only blank Sheet1 active and A1 selected; update home record."], ["On creation failure show error and retryable state without an incomplete home record."], ["Home -> creation -> saved editor, or creation -> retryable error."], saved),
        _command("Rename workbook", ["REQ-1-2-2"], ["Open Rename workbook and the Workbook name control prefilled with last saved name."], ["Trim boundary spaces and save non-empty name to both title and home link."], ["Empty trimmed name shows Workbook name cannot be empty; other save failures preserve original name."], ["Saved name -> pending name -> saved new name or original saved name plus error."], saved),
        _command("Import CSV", ["REQ-1-3-1"], ["Home Import CSV dialog; choose CSV file and Confirm import."], ["Parse entire original CSV text/order; create file-basename workbook with one Sheet1; first row is ordinary data."], ["Unclosed quoted field shows Invalid CSV file format. Import failed.; any parse/import failure creates no partial state or matching home link."], ["Home -> pending file -> complete imported editor or original home/retryable import error."], saved),
        _command("Export current worksheet CSV", ["REQ-1-3-2"], ["Current workbook has an active sheet; use Export CSV."], ["Download UTF-8 .csv of actual used-range order/empty cells/escaped text and calculated formula results, including filtered hidden rows."], ["Export must never mutate current content, active tab, filter view or formula bar."], ["Saved editor -> downloaded snapshot plus same saved editor."], "Export is read-only; the same visible state remains after refresh."),
        _command("Add worksheet", ["REQ-2-1-1"], ["Use Add worksheet in current workbook."], ["Append first unused SheetN, blank and isolated from source rules/filters/pivots; activate it with A1 selected."], ["Addition failure shows error and leaves no new tab or existing-sheet changes."], ["Existing ordered sheets -> ordered sheets plus active blank new sheet, or unchanged sheets plus error."], saved),
        _command("Switch worksheet", ["REQ-2-1-2"], ["Click a target ARIA tab in the same workbook."], ["Restore target structure/grid/selection/formula bar/filter/rules/pivot state; first-time target uses A1; retain source state."], ["Switching must not mutate or substitute source/another sheet state."], ["Active source -> active target with each sheet's own saved selection."], saved),
        _command("Rename worksheet", ["REQ-2-1-3"], ["Worksheet options menu Rename opens Rename worksheet dialog prefilled with current Worksheet name."], ["Trim name, save non-empty workbook-unique value while retaining sheet identity/order/data."], ["Empty shows Worksheet name cannot be empty; duplicate shows Worksheet name already exists; preserve original on any failure."], ["Original tab -> pending name -> renamed same worksheet or original plus error."], saved),
        _command("Delete worksheet", ["REQ-2-1-4"], ["Use Delete menu command; allowed deletion requires Delete worksheet dialog confirming target name."], ["Remove target and its full data/formula/filter/rule/pivot state; activate an adjacent sheet; deleting pivot result removes its source constraint."], ["Final sheet shows A workbook must contain at least one worksheet without dialog; pivot source confirmation shows Please delete or rebuild dependent pivot tables first, closes dialog and preserves source/results; other failures preserve target."], ["Existing target -> confirmation -> removed target and adjacent active survivor, or unchanged target plus visible rejection."], saved),
        _command("Insert/delete rows", ["REQ-2-2-1"], ["Use named rowheader context menu Insert 1 row above/below or Delete row."], ["Move all subsequent complete records/rules/references consistently; remove deleted-row rules; adjust filters/pivot source range; recalculate formulas."], [atomic, "Shifted 0-to-100 rule rejects out-of-range input with Please enter a number from 0 to 100; unpreservable references display explicit errors."], ["Pre-operation structure -> complete adjusted structure with old pivot result pending explicit refresh, or unchanged structure plus error."], saved),
        _command("Insert/delete columns", ["REQ-2-2-2"], ["Use named columnheader context menu Insert 1 column left/right or Delete column."], ["Move complete surviving data/rules/references; preserve outside-deleted-column data; track filter/pivot fields; deleted selected headers invalidate refresh without replacing old result."], [atomic, "Invalid direct references show #REF!; shifted 0-to-100 rule rejection uses Please enter a number from 0 to 100."], ["Pre-operation structure -> complete adjusted structure plus adjusted dependencies/analysis validity, or unchanged structure plus error."], saved),
        _command("Edit cell", ["REQ-3-1-1"], ["Select cell; edit Formula bar or double-click cell for Edit <coordinate>."], ["Enter or selecting another cell commits ordinary text/numbers/boolean-like/date text/formula; synchronize original formula/value and displayed result; recalculate direct/transitive dependents."], ["Escape cancels pending input; failed commit leaves original grid and formula-bar value/expression and dependent results unchanged."], ["Saved cell -> pending input -> saved complete edit, cancelled original, or rejected original plus error."], saved),
        _command("Paste external rectangle", ["REQ-3-1-2"], ["Select start cell and paste same tab/newline external clipboard via Paste menuitem or Ctrl+V."], ["Apply entire rectangle, preserve empties/layout, overwrite only target, replace target formulas and update dependencies."], [atomic, "Any invalid numeric target rejects every target; 0-to-100 scenario shows Please enter a number from 0 to 100."], ["Clipboard plus saved target -> complete pasted target or complete unchanged target plus error."], saved),
        _command("Select cell/range", ["REQ-3-1-3"], ["Click cell or drag between opposite rectangle corners."], ["Replace selection with exactly all rectangle cells; mark inside true/outside false; subsequent operations use only this range."], ["Do not expand to adjacent existing data or retain only the top-left corner after reopening."], ["Previous selection -> complete current sheet rectangle, independent of other sheets."], saved),
        _command("Copy/cut/paste range", ["REQ-3-2-1"], ["Select complete source rectangle and target location in same worksheet."], ["Copy retains source; successful cut clears source only after target fully commits; preserve layout and copied formula relative/absolute reference semantics; outside cells untouched."], [atomic, "Invalid validated target rejects the whole source/target update, including source clearing and affected formulas."], ["Saved source/target -> copied or pending-cut transfer -> complete saved transfer or complete original state plus error."], saved),
        _command("Undo/Redo", ["REQ-3-2-2"], ["Current workbook session has a recent successful/undone operation; toolbar or Ctrl+Z/Ctrl+Y."], ["Restore/reapply whole cell/paste/range-move/structure operation with formulas/rules/pivot validity/results; consecutive undo is reverse order; new successful modification disables Redo and Ctrl+Y old branch."], ["No effect on another workbook; disabled redo cannot restore abandoned branch."], ["Successful operation -> restored previous state -> reapplied operation, or new successful branch discarding redo."], "Persist every resulting visible state; history itself may be empty after reopening."),
        _command("Calculate expressions/functions", ["REQ-4-1-1"], ["Submit required basic expression or case-insensitive SUM/AVERAGE/COUNT/MIN/MAX over same-sheet contiguous range."], ["Calculate from current numeric source cells; ignore blanks/text for numeric aggregation and count only numeric cells for COUNT; show original expression in formula bar."], ["Unsupported/malformed/reference/division/circular errors use REQ-4-2-2 stable values rather than stale numeric results."], ["Committed expression plus current inputs -> current result/error and preserved original expression."], saved),
        _command("Copy formula references", ["REQ-4-1-2"], ["Copy formula through same-sheet range transfer to offset target."], ["Adjust relative row/column references by target offset, keep absolute references, preserve source and calculate target with adjusted original expression."], ["Out-of-bounds relative offset yields target original =#REF! and displayed #REF!, without altering source."], ["Source formula -> unchanged source plus adjusted target formula/result or explicit invalid target reference."], saved),
        _command("Recalculate dependencies", ["REQ-4-2-1"], ["A source edit, paste, move or structure change successfully commits."], ["Update direct and transitive formulas in dependency order from current source data; retain consistent original expressions and unrelated-sheet results."], ["Rejected source operation does not change dependent results; successful changes must not retain pre-change results after reopening."], ["Current committed sources -> consistent direct/transitive results/errors."], saved),
        _command("Display/fix formula error", ["REQ-4-2-2"], ["An entered formula is erroneous, or user edits its original expression to a valid formula."], ["Show stable error and original formula; keep unrelated work usable; valid correction updates result/dependents and clears prior error after reopening."], ["An error must not block unrelated viewing/editing/recalculation or replace original submitted formula."], ["Erroneous expression -> persistent explicit error -> valid corrected expression with recovered dependent results."], saved),
        _command("Sort range", ["REQ-5-1-1"], ["Select exact range; Data Sort range dialog selects header-named Sort by, Ascending/Descending Order and Data has header row."], ["Compare numbers/dates/text by type; stable equal-key order; move entire records/formulas; preserve declared header and outside range; retain same-range filters/rules."], [atomic, "Failed sort retains original row order."], ["Selected original records -> complete ordered same-range records or unchanged order plus error."], saved),
        _command("Create/apply/clear filter", ["REQ-5-1-2"], ["Select header region; Data Create filter; open Filter <header> for displayed value checkboxes or supported Condition/Value."], ["Use distinct source-value selection or condition; AND across columns; hide only nonmatches without record deletion/reordering; clear restores originals; export/pivot read hidden records too."], ["Filtering may not modify source values/order/formulas/rules, adjacent ranges or other worksheets."], ["Unfiltered records -> saved filtered view -> cleared original view."], saved),
        _command("Save/modify/delete validation", ["REQ-5-2-1"], ["Select target range; Data validation Rule type/parameters; selecting any covered interior cell reopens the existing rule prefilled with Delete rule."], ["Save trimmed Dropdown options or inclusive Number range; modification/deletion changes the entire original covered range; close on success without changing current values; enforce the new saved constraint through every input/transfer path."], ["Invalid grid/formula/paste/move value shows required dropdown/numeric error; any invalid bulk target retains every original source/target value."], ["Unconstrained/effective old rule -> effective saved/modified rule or deleted constraint; invalid write -> complete unchanged values."], saved),
        _command("Create/apply/refresh pivot", ["REQ-5-3-1"], ["Select header source; Data Create pivot table dialog shows Source range: <range>, New worksheet and Create; the new result worksheet exposes Pivot table editor with Rows/optional Columns/Values/Summarize by then Apply."], ["Create first unused PivotN result sheet and link it persistently to the source; aggregate all qualifying source rows including hidden rows using required numeric/nonempty semantics; order groups by first appearance with Grand Totals; persist successful configuration/results; explicit refresh fully replaces old results with current adjusted source."], ["Deleted selected header shows Pivot field is no longer available. Select a new field.; nonnumeric-only SUM/AVERAGE shows Value field requires numeric values; other invalid range/field gives visible error; preserve source and complete last successful result."], ["Source selection -> new pivot sheet/configuration -> successful saved result; source changes -> stale last successful result -> explicit refreshed result or preserved result plus error."], saved),
    ]
