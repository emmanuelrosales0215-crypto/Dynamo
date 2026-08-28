# Best Civil 3D Repositories on GitHub

A curated shortlist of the most useful open-source repositories for AutoCAD Civil 3D
development and automation. Ordered by category, with the strongest picks first.
Star counts and activity are as of August 2026.

---

## 1. Dynamo for Civil 3D

The most relevant category if you are building Dynamo graphs or custom Dynamo packages.

| Repo | Stars | Language | Why it matters |
|---|---|---|---|
| [Autodesk/civilconnection](https://github.com/Autodesk/civilconnection) | 117 | C# | **Official Autodesk.** The reference implementation for moving data between Civil 3D, Dynamo, and Revit. The single best source for how Civil 3D objects (alignments, profiles, corridors, featurelines) are wrapped as Dynamo nodes. Still actively maintained. |
| [mzjensen/Camber](https://github.com/mzjensen/Camber) | 53 | C# | The best-regarded community Dynamo package for Civil 3D. Broad node coverage well beyond the out-of-the-box nodes, cleanly structured ZeroTouch code. Read this if you're writing your own package. |
| [paoloemilioserra/Civil3dToolkit](https://github.com/paoloemilioserra/Civil3dToolkit) | 33 | — | Crowd-sourced Civil 3D Toolkit companion repo. Good for issue-driven node requests and community conventions; the code itself lives in the package. |
| [GeorgGrebenyuk/Civil3D.CustomNodes](https://github.com/GeorgGrebenyuk/Civil3D.CustomNodes) | small | C# | Minimal, readable example of a .NET Dynamo package sitting directly on the AutoCAD + Civil 3D APIs (Civil 3D 2022.1+). Useful as a starting skeleton. |
| [DynamoDS/DynamoPrimerNew](https://github.com/DynamoDS/DynamoPrimerNew) | 19 | — | The official Dynamo Primer (v2, Dynamo 2.13+). Not Civil 3D specific, but the canonical learning material. |

---

## 2. API exploration and debugging

Indispensable when you need to find out what a Civil 3D object actually exposes.

| Repo | Stars | Language | Why it matters |
|---|---|---|---|
| [ADN-DevTech/Civil3DSnoop](https://github.com/ADN-DevTech/Civil3DSnoop) | 70 | VB.NET | **Official Autodesk ADN.** Interactive inspector for the Civil 3D database — pick an object, walk its properties. The fastest way to learn the API. Default branch has been updated to .NET 8. |
| [chuongmep/CadPythonShell](https://github.com/chuongmep/CadPythonShell) | 119 | C# | IronPython console inside AutoCAD/Civil 3D with a full snoop database. Live REPL against the running drawing — the quickest way to prototype API calls before writing C#. |
| [ADN-DevTech/MgdDbg](https://github.com/ADN-DevTech/MgdDbg) | 164 | C# | The classic AutoCAD DWG database inspector. Broader (plain AutoCAD) than Civil3DSnoop but more mature; pair the two. |
| [chuongmep/CadAddinManager](https://github.com/chuongmep/CadAddinManager) | 126 | C# | Hot-reload .NET assemblies without restarting AutoCAD/Civil 3D. Enormous quality-of-life win for the edit-build-test loop. |
| [htlcnn/AutoCADLookup](https://github.com/htlcnn/AutoCADLookup) | 25 | C# | Lightweight C# object snooping for AutoCAD. |

---

## 3. Plugin scaffolding and .NET templates

| Repo | Stars | Language | Why it matters |
|---|---|---|---|
| [ADN-DevTech/CivilClassLibTemplate](https://github.com/ADN-DevTech/CivilClassLibTemplate) | 12 | C# | **Official.** .NET (Core) project template for Civil 3D 2025+ add-ins. Start here for any new plugin on a modern Civil 3D. |
| [ADN-DevTech/AutoCAD-Net-Wizards](https://github.com/ADN-DevTech/AutoCAD-Net-Wizards) | 142 | HTML/C# | **Official.** Visual Studio wizards for AutoCAD .NET plugins — still the standard scaffolding for AutoCAD-level add-ins. |
| [ADN-DevTech/ObjectARX-Wizards](https://github.com/ADN-DevTech/ObjectARX-Wizards) | 121 | HTML/C++ | **Official.** Same, for native ObjectARX (C++). Default branch tracks AutoCAD 2026. |
| [ADN-DevTech/AutoCADDotnetTrainingMaterial](https://github.com/ADN-DevTech/AutoCADDotnetTrainingMaterial) | 57 | — | Autodesk's own .NET training labs and exercises. |
| [ADN-DevTech/coreconsolerunner](https://github.com/ADN-DevTech/coreconsolerunner) | 6 | — | NUnit test runner driven by AutoCAD CoreConsole — how you get real automated tests around plugin code. |

---

## 4. Production tool suites (read for patterns, or use directly)

| Repo | Stars | Language | Why it matters |
|---|---|---|---|
| [shtirlitsDva/Autocad-Civil3d-Tools](https://github.com/shtirlitsDva/Autocad-Civil3d-Tools) | 38 | C# | The largest real-world Civil 3D codebase in the open. Utility-network / district-heating oriented, actively developed. Best source of "how do people actually do this" patterns. |
| [shtirlitsDva/Civil-3D-ProfileToolBox](https://github.com/shtirlitsDva/Civil-3D-ProfileToolBox) | 19 | C# | Reverse-engineered profile-from-polyline creation. Valuable for the profile/profile-view API, which is poorly documented. |
| [puppetsw/CivilSurveySuite](https://github.com/puppetsw/CivilSurveySuite) | 6 | C# | Survey toolset with a genuinely clean architecture (separated services, testable). The best-structured small Civil 3D project to imitate. |
| [puppetsw/Civil-3D-Addons](https://github.com/puppetsw/Civil-3D-Addons) | 10 | C# | Assorted small, focused add-ins from the same author. |
| [puppetsw/StringMaster](https://github.com/puppetsw/StringMaster) | 11 | C# | CogoPoint stringing — a good worked example of the COGO point API. |
| [GeorgGrebenyuk/civil3d_2_ifc](https://github.com/GeorgGrebenyuk/civil3d_2_ifc) | small | C# | Civil 3D → IFC export via GeometryGym. Rare open example of infra IFC export. |

---

## 5. Interoperability

| Repo | Stars | Language | Why it matters |
|---|---|---|---|
| [specklesystems/speckle-sharp-connectors](https://github.com/specklesystems/speckle-sharp-connectors) | 65 | C# | Speckle V3 connectors, including the live Civil 3D connector. The current, maintained line. |
| [specklesystems/speckle-sharp](https://github.com/specklesystems/speckle-sharp) | 434 | C# | ⚠️ **Archived**, but still the richest reference for Civil 3D ↔ Revit ↔ Rhino object conversion logic. Read it, don't build on it. |
| [tumcms/IfcInfraToolKit](https://github.com/tumcms/IfcInfraToolKit) | 6 | C# | Academic (TUM) toolkit for IFC infrastructure alignments. |

---

## 6. AutoLISP

Lower ceiling than .NET, but far faster for small in-house commands.

| Repo | Stars | Language | Why it matters |
|---|---|---|---|
| [dtgoitia/civil-autolisp](https://github.com/dtgoitia/civil-autolisp) | 60 | AutoLISP | The most-starred civil-engineering LISP collection. |
| [retrospectivePreposterous/AutoLISP-3DTools](https://github.com/retrospectivePreposterous/AutoLISP-3DTools) | 19 | AutoLISP | 3D modeling helpers for AutoCAD / Civil 3D. |
| [thelegendofbrian/C3D-Utils](https://github.com/thelegendofbrian/C3D-Utils) | 9 | AutoLISP | Civil 3D-specific utilities, including backup tooling. |
| [mf4633/C3D-AutoCAD](https://github.com/mf4633/C3D-AutoCAD) | small | AutoLISP | 26 small, well-documented survey/annotation commands. Good beginner reading. |

---

## 7. AI / MCP integrations (new and moving fast — evaluate before adopting)

| Repo | Stars | Language | Why it matters |
|---|---|---|---|
| [ADN-DevTech/acad-api-skill](https://github.com/ADN-DevTech/acad-api-skill) | 12 | PowerShell | **Official.** Agent skills and rules for scaffolding AutoCAD / Civil 3D / Plant 3D .NET 10 plugins. The credible one in this category. |
| [autodesk-platform-services/skills](https://github.com/autodesk-platform-services/skills) | 41 | — | **Official.** Agent skills for Autodesk Platform Services (APS/Forge). |
| [Sacred-G/Civil3D-mcp](https://github.com/Sacred-G/Civil3D-mcp) | 30 | TypeScript | Largest community Civil 3D MCP server (~180 tools). Unvetted; treat as a prototype. |
| [shtirlitsDva/cad-mcp](https://github.com/shtirlitsDva/cad-mcp) | small | C# | Runs C# inside a live AutoCAD/Civil 3D process via a Roslyn + named-pipe kernel. The most technically interesting approach of the MCP bunch, from a credible author. |
| [barbosaihan/civil3d-mcp](https://github.com/barbosaihan/civil3d-mcp) | 26 | TypeScript | Another Civil 3D MCP server. |

---

## 8. Reference / meta

| Repo | Stars | Why it matters |
|---|---|---|
| [QuantumNovice/awesome-civil-engineering](https://github.com/QuantumNovice/awesome-civil-engineering) | 84 | Broad awesome-list for civil engineering software and libraries. |
| [ganadara135/CorridorRoad](https://github.com/ganadara135/CorridorRoad) | 8 | FreeCAD workbench implementing a Civil 3D-style corridor pipeline (alignment → sections → corridor → cut/fill). Useful if you want to see the algorithms rather than call an API. |

---

## Recommended starting set

If you only clone five:

1. **[Autodesk/civilconnection](https://github.com/Autodesk/civilconnection)** — official Dynamo ↔ Civil 3D reference.
2. **[mzjensen/Camber](https://github.com/mzjensen/Camber)** — best community Dynamo package to learn from.
3. **[ADN-DevTech/Civil3DSnoop](https://github.com/ADN-DevTech/Civil3DSnoop)** — API discovery.
4. **[chuongmep/CadAddinManager](https://github.com/chuongmep/CadAddinManager)** — hot reload, saves hours.
5. **[shtirlitsDva/Autocad-Civil3d-Tools](https://github.com/shtirlitsDva/Autocad-Civil3d-Tools)** — real production patterns.

## A caution on search results

Searching GitHub for "Civil 3D" surfaces a large number of repositories whose topics
are stuffed with terms like `autodesk-civil-3d-crack` or `full-installer`. These are
not software projects — they are bait pointing at pirated or malicious installers.
None are included above.
