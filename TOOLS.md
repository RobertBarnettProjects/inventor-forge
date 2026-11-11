# inventor-forge tools

168 tools. Lengths mm, angles degrees, forces N, stresses MPa.

## Session

| Tool | What it does | Arguments |
|---|---|---|
| `connect` | Attach to the running Inventor (or start it) and report the version, project and open documents. | `private` |
| `close_private_inventor` | Close the separate Inventor started by connect(private=true), discarding anything unsaved in it. Never touches an Inventor this session did not start. |  |
| `list_projects` | Inventor projects known to this machine and which one is active. |  |
| `set_active_project` | Switch Inventor's active project (by name or .ipj path). Inventor only allows this with no documents open. | `project`* |
| `status` | Active document summary (type, path, feature/sketch/body counts, volume, material). |  |
| `list_documents` | Every open (visible) document, with the active one marked. |  |
| `transaction` | Group several operations into one undo step: begin, commit, or abort (rolls everything back). | `action`, `name` |
| `undo` | Undo the last N operations in the active document. | `steps` |
| `model_version` | A cheap fingerprint of the active document's geometry, for noticing edits made by hand in Inventor (it changes whenever the model's shape changes). |  |

## Documents

| Tool | What it does | Arguments |
|---|---|---|
| `create_part` | New metric part document (optionally a sheet-metal part) and make it active. | `name`, `sheet_metal` |
| `create_assembly` | New metric assembly document and make it active. | `name` |
| `open_document` | Open an Inventor file (.ipt .iam .idw .dwg) or import STEP/IGES/SAT, and activate it. | `path`* |
| `activate_document` | Bring an open document to the front by display name, file name or path. | `name`* |
| `save_document` | Save the active document; with a path, Save As (folders are created). Relative paths go under ~/Documents/inventor-forge. | `path` |
| `close_document` | Close the active (or named) document. Unsaved changes are discarded unless save=true. | `save`, `name` |
| `export_document` | Export a copy of the active document: STEP, IGES, STL, SAT, Parasolid (X_T), OBJ, JT, 3MF, PDF/DWG/DXF (drawings), PNG/JPG (picture of the view). Format comes from the extension if omitted. | `path`*, `format` |
| `close_unused_documents` | Close documents Inventor holds in the background (no window, nothing referencing them) — e.g. parts loaded for a drawing that was closed. Frees their files for save_document. Never touches documents with a window. |  |
| `referenced_files` | The active document's file and every file it depends on (parts of an assembly, the model of a drawing). |  |

## View

| Tool | What it does | Arguments |
|---|---|---|
| `set_view` | Orient the active 3D view: iso, iso_left, iso_bottom, front, back, top, bottom, left, right, home. | `view`, `fit` |
| `screenshot` | Save a PNG of the active document's view (model or drawing sheet) — look at it to check your work. | `path`, `view`, `width`, `height` |

## Sketch

| Tool | What it does | Arguments |
|---|---|---|
| `create_sketch` | Start a new sketch on a base plane (XY, XZ, YZ or a work plane name), optionally offset along its normal, or on a planar face of the body. Later draw_* calls go into this sketch. | `plane`, `offset`, `face_index` |
| `select_sketch` | Make an existing sketch the target of draw_* / extrude (by 1-based index or name). | `index`, `name` |
| `draw_rectangle` | Rectangle in the active sketch, width along sketch x, height along sketch y. | `width`*, `height`*, `x`, `y`, `centered`, `dimension` |
| `draw_circle` | Circle in the active sketch (diameter dimension added). | `diameter`*, `x`, `y`, `construction`, `dimension` |
| `draw_line` | Line from (x1, y1) to (x2, y2) mm in the active sketch (construction lines don't make profiles, but can be revolve axes). | `x1`*, `y1`*, `x2`*, `y2`*, `construction` |
| `draw_arc` | Arc by centre, radius (mm), start angle and sweep (degrees, counter-clockwise). | `x`*, `y`*, `radius`*, `start_angle`, `sweep_angle` |
| `draw_polygon` | Regular polygon. inscribed=true: radius to the corners; false: radius to the flats (a hex nut across flats S uses radius=S/2, inscribed=false). | `sides`, `radius`, `x`, `y`, `inscribed` |
| `draw_closed_profile` | Connected polyline through [[x, y], ...] mm (closed back to the first point by default). Segments share endpoints, so the result is one clean profile. | `points`*, `close` |
| `draw_slot` | Straight slot (obround): centre-to-centre length, width, centre (x, y), angle in degrees. | `length`*, `width`*, `x`, `y`, `angle` |
| `draw_point` | Sketch point (a hole centre by default — hole(..., use_sketch_points=true) drills them all). | `x`*, `y`*, `hole_center` |
| `sketch_info` | Entities, dimensions, profile count and constraint status of the active (or given) sketch. | `index` |
| `list_sketch_curves` | Curves of the active (or given) sketch with the indices that the constraint and dimension tools take. | `index` |
| `add_sketch_constraint` | Geometric constraint: horizontal, vertical (one line); parallel, perpendicular, equal, tangent, collinear, concentric (two curves). Curve indices from list_sketch_curves. | `type`*, `curve_one`*, `curve_two` |
| `add_sketch_dimension` | Driving dimension on a curve: its length (line) or diameter/radius (circle, arc). value (e.g. "25 mm" or an expression) sets it and the sketch solves to match. | `curve`*, `value`, `kind`, `x`, `y` |
| `offset_sketch` | Offset connected sketch curves by a distance (mm); flip goes to the other side. | `curves`*, `distance`*, `flip` |
| `project_edges` | Project model edges (list_edges indices) into the active sketch as reference geometry. | `edges`* |

## Features

| Tool | What it does | Arguments |
|---|---|---|
| `extrude` | Extrude the active sketch's closed profile(s) — all closed regions, inner loops become holes. | `distance`, `operation`, `direction`, `through_all`, `taper`, `sketch_index` |
| `revolve` | Revolve the active sketch's profile about an axis. | `axis`, `angle`, `operation`, `sketch_index` |
| `hole` | Drilled, tapped, counterbored or countersunk hole(s), placed by model coordinates. | `x`, `y`, `diameter`, `depth`, `points`, `face_index`, `axis`, `tap`, `tap_class`, `cbore_diameter`, `cbore_depth`, `csink_diameter`, `csink_angle`, `use_sketch_points` |
| `hole_linear` | Hole on a planar face positioned by distances from two of its edges (Inventor's linear placement). | `face_index`*, `edge_one`*, `distance_one`*, `edge_two`*, `distance_two`*, `diameter`, `depth`, `tap` |
| `fillet` | Constant-radius fillet on edges (1-based indices from list_edges / find_edge). | `radius`*, `edges`* |
| `chamfer` | Chamfer edges: equal distance, two distances, or distance + angle (needs face_index for the reference face of the last two forms). | `distance`*, `edges`*, `distance_two`, `angle`, `face_index` |
| `circular_pattern` | Circular pattern of features (names or 1-based indices) about an axis (X/Y/Z or work axis name). | `features`*, `count`, `angle`, `axis` |
| `rectangular_pattern` | Rectangular (grid) pattern of features along two axes; spacing in mm (negative flips the direction). | `features`*, `x_count`, `x_spacing`, `y_count`, `y_spacing`, `x_axis`, `y_axis` |
| `mirror` | Mirror features (names / indices) across a plane (XY, XZ, YZ or work plane name). | `features`*, `plane` |
| `shell` | Hollow the body to a wall thickness, leaving the listed faces open. | `thickness`*, `remove_faces`, `direction` |
| `thread` | Cosmetic (modelled-as-annotation) ISO metric thread on a cylindrical face — shows on drawings and in the BOM without heavy helical geometry. | `face_index`*, `designation`, `internal`, `thread_class`, `length` |
| `sweep` | Sweep a closed profile (sketch index) along a path (first curve chain of another sketch). | `profile_sketch`*, `path_sketch`*, `operation` |
| `loft` | Loft through the closed profiles of two or more sketches (1-based indices, in order). | `sketches`*, `operation` |
| `work_plane` | Work plane offset from a base plane (mm), or rotated about an axis by an angle (degrees). | `base`, `offset`, `angle`, `axis`, `name` |
| `work_axis` | Work axis through a cylindrical face's axis or along a straight edge (for patterns/revolves). | `face_index`, `edge_index`, `name` |
| `list_features` | Feature tree: index, name, type, suppressed, health. |  |
| `delete_feature` | Delete features by name or 1-based index (dependent features go too). | `features`*, `keep_sketches` |
| `suppress_feature` | Suppress (or unsuppress) a feature without deleting it — handy for what-if checks. | `feature`*, `suppress` |
| `coil` | Coil / spring: sweep the active sketch's closed profile helically about an axis. | `pitch`*, `revolutions`*, `axis`, `operation`, `clockwise`, `sketch_index` |
| `combine_bodies` | Boolean between solid bodies of a multi-body part. operation: join / cut / intersect. | `base`, `tools`, `operation`, `keep_tools` |
| `split_part` | Cut the part with a plane (XY/XZ/YZ or work plane name), removing one side, or split it into two bodies. | `plane`, `remove`, `keep_both` |
| `thicken_face` | Thicken or offset faces by a distance (mm). operation join adds material, cut removes it. | `faces`*, `distance`*, `operation`, `direction` |
| `face_draft` | Mould draft on faces by an angle (degrees) relative to a pull direction normal to a plane (fixed at that plane). | `faces`*, `angle`*, `pull_plane` |
| `emboss_text` | Engrave (or emboss) text into a planar face. With face_index the text is centred on the face and (x, y) are offsets from that centre in mm; without it (x, y) are coordinates in the active sketch. height is the text height. | `text`*, `x`, `y`, `depth`, `engrave`, `height`, `face_index` |
| `frame_members` | A welded box-section frame in one step, from member centre lines in the XY plane: every member becomes a width x height bar, all joined into one solid; wall > 0 then hollows it into tube of that wall thickness (do this before adding pads and brackets, which should stay solid). Returns a cut list: each member's centre-line length, its end angles (between the cut face and the member's axis: 90 = square cut, 45 = mitred corner) and the stock length to cut. | `members`*, `width`, `height`, `wall`, `z`, `name` |
| `tube_frame` | A welded round-tube (CHS) frame in 3D, in one step: each member is a straight tube on a centre line [x1, y1, z1, x2, y2, z2] (mm). All members are swept solid and joined, then bored to the wall thickness, so joints are welded and tee'd tubes are coped into their neighbours. Ends that meet another member's end (corners) run on by half a diameter so the corner closes. Use real sizes (e.g. AS/NZS 1163 CHS 33.7x2.6, 26.9x2.3). Returns a cut list (length between node centres, end conditions) and the total tube length/mass basis. | `members`*, `od`, `wall`, `name` |
| `parametric_extrusion` | A closed profile whose every corner is driven by parameter expressions, extruded to a parametric width. The sketch comes out fully constrained, so changing a parameter (or a linked master) reshapes the part reliably. | `plane`*, `vertices`*, `width`*, `name`, `operation`, `symmetric` |
| `split_faces` | Split faces along sketch lines, without changing the solid: for example to load only a patch of a face in an analysis. The sketch doesn't have to be on the face. | `sketch`, `faces` |

## Inspect

| Tool | What it does | Arguments |
|---|---|---|
| `inspect` | Part summary: volume, surface area, bounding box, face/edge counts, features, mass, material. |  |
| `list_faces` | Face table: index, type (plane/cylinder/...), area, centroid, outward normal or diameter/axis, and hole=true for concave cylinders. Indices are what fillet/shell/hole/FEA tools take. | `min_area`, `type`, `max_count` |
| `list_edges` | Edge table: index, type (line/circle/arc...), length, midpoint, diameter/centre for circles. | `min_length`, `type`, `max_count` |
| `find_edge` | Edge(s) whose midpoint is nearest (x, y, z) mm — omitted coordinates are ignored. Returns the best match plus any others within tolerance. | `x`, `y`, `z`, `type`, `tolerance` |
| `find_face` | Face nearest a point (centroid distance) and/or best aligned with an outward normal. | `x`, `y`, `z`, `normal`, `type`, `min_area` |
| `mass_properties` | Mass, volume, area, centre of gravity and inertia (about the CoG-aligned global axes and principal) of the active part or assembly, using its assigned material(s). |  |
| `measure` | Minimum distance (and angle between planar faces) for two faces, two edges, or a face and an edge. | `face_one`, `face_two`, `edge_one`, `edge_two` |
| `face_at_point` | The face a point (mm) lies on — for references picked in a viewer. Unlike find_face (nearest face centre) this checks the surface itself, and says when the point is on an edge shared by two faces. | `x`*, `y`*, `z`*, `tolerance` |
| `name_face` | Give a face a name that stays with it when indices change (the same names as Inventor's Assign Name). | `face`*, `name`* |
| `find_named_face` | Current face index (for list_faces and the analysis tools) of a named face. | `name`* |
| `list_named_faces` | Every named face of the part and its current index. |  |

## Parameters

| Tool | What it does | Arguments |
|---|---|---|
| `get_parameters` | Model (dimension) and user parameters with expressions and values (lengths in mm, angles in deg). | `user_only` |
| `set_parameter` | Set a parameter's expression (e.g. "40 mm", "d0 * 2", "Thickness + 2") and rebuild. | `name`*, `expression`* |
| `add_parameter` | Add a user parameter (units: mm, deg, ul for unitless, kg, N, MPa...). | `name`*, `expression`*, `units`, `comment` |
| `list_dimensions` | Driving sketch dimensions (all sketches, or one) with the parameter that controls each. | `sketch_index` |
| `edit_dimension` | Change a dimension by its parameter name (d0, d1 ... from list_dimensions) and rebuild. | `parameter`*, `value`* |
| `link_parameters` | Link user parameters from another Inventor file (a master part) into this part or assembly, so one file drives them all. Linking the same file again adds any new names to the existing link. | `source`*, `names` |
| `list_model_states` | Model states of the active part or assembly (variants of one file, e.g. with different features suppressed). |  |
| `add_model_state` | Add a model state. While it is active, suppressing features or changing parameters only affects that state. | `name`*, `activate` |
| `activate_model_state` | Switch the active part or assembly to a model state. | `name`* |

## Properties

| Tool | What it does | Arguments |
|---|---|---|
| `get_iproperties` | Common iProperties (part number, description, designer, revision...) and custom properties. |  |
| `set_iproperties` | Set iProperties: keys like part_number, description, title, author, designer, revision, project, company, checked_by, vendor, stock_number — anything else becomes a custom property. Drawing title blocks read these. | `properties`* |

## Materials

| Tool | What it does | Arguments |
|---|---|---|
| `list_materials` | Material names available in the active material library (filter is a case-insensitive substring). | `filter` |
| `set_material` | Assign a material from the library by name (exact or unique partial match, e.g. "Steel, Mild", "Aluminum 6061"). Returns its mechanical properties. | `name`* |
| `material_properties` | Young's modulus (MPa), Poisson's ratio, density (kg/m³), yield and ultimate strength (MPa) of the part's material. |  |
| `create_material` | Make a named material in the active part from a library one, with your own strengths, and assign it — for grades the library lacks, e.g. name="AS/NZS 1163 C250L0", yield_MPa=250, ultimate_MPa=320. Stress Analysis uses these values, so the safety factor is against the right yield. | `name`*, `base`, `yield_MPa`, `ultimate_MPa`, `E_MPa`, `poisson`, `density_kg_m3` |
| `set_appearance` | Give the active part a library appearance (colour/finish only; mass and stress use the material), by exact or partial name, e.g. "Rubber - Black", "Powder Coat - Red", "Chrome - Polished". | `name`* |

## Sheet Metal

| Tool | What it does | Arguments |
|---|---|---|
| `set_sheet_metal_thickness` | Sheet thickness (mm) and optionally the default bend radius (mm) for this part. | `thickness`*, `bend_radius` |
| `sheet_metal_face` | Sheet-metal face (a plate of the sheet thickness) from the active sketch's closed profile. | `sketch_index` |
| `flange` | Bend a flange up from one or more model edges (indices from list_edges / find_edge, pick the outer edges of the face). | `edges`*, `height`, `angle`, `flip` |
| `sheet_metal_cut` | Cut the active sketch's profile through the sheet (normal to the face it is sketched on). | `sketch_index` |
| `flat_pattern` | Unfold to the flat pattern, report its blank size and bend count, optionally write a DXF of the flat pattern for laser/plasma cutting, then return to the folded model. | `dxf_path` |

## Assembly

| Tool | What it does | Arguments |
|---|---|---|
| `place_component` | Place a part/assembly file (or an open document by name) into the active assembly at (x, y, z) mm, optionally rotated about X/Y/Z by rotate_angle degrees. The first component is usually grounded. | `path`*, `x`, `y`, `z`, `rotate_axis`, `rotate_angle`, `grounded` |
| `add_constraint` | Assembly constraint between two components (or a component and the assembly origin). | `type`*, `occurrence_one`*, `entity_one`*, `occurrence_two`*, `entity_two`*, `offset`, `angle`, `opposed`, `offset_expression` |
| `ground_component` | Ground (fix in place) or unground a component. | `occurrence`*, `grounded` |
| `move_component` | Move a (non-grounded, unconstrained) component's origin to (x, y, z) mm. | `occurrence`*, `x`*, `y`*, `z`* |
| `inspect_assembly` | Components (position, grounded, mass), constraints (type, health), total mass; with faces_of, the face table of that component in assembly coordinates (for picking constraint faces). | `faces_of` |
| `check_interference` | Interference check across all components: which pairs overlap and by how much volume. |  |
| `check_assembly` | One-call health check of an assembly: interferences, constraint health, overall size, mass, ungrounded components with no constraints. |  |
| `component_gap` | Smallest distance between two components, in mm (0 when they touch or overlap). | `occurrence_one`*, `occurrence_two`* |
| `bill_of_materials` | Parts-only BOM: item, quantity, part number, description, material, mass; optional CSV export. | `csv_path` |
| `pattern_component` | Circular (angle = degrees between copies) or linear (linear=true, spacing in mm) pattern of components along an assembly origin axis X/Y/Z. | `occurrences`*, `axis`, `count`, `angle`, `linear`, `spacing` |
| `set_component_model_state` | Show a component in the assembly in one of its model states. | `occurrence`*, `state`* |

## Drawing

| Tool | What it does | Arguments |
|---|---|---|
| `create_drawing` | New drawing document (ISO template; AS1100 = third-angle projection, ISO = first-angle). | `standard`, `sheet_size`, `orientation`, `name` |
| `add_sheet` | Add a sheet to the drawing (with the template's border and title block) and make it active. | `sheet_size`, `orientation`, `name` |
| `activate_sheet` | Activate a sheet by name or 1-based index. | `sheet`* |
| `add_base_view` | Base view of a part/assembly (file path or open document name) centred at (x, y) sheet mm. | `model`, `x`, `y`, `scale`, `orientation`, `style`, `name` |
| `add_projected_view` | Projected view from a parent view, placed at (x, y) sheet mm. Above/below/left/right gives the orthographic views (per the drawing's projection angle); a diagonal position gives an isometric. | `parent`*, `x`*, `y`*, `style`, `name` |
| `add_section_view` | Full section through a parent view along a straight cutting line, placed at (x, y) sheet mm. | `parent`*, `x`*, `y`*, `cut`, `offset`, `label` |
| `add_detail_view` | Circular detail (enlarged) view of part of a parent view. center/radius are sheet mm on the parent. | `parent`*, `center_x`*, `center_y`*, `radius`*, `x`*, `y`*, `scale`, `label` |
| `move_view` | Move a view's centre to (x, y) sheet mm (projected children follow alignment). | `view`*, `x`*, `y`* |
| `set_view_scale` | Change a base view's scale (dependent views follow). | `view`*, `scale`* |
| `list_views` | Views on the active sheet: name, scale, centre, box, size, type. |  |
| `add_linear_dimension` | Dimension a model edge's length (one edge) or the distance between two edges, in a view. Edge indices are the part's list_edges indices. (x, y) sheet mm for the text; 0,0 = auto. | `view`*, `edge_one`*, `edge_two`, `x`, `y`, `direction`, `occurrence` |
| `add_diameter_dimension` | Diameter dimension on a circular edge (list_edges type circle) in a view. | `view`*, `edge`*, `x`, `y`, `occurrence` |
| `auto_dimension_view` | Retrieve the model's own (sketch + feature) dimensions into a view — the fastest way to a fully-dimensioned view — and optionally arrange them clear of the geometry. | `view`*, `arrange` |
| `add_centermarks` | Centre marks on every circular edge in a view (or all views on the sheet). | `view` |
| `add_hole_note` | Hole/thread note (Ø, depth, thread, counterbore...) on a hole's circular edge in a view. | `view`*, `edge`*, `x`, `y` |
| `add_general_notes` | Free text note at (x, y) sheet mm (use \n for new lines, e.g. "NOTES:\n1. DEBURR ALL EDGES"). | `text`*, `x`, `y` |
| `add_parts_list` | Parts list (BOM table) for an assembly view; default position above the title block. | `view`, `x`, `y` |
| `auto_balloon` | Balloon every component visible in an assembly view, placed outside the view and linked to the parts list numbering. | `view` |
| `set_title_block_field` | Fill title-block fields: title, drawing_number, drawn_by, checked_by, approved_by, revision, description, company, material, project. Writes the drawing's iProperties (which the title block shows) and any prompted entries with a matching name. | `fields`* |
| `place_view_labels` | Show a label (name + scale) under every view; names views FRONT/TOP/RIGHT/ISO... from their orientation when they still have default names. |  |
| `add_projection_symbol` | Put the projection-angle symbol on the sheet (a truncated cone and two circles, as AS 1100 and ISO call for). | `x`, `y`, `third_angle` |
| `set_view_component_visibility` | Show or hide one component in a view, e.g. a large reference part that forces a small scale. | `view`*, `occurrence`*, `visible` |
| `make_part_sheet` | One-shot detail drawing of a part: new drawing, FRONT + projected TOP/RIGHT laid out for the projection angle and clear of the title block, a shaded ISOMETRIC, retrieved model dimensions, hole position dimensions, centre marks, view labels, title block — then QA. Always render_sheet and look, and fix what check_drawing reports. | `model`, `views`, `scale`, `sheet_size`, `standard`, `dimensions`, `title`, `drawing_number`, `drawn_by`, `material` |
| `make_assembly_sheet` | One-shot general-arrangement (GA) drawing of an assembly: FRONT + TOP, shaded ISOMETRIC, parts list above the title block, balloons, labels, title block, QA. | `model`, `scale`, `sheet_size`, `standard`, `title`, `drawing_number`, `drawn_by` |
| `list_drawing_dimensions` | Dimensions on the active sheet: index (for the tools below), value, text, tolerance and text position. |  |
| `set_dimension_tolerance` | Tolerance a drawing dimension: symmetric (±), deviation (upper/lower, mm) or an ISO fit such as hole_fit="H7" (a hole), shaft_fit="g6" (a shaft), or both for a fit. | `index`*, `upper`, `lower`, `symmetric`, `hole_fit`, `shaft_fit` |
| `move_dimension_text` | Move a dimension's text to (x, y) sheet mm. | `index`*, `x`*, `y`* |
| `delete_drawing_dimension` | Delete a drawing dimension by index (see list_drawing_dimensions). | `index`* |
| `add_surface_finish` | Surface texture symbol (machining required) on a model edge in a view; roughness is Ra in µm. | `view`*, `edge`*, `roughness`, `x`, `y`, `occurrence` |
| `add_hole_table` | Hole table for every hole in a view, positioned with its top-left at (x, y) sheet mm (default above the title block). Needs a datum in the view; the table is returned as text rows. | `view`*, `x`, `y` |
| `add_revision_table` | Revision table on the active sheet; default placement is above the title block. | `x`, `y` |
| `check_drawing` | QA of every sheet: views overlapping each other / the title block / the sheet edge, views with no dimensions, empty title-block fields, missing parts list or balloons on assemblies. Ends with TOTAL ISSUES: N — aim for 0, then render_sheet and look. |  |
| `render_sheet` | PNG of the active sheet (look at it before exporting). | `path`, `width` |
| `export_pdf` | Export the drawing (all sheets by default) to PDF, vector, black lines. | `path`*, `all_sheets` |

## Analysis

| Tool | What it does | Arguments |
|---|---|---|
| `analyze_stress` | Static stress analysis in Inventor's own Stress Analysis environment. TAKES OVER THE MOUSE AND KEYBOARD for the duration (faces are picked in the viewport; Inventor must be visible and nobody should touch the mouse). Creates a study, fixes the faces, applies the loads, simulates, and reads Inventor's stress report: max von Mises and principal stresses, max displacement, min safety factor, reactions (equilibrium check against the applied loads), plus a picture of the stress plot. | `fixed_faces`, `loads`, `gravity`, `mesh_fraction`, `name`, `user_notified`, `frictionless_faces`, `pin_faces`, `study_name`, `contact_type`, `contacts`, `local_mesh`, `refinements`, `convergence_percent`, `model_state` |
| `analyze_modes` | Natural frequencies with Inventor's Stress Analysis (modal study). TAKES OVER THE MOUSE AND KEYBOARD while it runs (faces are picked in the viewport). Returns the frequencies from Inventor's report. Needs user_notified=true (see analyze_stress). | `fixed_faces`*, `modes`, `name`, `user_notified`, `study_name` |
| `exit_analysis` | Leave Inventor's Stress Analysis environment and return to modelling. |  |
| `read_stress_report` | Parse an Inventor Stress Analysis HTML report (results summary, reactions, loads, material). | `path`* |
| `list_studies` | The Stress Analysis studies in this document and what each holds: constraints, loads, contacts, results. |  |
| `set_contact_type` | Change the type of the automatic contacts between components, e.g. Separation for parts that may lift apart (compression only, so the solve becomes nonlinear and slower). No mouse needed. | `study`*, `between`*, `type`* |
| `activate_study` | Make a study the active one (later solve and result commands act on it). | `study`* |
| `rename_study` | Rename a Stress Analysis study. | `study`*, `new_name`* |
| `copy_study` | Copy a study, keeping its faces, supports and loads, so no faces need picking. Returns the copy's own load parameters, in the same order as the original's values (set them with set_analysis_parameters). | `source`*, `new_name` |
| `list_analysis_parameters` | Every Stress Analysis load value in this document: the sa_N parameters, in creation order (forces in N as X, Y, Z triples; gravity in mm/s^2). |  |
| `set_analysis_parameters` | Change Stress Analysis load values directly, with no dialog. The affected study needs solving again. | `values`* |
| `read_result_maximum` | Peak value of a solved study's result, without generating a report (seconds, against minutes for a file with many studies). Gives peaks only; use study_report for reactions and full results. | `study`*, `result` |
| `show_result` | Show a solved study's result in Inventor and save a picture of it. | `study`*, `result`, `view` |
| `set_result_colors` | Change how Inventor colours a solved study's result: a fixed scale (say, ending at yield so anything red is over it), greyscale, or back to automatic. No mouse needed. Returns a picture. A manual maximum stops read_result_maximum reading the true peak until auto is set again. | `study`*, `result`, `maximum`, `minimum`, `gray`, `auto`, `view` |
| `result_at_point` | A solved result's value at one spot — the middle of a face, or a point on it — for example the stress a short way from a sharp corner whose peak is a singularity. Inventor has no API for this, so the value is read off the screen: the colour scale's top is moved until that spot just reaches the top colour. Inventor comes to the front and the pointer is moved out of the way, so this needs user_notified=true like the analyses. | `study`*, `face`*, `result`, `point`, `tolerance`, `user_notified` |
| `mesh_convergence` | Check that a study's peak doesn't depend on the mesh: copies it at finer average element sizes, solves each and compares the peaks. No mouse needed. (analyze_stress's refinements= uses Inventor's own refinement instead.) | `study`*, `fractions`, `result`, `timeout` |
| `refresh_analysis_display` | Clear arrows and labels left on screen from other studies by leaving Stress Analysis and coming back. Save first: switching environments repeatedly has been linked to an Inventor crash. |  |
| `solve_study` | Solve an existing study, with no mouse or keyboard use. Don't use Inventor until it returns; solver warnings are returned. | `study`*, `timeout` |
| `study_report` | Generate Inventor's report and read one study from it: summary, reactions (the way to get reactions; Inventor's Reaction Forces dialog crashes it), loads, material. A full report covers every study, which takes many minutes on a file with several and has crashed Inventor on very large ones. | `study`, `name`, `only_this_study`, `user_notified` |
| `run_study_cases` | Run a table of load cases from one template study, with no mouse or keyboard. Each case copies the template, writes its load values, solves, reads the peaks and saves the file. Finished cases are recorded, so after a crash the same call carries on where it stopped; in a private Inventor (connect(private=true)) a crashed Inventor is restarted and the run continues by itself. Save the document first, and keep runs short: long Inventor sessions are the usual cause of crashes. | `template`*, `cases`*, `results_path`, `results`, `timeout` |
| `delete_study_item` | Delete a whole study, or one constraint or load inside it. This can't be undone. To move a load to other faces, delete it and add it again: picking in an edit dialog adds faces. | `study`*, `item` |
| `solve_state` | What every running Inventor is doing, read from Windows only (window titles, CPU, memory), so it is safe during a solve and while another session is using Inventor. Call it twice a few seconds apart: rising CPU means still working. |  |

## System

| Tool | What it does | Arguments |
|---|---|---|
| `execute_python` | Run Python in a persistent namespace with the live Inventor objects: app, doc, cdef (component definition or None), tg (TransientGeometry), to (TransientObjects), K (all Inventor enum constants), items(collection), typed_call(obj, method, ...) for [out]-parameter methods, MM (=0.1, mm->cm). Inventor API units are cm and radians. The value of a final expression is returned; print() output too. Use it for anything the dedicated tools don't cover. | `code`* |
| `reload_api` | Reload the tool modules from disk (after editing them) without restarting the server. |  |
| `list_tools` | Tool names by group (session, documents, sketch, features, inspect, parameters, materials, properties, sheet_metal, assembly, drawing, analysis, view, system). | `group` |
| `read_pdf_text` | Text of a PDF (datasheets, standards, drawings from others) using only Python's standard library. Works for most PDFs written with simple fonts; scanned pages and some embedded fonts give little or no text. | `path`*, `max_chars` |

## Parts

| Tool | What it does | Arguments |
|---|---|---|
| `create_standard_part` | Model a standard metric part in a new document, with part number and description filled in: hex_bolt (ISO 4017), socket_screw (ISO 4762), hex_nut (ISO 4032), washer (ISO 7089, form A) or dowel (ISO 2338, nominal diameter). Threads are cosmetic. The head's underside (or the part's base) is on the XY plane, shanks point down -Z. | `kind`*, `size`*, `length`, `material`, `save_path` |

`*` = required.
