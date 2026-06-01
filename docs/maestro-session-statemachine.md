# Maestro Session State Machine

How `virtuoso_bridge/virtuoso/maestro/lifecycle.py` drives a maestro view.
Everything below is built on one channel: `client.execute_skill("<SKILL>")`.

## `open_gui_session(lib, cell)` — get an editable GUI session ready to simulate

```mermaid
flowchart TD
    A["open_gui_session(lib, cell)"] --> B["_close_background_sessions()<br/>maeGetSessions() − GUI sessions<br/>→ maeCloseSession(forceClose) each"]
    B --> C["windows = _get_session_windows()<br/>(parse hiGetWindowList titles)"]
    C --> D{for each window w}
    D -->|"is_target AND mode == editing"| E["REUSE → return w.session"]
    D -->|"other cell, OR target in reading mode"| F["close_gui_session(w,<br/>save = mode==editing)"]
    F --> D
    D -->|no more windows| G["deOpenCellView(lib, cell,<br/>'maestro','maestro', nil, 'a')<br/>timeout=60s"]
    G --> H{error / nil output?}
    H -->|yes| X1["raise RuntimeError<br/>(no maestro view / open failed)"]
    H -->|no| I["session = _find_session_for_cell(lib,cell)<br/>(match by window title)"]
    I --> J{found?}
    J -->|no| X2["raise RuntimeError<br/>(no ADE window appeared)"]
    J -->|yes| K["return session (e.g. 'fnxSession3')"]

    classDef ok fill:#1f6f3f,stroke:#0d3,color:#fff;
    classDef err fill:#7a1f1f,stroke:#d33,color:#fff;
    class E,K ok;
    class X1,X2 err;
```

## `close_gui_session(session, save)` — close safely without hanging the SKILL channel

```mermaid
flowchart TD
    A["close_gui_session(session, save)"] --> B{"GUI window<br/>for session?"}
    B -->|no| B1["maeCloseSession(forceClose) · return"]
    B -->|yes| C{"modified (*) AND save?"}
    C -->|no| G
    C -->|yes, mode==editing| D["maeSaveSetup(session)"]
    C -->|yes, mode==reading| E{"another Editing<br/>session holds lock?"}
    E -->|no| F["maeMakeEditable()"]
    F --> F1{ok?}
    F1 -->|yes| F2["maeSaveSetup(session)"]
    F1 -->|no| F3["discard changes"]
    E -->|yes| F3
    D --> G
    F2 --> G
    F3 --> G

    G["_close_gui_window()"] --> H{"window modified?"}
    H -->|yes| H1["start daemon thread:<br/>sleep 0.5s → X11 Alt+N (Don't Save)<br/>pre-empts the blocking save dialog"]
    H -->|no| I
    H1 --> I["execute_skill: hiCloseWindow(w)"]
    I --> J["_purge_maestro_cellviews()<br/>dbPurge → release edit lock<br/>(avoids ASSEMBLER-8127)"]
    J --> K["closed"]

    classDef bypass fill:#7a5a00,stroke:#fb0,color:#fff;
    class H1 bypass;
```

## Why each step exists

| Step | SKILL | Reason |
|---|---|---|
| close background first | `maeCloseSession ?forceClose t` | background/zombie sessions hold lock files (ASSEMBLER-8051) |
| reuse editing window | title contains `Editing:` | avoid reopening / double lock |
| open via `deOpenCellView(... "a")` | not `maeOpenSetup` | `maeOpenSetup` makes a 2nd background session → 8127 on next open |
| find by title, not `maeGetSetup` | `_find_session_for_cell` | a fresh/empty view has no tests, invisible to `maeGetSetup` |
| X11 Alt+N before `hiCloseWindow` | XTest fake key | save dialog blocks the single-threaded SKILL channel |
| `dbPurge` after close | `dbPurge(cv)` | cellview stays cached with edit lock; purge frees it |
