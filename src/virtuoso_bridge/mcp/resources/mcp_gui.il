; ============================================================================
; mcp_gui.il — AI Bridge GUI for Cadence Virtuoso
;
; Loads after ramic_bridge.il, reusing its globals:
;   RBPython  — path to the Python interpreter
;   RBIpc     — IPC handle for the RAMIC Bridge daemon
;   RBPort    — TCP port the daemon listens on (default 65432)
;
; Add to ~/.cdsinit:
;   load("/path/to/mcp_gui.il")   ; print path: virtuoso-bridge-mcp init
; ============================================================================

; ============================================================================
; Global state — guarded with boundp so reload() is safe
; ============================================================================
unless(boundp('RBAIIpc)          RBAIIpc          = nil)
unless(boundp('RBAIPort)         RBAIPort         = 8765)
unless(boundp('RBAILogPath)      RBAILogPath      = "/tmp/vb_mcp_log.jsonl")
unless(boundp('RBAILogLine)      RBAILogLine      = 0)
; RBAIProjectRoot must be set in ~/.cdsinit before loading this file.
; It is the directory that contains src/virtuoso_bridge/.
; Example:
;   RBAIProjectRoot = "/home/user/virtuoso-bridge-lite"
;   load(strcat(RBAIProjectRoot "/src/virtuoso_bridge/mcp/resources/mcp_gui.il"))
unless(boundp('RBAIProjectRoot)  RBAIProjectRoot  = "")

; ============================================================================
; IPC callbacks for the MCP Server subprocess
; ============================================================================

procedure(RBAIBridgeOut(ipcId data)
  printf("[AI Bridge stdout ipc=%L] %s\n" ipcId data))

procedure(RBAIBridgeErr(ipcId data)
  printf("[AI Bridge stderr ipc=%L] %s\n" ipcId data))

procedure(RBAIBridgeDone(ipcId data)
  let((exitStatus)
    exitStatus = ipcGetExitStatus(ipcId)
    printf("[AI Bridge ipc=%L] MCP Server exited (status=%L)\n" ipcId exitStatus)
    RBAIIpc = nil))

; ============================================================================
; Start / Stop the Python MCP Server subprocess
; ============================================================================

procedure(RBAIBridgeStart()
  if(RBAIIpc && ipcIsAliveProcess(RBAIIpc) then
    printf("[AI Bridge] MCP Server already running on port %d\n" RBAIPort)
  else
    prog((cmd)
      RBAILogLine = 0
      when(isFile(RBAILogPath) deleteFile(RBAILogPath))
      ; Strip Virtuoso's LD_LIBRARY_PATH / LD_PRELOAD so the system Python
      ; links against its own shared libraries, not Virtuoso's bundled copies.
      ; PYTHONPATH points to <project>/src so no pip install is needed.
      cmd = sprintf(nil
        "/usr/bin/env -u LD_LIBRARY_PATH -u LD_PRELOAD PYTHONPATH=%s/src %s -m virtuoso_bridge.mcp --port %d --log-path %s"
        RBAIProjectRoot RBPython RBAIPort RBAILogPath)
      RBAIIpc = ipcBeginProcess(
        cmd "" 'RBAIBridgeOut 'RBAIBridgeErr 'RBAIBridgeDone "")
      printf("[AI Bridge] MCP Server starting (ipc=%L port=%d log=%s)\n"
        RBAIIpc RBAIPort RBAILogPath)
      hiRegAfterTimeOut(1000 'RBAIBridgePollLog))))

procedure(RBAIBridgeStop()
  if(RBAIIpc && ipcIsAliveProcess(RBAIIpc) then
    ipcKillProcess(RBAIIpc)
    RBAIIpc = nil
    printf("[AI Bridge] MCP Server stopped\n")
  else
    printf("[AI Bridge] MCP Server is not running\n")))

; ============================================================================
; Log polling — scheduled every 500ms while server subprocess is alive
; ============================================================================

procedure(_rbaiFmtLine(rawLine)
  ; Extract the value of the "display" field from a JSON log line.
  ; Example: {"ts":"10:23:45","display":"[10:23:45] > list_windows","type":"tool_call"}
  ; Strips trailing newline, then finds "display":" and extracts until the next ".
  let((s e stripped)
    stripped = rawLine
    when(strlen(rawLine) > 0
      when(equal(substring(rawLine strlen(rawLine) 1) "\n")
        stripped = substring(rawLine 1 (strlen(rawLine) - 1))))
    s = index(stripped "\"display\":\"")
    if(s then
      s = substring(s 12)       ; skip past the 11-char prefix  "display":"
      e = index(s "\"")         ; suffix starting at the closing quote
      if(e then
        substring(s 1 (strlen(s) - strlen(e)))
      else
        stripped)
    else
      stripped)))

procedure(RBAIBridgePollLog()
  let((port line choices display)
    when(isFile(RBAILogPath)
      port = infile(RBAILogPath)
      when(port
        ; Skip lines already shown
        for(i 1 RBAILogLine
          gets(port))
        ; Append new lines to the log listbox
        while((line = gets(port)) != nil
          display = _rbaiFmtLine(line)
          when(boundp('RBAILogForm) && RBAILogForm
            choices = RBAILogForm->RBAILogList->choices
            when(length(choices) == 1 && equal(car(choices) "(log empty)")
              choices = nil)
            choices = append(choices list(display))
            when(length(choices) > 500
              choices = nthcdr((length(choices) - 500) choices))
            RBAILogForm->RBAILogList->choices = choices)
          RBAILogLine = RBAILogLine + 1)
        close(port))))
  when(RBAIIpc && ipcIsAliveProcess(RBAIIpc)
    hiRegAfterTimeOut(500 'RBAIBridgePollLog)))

; ============================================================================
; Refresh the status form labels with live daemon / MCP states
; ============================================================================

procedure(RBAIRefreshStatus()
  let((daemonOk mcpOk)
    daemonOk = boundp('RBIpc) && RBIpc && ipcIsAliveProcess(RBIpc)
    mcpOk    = RBAIIpc && ipcIsAliveProcess(RBAIIpc)
    when(boundp('RBAIStatusForm) && RBAIStatusForm
      RBAIStatusForm->RBAIStatDaemon->labelText =
        sprintf(nil "Bridge Daemon : %s  (port %d)"
          if(daemonOk "[Running]" "[Down]")
          if(boundp('RBPort) RBPort 65432))
      RBAIStatusForm->RBAIStatMcp->labelText =
        sprintf(nil "MCP Server    : %s  (port %d)"
          if(mcpOk "[Running]" "[Stopped]")
          RBAIPort)
      RBAIStatusForm->RBAIStatHint->labelText =
        if(mcpOk
          "Claude Desktop MCP: http://127.0.0.1:8765/mcp"
          "Start MCP Server, then configure Claude Desktop."))))

; ============================================================================
; Clear the log view and reset the read cursor
; ============================================================================

procedure(RBAILogFormClear()
  when(boundp('RBAILogForm) && RBAILogForm
    RBAILogForm->RBAILogList->choices = list("(log empty)"))
  RBAILogLine = 0
  when(isFile(RBAILogPath) deleteFile(RBAILogPath)))

; ============================================================================
; GUI — build forms + menu exactly once per Virtuoso session.
; ============================================================================

unless(boundp('RBAIInstalled) && RBAIInstalled
progn(

; --------------------------------------------------------------------------
; Status form
; --------------------------------------------------------------------------
RBAIStatDaemon = hiCreateLabel(?name 'RBAIStatDaemon
                   ?labelText "Bridge Daemon : (unknown)"
                   ?justification CDS_JUSTIFY_LEFT)
RBAIStatMcp    = hiCreateLabel(?name 'RBAIStatMcp
                   ?labelText "MCP Server    : (unknown)"
                   ?justification CDS_JUSTIFY_LEFT)
RBAIStatHint   = hiCreateLabel(?name 'RBAIStatHint
                   ?labelText "Click Refresh to update status."
                   ?justification CDS_JUSTIFY_LEFT)

RBAIBtnStart   = hiCreateButton(?name 'RBAIBtnStart
                   ?buttonText "Start MCP Server"
                   ?callback   "RBAIBridgeStart() RBAIRefreshStatus()")
RBAIBtnStop    = hiCreateButton(?name 'RBAIBtnStop
                   ?buttonText "Stop MCP Server"
                   ?callback   "RBAIBridgeStop() RBAIRefreshStatus()")
RBAIBtnRefresh = hiCreateButton(?name 'RBAIBtnRefresh
                   ?buttonText "Refresh"
                   ?callback   "RBAIRefreshStatus()")

RBAIStatusForm = hiCreateAppForm(
  ?name         'RBAIStatusForm
  ?formTitle    "AI Bridge - Status"
  ?fields       list(
    list(RBAIStatDaemon  20:20  600:22)
    list(RBAIStatMcp     20:50  600:22)
    list(RBAIStatHint    20:80  600:22)
    list(RBAIBtnStart    20:120 160:28)
    list(RBAIBtnStop    195:120 160:28)
    list(RBAIBtnRefresh 370:120 100:28))
  ?buttonLayout 'Close)

; --------------------------------------------------------------------------
; Agent log form
; --------------------------------------------------------------------------
RBAILogList  = hiCreateListBox(?name       'RBAILogList
                 ?choices     list("(log empty)")
                 ?numVisLines 22)
RBAIBtnClear = hiCreateButton(?name 'RBAIBtnClear
                 ?buttonText "Clear log"
                 ?callback   "RBAILogFormClear()")

RBAILogForm = hiCreateAppForm(
  ?name         'RBAILogForm
  ?formTitle    "AI Bridge - Agent Log"
  ?fields       list(
    list(RBAILogList   10:10  820:374)
    list(RBAIBtnClear  10:394  90:28))
  ?buttonLayout 'Close)

; --------------------------------------------------------------------------
; Banner menu — inserted once (guarded by RBAIMenuInstalled)
; --------------------------------------------------------------------------
unless(boundp('RBAIMenuInstalled) && RBAIMenuInstalled
  let((menu)
    menu = hiCreatePulldownMenu(
      'RBAIMenu "AI Bridge"
      list(
        hiCreateMenuItem(
          ?name     'RBAIMenuStatus
          ?itemText "Status..."
          ?callback "RBAIRefreshStatus() hiDisplayForm(RBAIStatusForm)")
        hiCreateSeparatorMenuItem('RBAIMenuSep1)
        hiCreateMenuItem(
          ?name     'RBAIMenuStart
          ?itemText "Start MCP Server"
          ?callback "RBAIBridgeStart()")
        hiCreateMenuItem(
          ?name     'RBAIMenuStop
          ?itemText "Stop MCP Server"
          ?callback "RBAIBridgeStop()")
        hiCreateSeparatorMenuItem('RBAIMenuSep2)
        hiCreateMenuItem(
          ?name     'RBAIMenuLog
          ?itemText "Agent Log..."
          ?callback "hiDisplayForm(RBAILogForm)")))
    hiInsertBannerMenu(window(1) menu 4)
    RBAIMenuInstalled = t))

RBAIInstalled = t
) ; end progn / unless

printf("[AI Bridge] loaded - AI Bridge menu is now available\n")
