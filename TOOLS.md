# inventor-forge tools

104 tools. Lengths mm, angles degrees, forces N, stresses MPa.

## Session

| Tool | What it does | Arguments |
|---|---|---|
| `connect` | Attach to the running Inventor (or start it) and report the version and open documents. |  |
| `status` | Active document summary (type, path, feature/sketch/body counts, volume, material). |  |
| `list_documents` | Every open (visible) document, with the active one marked. |  |
| `transaction` | Group several operations into one undo step: begin, commit, or abort (rolls everything back). | `action`, `name` |
| `undo` | Undo the last N operations in the active document. | `steps` |

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

## Parameters

| Tool | What it does | Arguments |
|---|---|---|
| `get_parameters` | Model (dimension) and user parameters with expressions and values (lengths in mm, angles in deg). | `user_only` |
| `set_parameter` | Set a parameter's expression (e.g. "40 mm", "d0 * 2", "Thickness + 2") and rebuild. | `name`*, `expression`* |
| `add_parameter` | Add a user parameter (units: mm, deg, ul for unitless, kg, N, MPa...). | `name`*, `expression`*, `units`, `comment` |
| `list_dimensions` | Driving sketch dimensions (all sketches, or one) with the parameter that controls each. | `sketch_index` |
| `edit_dimension` | Change a dimension by its parameter name (d0, d1 ... from list_dimensions) and rebuild. | `parameter`*, `value`* |

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
| `add_constraint` | Assembly constraint between two components (or a component and the assembly origin). | `type`*, `occurrence_one`*, `entity_one`*, `occurrence_two`*, `entity_two`*, `offset`, `angle`, `opposed` |
| `ground_component` | Ground (fix in place) or unground a component. | `occurrence`*, `grounded` |
| `move_component` | Move a (non-grounded, unconstrained) component's origin to (x, y, z) mm. | `occurrence`*, `x`*, `y`*, `z`* |
| `inspect_assembly` | Components (position, grounded, mass), constraints (type, health), total mass; with faces_of, the face table of that component in assembly coordinates (for picking constraint faces). | `faces_of` |
| `check_interference` | Interference check across all components: which pairs overlap and by how much volume. |  |
| `bill_of_materials` | Parts-only BOM: item, quantity, part number, description, material, mass; optional CSV export. | `csv_path` |

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
| `make_part_sheet` | One-shot detail drawing of a part: new drawing, FRONT + projected TOP/RIGHT laid out for the projection angle and clear of the title block, a shaded ISOMETRIC, retrieved model dimensions, hole position dimensions, centre marks, view labels, title block — then QA. Always render_sheet and look, and fix what check_drawing reports. | `model`, `views`, `scale`, `sheet_size`, `standard`, `dimensions`, `title`, `drawing_number`, `drawn_by`, `material` |
| `make_assembly_sheet` | One-shot general-arrangement (GA) drawing of an assembly: FRONT + TOP, shaded ISOMETRIC, parts list above the title block, balloons, labels, title block, QA. | `model`, `scale`, `sheet_size`, `standard`, `title`, `drawing_number`, `drawn_by` |
| `check_drawing` | QA of every sheet: views overlapping each other / the title block / the sheet edge, views with no dimensions, empty title-block fields, missing parts list or balloons on assemblies. Ends with TOTAL ISSUES: N — aim for 0, then render_sheet and look. |  |
| `render_sheet` | PNG of the active sheet (look at it before exporting). | `path`, `width` |
| `export_pdf` | Export the drawing (all sheets by default) to PDF, vector, black lines. | `path`*, `all_sheets` |

## Analysis

| Tool | What it does | Arguments |
|---|---|---|
| `analyze_stress` | Static stress analysis in Inventor's own Stress Analysis environment. TAKES OVER THE MOUSE AND KEYBOARD for the duration (faces are picked in the viewport; Inventor must be visible and nobody should touch the mouse). Creates a study, fixes the faces, applies the loads, simulates, and reads Inventor's stress report: max von Mises and principal stresses, max displacement, min safety factor, reactions (equilibrium check against the applied loads), plus a picture of the stress plot. | `fixed_faces`*, `loads`, `gravity`, `mesh_fraction`, `name`, `user_notified` |
| `analyze_modes` | Natural frequencies with Inventor's Stress Analysis (modal study). TAKES OVER THE MOUSE AND KEYBOARD while it runs (faces are picked in the viewport). Returns the frequencies from Inventor's report. Needs user_notified=true (see analyze_stress). | `fixed_faces`*, `modes`, `name`, `user_notified` |
| `exit_analysis` | Leave Inventor's Stress Analysis environment and return to modelling. |  |
| `read_stress_report` | Parse an Inventor Stress Analysis HTML report (results summary, reactions, loads, material). | `path`* |

## System

| Tool | What it does | Arguments |
|---|---|---|
| `execute_python` | Run Python in a persistent namespace with the live Inventor objects: app, doc, cdef (component definition or None), tg (TransientGeometry), to (TransientObjects), K (all Inventor enum constants), items(collection), typed_call(obj, method, ...) for [out]-parameter methods, MM (=0.1, mm->cm). Inventor API units are cm and radians. The value of a final expression is returned; print() output too. Use it for anything the dedicated tools don't cover. | `code`* |
| `reload_api` | Reload the tool modules from disk (after editing them) without restarting the server. |  |
| `list_tools` | Tool names by group (session, documents, sketch, features, inspect, parameters, materials, properties, sheet_metal, assembly, drawing, analysis, view, system). | `group` |

`*` = required.
