# Assemblies

## Placing and checking
- `place_component` adds the component to every model state.
- After each change, `check_interference` (fast, volumes in mm^3) or `check_assembly`. An overlap that "looks fine"
  is usually a cut on the wrong side or a part in the wrong place.
- Pick components by exact name (`Runner:1`). A name without `:n` is accepted only when one component has it;
  substrings are never matched (a weld body `FW_Runner_Deck` is not `Runner`).

## Design for fabrication before analysis
- Before modelling an added member for analysis, settle how it is attached and leave room for it: weld size (the
  minimum for the thicker part), toe clearance to edges and other welds, access, standard plate sizes.
- Model added plates the way they will be attached. Faces that touch become bonded contacts, which treats a lapped
  plate as a solid section. Use Separation contacts on lapped faces and carry the load through modelled weld bodies.

## Copying an assembly
- Use `copy_assembly`, not Save As. Save As leaves parts used only in inactive model states linked to the original
  folder, and nothing reports it.
- References are mapped by file name only. A whole-path text replace also rewrites folder names that share the
  prefix.
- Verify from the saved files' `ReferencedFileDescriptors`. `AllReferencedDocuments` lists loaded documents only.
  The descriptors also list the Stress Analysis set-up files (`AIP\FEA`), and a copied model can still point at its
  source's: check for missing references (`list_references`) before moving any folder.
- Walking `File.AllReferencedFiles` has crashed Inventor; use the open documents and the top file's descriptors.
- `os.path.normcase` lower-cases paths: compare with it, but copy and save with the real path.
- Never rename or move a folder other copies may still link to: their studies fail with "Invalid constraint".
- Repointing can drop Stress Analysis contacts, which automatic contacts recreate as Bonded. `copy_assembly`
  compares contact types before and after; set them again if they changed.
- Component names inside the copy keep the original names (`K1_Post:1`); only the files are renamed.
- Prune studies before copying (`purge_studies`): each study's mesh and results are copied with the model.

## Checking and repairing references
- Inventor quietly finds a moved file through the project's search paths, so a model can open fine here and break
  on another PC or under another project. `list_references` reads every reference from the files (inactive model
  states and Stress Analysis set-up files included) and marks each ok, found_elsewhere, substituted (same name,
  different design), missing or disabled; `root` also flags references outside a folder (before packaging).
- `replace_reference` repoints one file, a file name wherever it is used, or a whole folder to a new folder. It
  backs up every file it changes into a reference_backups folder in the job folder, saves, and reads the references back.
  Run it with `dry_run=true` first. Inventor only accepts a copy of the same design as the new file.
- Repointing can change Stress Analysis contacts as `copy_assembly` notes: list contacts before and after.

## Saving
- `save_document(list_only=true)` shows every document a save would write. A path equal to the document's own file
  saves in place.
- Saves run in silent mode, so a "save dependents?" prompt can't hold the session.
