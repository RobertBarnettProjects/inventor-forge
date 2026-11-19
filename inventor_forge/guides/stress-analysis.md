# Stress Analysis

## Before solving
- Hand-check loads, load paths and stability first. Decide which loads are global: a self-equilibrating preload
  (a tie-down pulling a lug up and the payload down) adds nothing to global bending.
- After any geometry change, update the mesh before generating automatic contacts (`update_contacts` does both).
  Automatic contacts use the last mesh: new parts get no contacts and nothing says so.
- Contacts between parts that no longer touch stay in the list. Delete only after measuring that they are apart
  (`update_contacts(delete_stale=true)`), never by part name alone, and review the list of deletions.
- After every contact change, `list_contacts`: each component has every neighbour it should touch, and each type is
  the intended one. A component with no contacts floats.
- Separation contacts make solves 10-20 times slower than bonded ones.
- "Degenerate element" appears only at solve time; a mesh preview doesn't catch it. Suppress-and-solve finds the
  culprit.
- Restrain with the minimum: "Detect and Eliminate Rigid Body Modes" when the loads balance, or 3-2-1 point
  restraints. Never a whole face, and never reuse a restraint chosen for one support case in another.
- A restraint added only for stability must carry nothing: check its reaction forces and moments on the first solve.
  The totals can be zero while it still works (0 N but several kN·m), and self-balanced pairs cancel in the totals but
  still load it locally. A peak at a restraint means the restraint is doing work: fix it, don't discount the peak.
- Validate the first model completely before a batch: reactions at every restraint, a contour capped at yield over
  the whole model, the peak location and a hand check. Results that barely change between design options point at
  the boundary conditions, not the structure.
- Welded plates: model each weld as a body (`weld_body`), touching both parts, and set the lapped faces between the
  plates to Separation. Check every weld body before solving: its volume (leg²/2 × length), where it sits, and a
  contact with each part. A missing weld silently disconnects a part.
- After copying a study onto a model whose parts changed since the template was set up, rebuild every model state
  and update the mesh: otherwise the solve fails at once with "Element material isn't defined".

## Running
- Never call COM during a solve or a report: Inventor can crash. `solve_state` polls with Windows calls only.
- Entering the Stress Analysis environment is the commonest crash point. Save before, keep runs resumable.
- At most two solves at once on one PC; light work alongside two solves has cost finished results. Memory, not
  processor time, is the limit: each solver uses about two threads but several GB. A solve won't start beside others
  when free memory is under 6 GB (`INVENTOR_FORGE_MIN_FREE_GB`).
- Never save a model, or open and save one, while another Inventor is solving it: the solver's own save then fails
  and the result is lost.
- The Study edit dialog changes the active study, not the selected one: activate a study before renaming it
  (`rename_study` does) and check the name changed from exactly old to new.
- Save Stress Analysis edits from within the Stress Analysis environment.
- A re-run that finishes in seconds may have reused saved results from an interrupted run: compare its numbers with
  the previous run before accepting it.
- Load values live in `sa_N` parameters. A copied study gets a new block; match by value
  (`run_study_cases` does this).
- A large study copy can take over 8 s to appear; wait about 40 s before retrying.
- `solve_study` skips a study whose inputs haven't changed since its last solve.
- A finished solve can leave stacked "Cancel study?" prompts that stop Inventor responding. Close the Simulate
  dialog as soon as the study reports finished.
- A solve that ends in an error leaves no Results node; check before reading results.

## Reading results
- The colour bar's maximum is the true peak only while "Maximum" is automatic.
- To show everything above a limit, cap the scale's maximum at it (`set_result_colors(maximum=yield)`): values above
  saturate red. Raising the minimum doesn't work, because values below the minimum take the minimum's colour.
- Load figures: Inventor draws one glyph per load and no values, so label each load on the picture.
- Find where the peak is (`read_result_maximum(locate=true)`). Peaks at sharp corners, point supports and contact
  edges are usually singularities; judge the stress a short way off (`result_at_point`).
- Hand-check every campaign with a beam model. A beam value far below the peak points to a local effect or
  singularity to locate.
- `study_report` checks reactions against applied forces. A solve much faster than its siblings suggests lost
  contacts.
- Inventor's Reaction Forces dialog has crashed it; read reactions from the report.
- Before/after figures: render both from the model's own view with the same orthographic camera, so they overlay.

## Disk
- Every solved study keeps its mesh and results beside the model (`<model>\AIP\FEA`, roughly 0.1-0.5 GB each) until
  the study is deleted. `analysis_storage` reports the size; `purge_studies` deletes superseded studies.
- On a network drive, saving results takes minutes with Inventor unresponsive. Work on a local disk.
- Deleting a study doesn't always delete its files: `analysis_storage` compares result files with solved studies.
- Every Inventor that ended or was killed leaves its solver scratch folder (`%TEMP%\AFEA_*`, several GB) behind.
  `analysis_storage` reports them; `clean_analysis_scratch` removes idle ones once no solve is running.
