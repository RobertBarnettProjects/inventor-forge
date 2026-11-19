# Drawings

## Building sheets
- Build each sheet type from one script or one call sequence and rebuild it end to end after every change; don't
  hand-patch.
- Look at a picture of every build (`render_sheet`), zoomed where it matters, before reporting.
- Lay out by measurement: place, read the range box, then move.
- Choose scales by rule from the model size, so the same steps fit other sizes.
- Pick geometry by exact component name from the view's curves, not by guessed coordinates.
- Ask for house style early: view titles, scales, sheets, which views.

## Company templates
- A template that draws its title block in the border has no title block object: tell the tools where it is with
  `set_title_area`.
- A drawing made from a template doesn't carry the template's prompted values: `set_prompted_fields` on every sheet.
- Prompt values for `AddTitleBlock` / `AddBorder` must be a typed string array (`set_sheet_format` does this). Prompt
  names must be unique. Inventor writes them as `<Prompt ReadOnlyUniqueID='n'>`.
- Author and Designer iProperties fill in with the Windows user name; use prompted entries for initials.
- A title block is placed 10 mm in from the corner, so a full-sheet layout belongs in a border definition.

## Views and annotation
- Dimensions to sloped or chamfered ends show fractions (195.88); `set_dimension_precision` rounds them.
- Section cut lines run 10-16 mm past the view so the letters clear the part. Put cuts off-centre so they don't
  collide with a centred view title.
- Notes keep clear of view labels, sketched symbols and section letters; check every title and leader anyway.
- Leader-note text runs away from the arrow: text placed left of the arrow point is right-justified to it. Find room
  on that side, and check leader text in the picture: overlap checks don't see it.
- Wrap notes with a 10 % margin: capitals are wider than the average character width.
- A detail view's fence letter has no switch of its own; blanking the detail view's name hides it.
- A sketched symbol's leader starts at its insertion point, so put the symbol's origin on the corner that faces the
  target.
- After any text change, render again: longer text wraps onto more lines and can run into the title block.
- Totals on a drawing must equal quantity × the rounded value shown for each, and notes must add up the shown totals.
- Tables of your own (cut lists, weld schedules, load tables): `add_custom_table`. `check_drawing` checks them
  against views and the title block.
- End views of fabricated assemblies hide internal members: use a section plus an enlarged detail.
- Hide analysis-only bodies (weld bodies, ground pads) in views: `hide_components_in_views`.
- Before calling a stray shape a hidden-component failure, list which components the view actually draws.
- `AddDetailView` with a circular fence takes a radius number; pass omitted optional arguments as missing, not None.

## Rebuilding edited drawings
- To edit only the drawing while its model is in use (a solve), save the drawing alone
  (`save_document(only_this=true)`), so the model file is never written.
- People edit generated drawings. Before a rebuild, `supersede_drawing(path)`: it records where notes and symbols
  sit and moves the old file into a Superseded folder. After the rebuild, `apply_positions`, then save to the
  original path.
- Never put sample values into the file's iProperties; only in memory, and only when asked.
