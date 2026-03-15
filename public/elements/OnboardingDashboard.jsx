import React from "react";

const actionMeta = {
  explain_task: { label: "Explain this step", callback: "explain_task", tone: "ghost" },
  watch_agent: { label: "Run agent for me", callback: "watch_agent", tone: "primary" },
  self_complete: { label: "Mark done", callback: "self_complete", tone: "secondary" },
  skip: { label: "Skip for now", callback: "skip_task", tone: "ghost" },
  toggle_full_checklist: { label: "Show full checklist", callback: "toggle_full_checklist", tone: "ghost" },
};

const prettyLabel = {
  self_serve: "Manual step",
  agent_terminal: "Terminal agent",
  agent_browser: "Browser agent",
  manual_external: "External system",
  knowledge: "Read and learn",
  required: "Required",
  optional: "Optional",
  deferred: "Deferred",
  not_started: "Pending",
  in_progress: "In progress",
  completed: "Done",
  skipped: "Skipped",
  blocked: "Blocked",
};

function badgeStyle(kind) {
  const palette = {
    live: { bg: "rgba(16,185,129,0.14)", border: "rgba(16,185,129,0.34)", color: "#86efac" },
    demo: { bg: "rgba(245,158,11,0.14)", border: "rgba(245,158,11,0.34)", color: "#fcd34d" },
    status: { bg: "rgba(56,189,248,0.12)", border: "rgba(56,189,248,0.28)", color: "#7dd3fc" },
    warning: { bg: "rgba(248,113,113,0.14)", border: "rgba(248,113,113,0.28)", color: "#fca5a5" },
  };
  return palette[kind];
}

function buttonStyle(tone) {
  const shared = {
    borderRadius: "14px",
    border: "1px solid transparent",
    padding: "11px 14px",
    fontSize: "13px",
    fontWeight: 800,
    cursor: "pointer",
    transition: "transform 120ms ease, opacity 120ms ease, border-color 120ms ease",
    letterSpacing: "0.01em",
  };
  if (tone === "primary") {
    return {
      ...shared,
      background: "linear-gradient(135deg, #fb923c 0%, #f43f5e 100%)",
      color: "#140d08",
    };
  }
  if (tone === "secondary") {
    return {
      ...shared,
      background: "rgba(45,212,191,0.16)",
      borderColor: "rgba(45,212,191,0.3)",
      color: "#99f6e4",
    };
  }
  return {
    ...shared,
    background: "rgba(148,163,184,0.08)",
    borderColor: "rgba(148,163,184,0.18)",
    color: "#d2deea",
  };
}

function statusDot(status) {
  if (status === "completed") return "#22c55e";
  if (status === "in_progress") return "#38bdf8";
  if (status === "skipped") return "#f59e0b";
  if (status === "blocked") return "#f87171";
  return "#94a3b8";
}

function sendSuggestion(text) {
  if (typeof sendUserMessage === "function") {
    sendUserMessage(text);
  }
}

function triggerAction(action) {
  const meta = actionMeta[action];
  if (!meta) return;
  if (typeof callAction === "function") {
    callAction({ name: meta.callback, payload: { action: meta.callback } });
    return;
  }
  if (typeof sendUserMessage === "function") {
    const fallback = {
      explain_task: "what do i do for this step",
      watch_agent: "let agent do it",
      self_complete: "mark it done",
      skip: "skip this",
    };
    sendUserMessage(fallback[action]);
  }
}

function WorkspacePreview(props) {
  const nextAgentTask = props.nextAgentTask;
  const diagnostics = props.health || {};
  const machine = props.machinePanel || {};
  const transcript = props.latestTranscript || machine.lastTranscript || machine.lastOutput;

  if (props.streamUrl) {
    return (
      <iframe
        src={props.streamUrl}
        title="sandbox-stream"
        style={{
          width: "100%",
          height: "420px",
          border: "none",
          background: "#050b14",
          display: "block",
        }}
      />
    );
  }

  if (props.latestScreenshotArtifact) {
    return (
      <img
        src={props.latestScreenshotArtifact}
        alt="latest workspace capture"
        style={{ width: "100%", height: "420px", objectFit: "cover", display: "block" }}
      />
    );
  }

  if (props.workspaceMode === "local_machine") {
    return (
      <div
        style={{
          padding: "20px",
          height: "420px",
          display: "grid",
          gap: "14px",
          alignContent: "start",
          background: "linear-gradient(180deg, rgba(7,15,28,0.98), rgba(3,10,20,0.98))",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
            gap: "10px",
          }}
        >
          {[
            ["Backend", machine.backend || "local"],
            ["Browser", machine.browserMode || "system-browser"],
            ["Workdir", machine.workDir ? machine.workDir.split("/").slice(-2).join("/") : "waiting"],
            ["Last URL", machine.lastUrl ? "opened" : "none"],
          ].map(([label, value]) => (
            <div
              key={label}
              style={{
                background: "rgba(148,163,184,0.08)",
                border: "1px solid rgba(148,163,184,0.14)",
                borderRadius: "14px",
                padding: "10px 12px",
              }}
            >
              <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
              <div style={{ fontSize: "13px", fontWeight: 700, marginTop: "4px", wordBreak: "break-word" }}>{value}</div>
            </div>
          ))}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.15fr 0.85fr",
            gap: "12px",
            minHeight: "0",
            flex: 1,
          }}
        >
          <div
            style={{
              background: "rgba(8,13,23,0.92)",
              border: "1px solid rgba(148,163,184,0.14)",
              borderRadius: "16px",
              padding: "0",
              overflow: "hidden",
              minHeight: "260px",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "12px 14px",
                borderBottom: "1px solid rgba(148,163,184,0.12)",
                background: "rgba(255,255,255,0.02)",
              }}
            >
              <div style={{ display: "flex", gap: "8px" }}>
                <span style={{ width: "11px", height: "11px", borderRadius: "999px", background: "#fb7185" }} />
                <span style={{ width: "11px", height: "11px", borderRadius: "999px", background: "#f59e0b" }} />
                <span style={{ width: "11px", height: "11px", borderRadius: "999px", background: "#22c55e" }} />
              </div>
              <div style={{ fontSize: "12px", color: "#93a7bb", fontFamily: '"SFMono-Regular", "Menlo", monospace' }}>
                {machine.lastCommand || "waiting for first agent step"}
              </div>
            </div>
            <div
              style={{
                fontFamily: '"SFMono-Regular", "Menlo", monospace',
                fontSize: "12px",
                lineHeight: 1.65,
                color: "#d3f8de",
                padding: "16px 18px",
                whiteSpace: "pre-wrap",
                overflow: "auto",
                height: "100%",
                maxHeight: "320px",
              }}
            >
              {transcript || "# waiting for the first agent-run step..."}
            </div>
          </div>

          <div style={{ display: "grid", gap: "12px", alignContent: "start" }}>
            <div
              style={{
                background: "rgba(148,163,184,0.06)",
                border: "1px solid rgba(148,163,184,0.12)",
                borderRadius: "16px",
                padding: "14px 16px",
              }}
            >
              <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>
                Agent status
              </div>
              <div style={{ fontSize: "15px", fontWeight: 700, lineHeight: 1.4 }}>
                {props.latestStatus || "Ready for the first agent action"}
              </div>
            </div>

            {machine.files && machine.files.length > 0 ? (
              <div
                style={{
                  background: "rgba(148,163,184,0.06)",
                  border: "1px solid rgba(148,163,184,0.12)",
                  borderRadius: "16px",
                  padding: "14px 16px",
                }}
              >
                <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "8px" }}>
                  Workbench files
                </div>
                <div style={{ display: "grid", gap: "6px", fontFamily: '"SFMono-Regular", "Menlo", monospace', fontSize: "12px", color: "#d9e2ec" }}>
                  {machine.files.map((file) => (
                    <div key={file}>{file}</div>
                  ))}
                </div>
              </div>
            ) : null}

            {nextAgentTask ? (
              <div
                style={{
                  background: "rgba(34,211,238,0.08)",
                  border: "1px solid rgba(34,211,238,0.16)",
                  borderRadius: "16px",
                  padding: "14px 16px",
                }}
              >
                <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>
                  Next agent-ready step
                </div>
                <div style={{ fontSize: "14px", fontWeight: 700, lineHeight: 1.45 }}>
                  {nextAgentTask.taskId} {nextAgentTask.title}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <details
          style={{
            background: "rgba(148,163,184,0.05)",
            border: "1px solid rgba(148,163,184,0.1)",
            borderRadius: "14px",
            padding: "10px 12px",
          }}
        >
          <summary style={{ cursor: "pointer", fontSize: "12px", color: "#8ba0b7", fontWeight: 700 }}>
            Runtime diagnostics
          </summary>
          <div style={{ marginTop: "10px", display: "grid", gap: "6px", fontFamily: '"SFMono-Regular", "Menlo", monospace', fontSize: "12px", color: "#cfd9e5" }}>
            {Object.entries(diagnostics).map(([key, value]) => (
              <div key={key}>{key}: {value}</div>
            ))}
          </div>
        </details>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "20px",
        height: "420px",
        display: "grid",
        alignItems: "stretch",
      }}
    >
      <div
        style={{
          background: "linear-gradient(180deg, rgba(8,15,30,0.98), rgba(6,10,18,0.98))",
          border: "1px solid rgba(148,163,184,0.14)",
          borderRadius: "20px",
          padding: "18px",
          display: "grid",
          gridTemplateRows: "auto auto 1fr auto",
          gap: "16px",
        }}
      >
        <div style={{ display: "flex", gap: "8px" }}>
          <span style={{ width: "12px", height: "12px", borderRadius: "999px", background: "#fb7185" }} />
          <span style={{ width: "12px", height: "12px", borderRadius: "999px", background: "#f59e0b" }} />
          <span style={{ width: "12px", height: "12px", borderRadius: "999px", background: "#22c55e" }} />
        </div>

        <div>
          <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Agent machine
          </div>
          <div style={{ fontSize: "22px", fontWeight: 800, marginTop: "6px" }}>
            {props.workspaceMode === "live" ? "Live execution view" : "Guided demo workspace"}
          </div>
          <div style={{ marginTop: "8px", fontSize: "14px", lineHeight: 1.6, color: "#bfd0df", maxWidth: "560px" }}>
            {props.workspaceMode === "live"
              ? "When the agent runs, the live machine or browser stream appears here."
              : "This prototype is currently running in demo mode. You can still complete steps and see proof updates, but the machine view is simulated until a live sandbox is enabled."}
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gap: "12px",
            alignContent: "start",
          }}
        >
          <div
            style={{
              background: "rgba(148,163,184,0.06)",
              border: "1px solid rgba(148,163,184,0.12)",
              borderRadius: "16px",
              padding: "14px 16px",
            }}
          >
            <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>
              Current workspace status
            </div>
            <div style={{ fontSize: "15px", fontWeight: 700, marginBottom: "6px" }}>
              {props.currentTaskId ? `${props.currentTaskId} ${props.currentTask}` : "Waiting for your introduction"}
            </div>
            <div style={{ fontSize: "13px", color: "#a9bccd", lineHeight: 1.55 }}>
              {props.latestStatus || "No machine action has started yet. Use the action buttons on the right when you are ready."}
            </div>
          </div>

          {nextAgentTask ? (
            <div
              style={{
                background: "rgba(34,211,238,0.08)",
                border: "1px solid rgba(34,211,238,0.16)",
                borderRadius: "16px",
                padding: "14px 16px",
              }}
            >
              <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>
                Agent help becomes available at
              </div>
              <div style={{ fontSize: "15px", fontWeight: 700 }}>{nextAgentTask.taskId} {nextAgentTask.title}</div>
              <div style={{ marginTop: "4px", fontSize: "13px", color: "#abd4e6" }}>
                {prettyLabel[nextAgentTask.automation] || nextAgentTask.automation}
              </div>
            </div>
          ) : null}
        </div>

        <details
          style={{
            background: "rgba(148,163,184,0.05)",
            border: "1px solid rgba(148,163,184,0.1)",
            borderRadius: "14px",
            padding: "10px 12px",
          }}
        >
          <summary style={{ cursor: "pointer", fontSize: "12px", color: "#8ba0b7", fontWeight: 700 }}>
            Developer diagnostics
          </summary>
          <div style={{ marginTop: "10px", display: "grid", gap: "6px", fontFamily: '"SFMono-Regular", "Menlo", monospace', fontSize: "12px", color: "#cfd9e5" }}>
            {Object.entries(diagnostics).map(([key, value]) => (
              <div key={key}>{key}: {value}</div>
            ))}
          </div>
        </details>
      </div>
    </div>
  );
}

export default function OnboardingDashboard(props) {
  const desktopLayout = typeof window === "undefined" ? true : window.innerWidth >= 1280;
  const items = props.items || [];
  const availableActions = props.availableActions || [];
  const currentTaskSources = props.currentTaskSources || [];
  const evidence = props.currentTaskEvidence || [];
  const guidedStep = props.guidedStep || {};
  const actionLabels = props.actionLabels || {};
  const completion = props.totalTasks > 0 ? Math.round((props.completedTasks / props.totalTasks) * 100) : 0;
  const personaLine = [props.employeeName, props.personaTitle].filter(Boolean).join(" • ");
  const stageBadge = badgeStyle(props.workspaceMode === "live" ? "live" : props.workspaceMode === "local_machine" ? "status" : "demo");
  const upcomingTasks = props.upcomingTasks || [];
  const note = props.note;
  const milestone = props.milestoneProgress || {};
  const machine = props.machinePanel || {};

  return (
    <div
      style={{
        fontFamily: '"Avenir Next", "Segoe UI", sans-serif',
        color: "#e5edf5",
        background:
          "radial-gradient(circle at top left, rgba(251,146,60,0.18), transparent 32%), radial-gradient(circle at top right, rgba(34,211,238,0.16), transparent 24%), linear-gradient(180deg, #08111f 0%, #0f172a 100%)",
        border: "1px solid rgba(148,163,184,0.18)",
        borderRadius: "26px",
        padding: "24px",
        boxShadow: "0 30px 90px rgba(2,6,23,0.35)",
        width: desktopLayout ? "min(1320px, calc(100vw - 470px))" : "100%",
        maxWidth: "1320px",
        minWidth: desktopLayout ? "980px" : "0",
        margin: "0 auto",
        position: "relative",
        overflow: "hidden",
        boxSizing: "border-box",
      }}
    >
      {note ? (
        <div
          style={{
            marginBottom: "16px",
            background: "rgba(251,146,60,0.08)",
            border: "1px solid rgba(251,146,60,0.16)",
            borderRadius: "16px",
            padding: "12px 14px",
            fontSize: "14px",
            color: "#f8d5bb",
            lineHeight: 1.5,
          }}
        >
          {note}
        </div>
      ) : null}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "18px",
          marginBottom: "22px",
          flexWrap: "wrap",
        }}
      >
        <div style={{ minWidth: "280px", flex: 1 }}>
          <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "10px", flexWrap: "wrap" }}>
            <span
              style={{
                background: stageBadge.bg,
                border: `1px solid ${stageBadge.border}`,
                color: stageBadge.color,
                borderRadius: "999px",
                padding: "4px 10px",
                fontSize: "11px",
                fontWeight: 800,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            >
              {props.workspaceMode === "live" ? "Live agent mode" : props.workspaceMode === "local_machine" ? "Local machine mode" : "Guided demo mode"}
            </span>
            {props.currentTaskIndex ? (
              <span
                style={{
                  background: "rgba(56,189,248,0.12)",
                  border: "1px solid rgba(56,189,248,0.28)",
                  color: "#7dd3fc",
                  borderRadius: "999px",
                  padding: "4px 10px",
                  fontSize: "11px",
                  fontWeight: 700,
                }}
              >
                Step {props.currentTaskIndex} of {props.totalTasks || 0}
              </span>
            ) : null}
          </div>

          <div style={{ fontSize: "34px", lineHeight: 1.02, fontWeight: 800, letterSpacing: "-0.03em", marginBottom: "8px" }}>
            {personaLine || "Your onboarding workspace"}
          </div>
          <div style={{ fontSize: "15px", color: "#b8c7d6", maxWidth: "820px", lineHeight: 1.6 }}>
            One active step, one clear next action. The left side is the machine and proof surface. The right side is the onboarding decision surface.
          </div>
        </div>

        <div
          style={{
            minWidth: "240px",
            background: "rgba(15,23,42,0.7)",
            border: "1px solid rgba(148,163,184,0.16)",
            borderRadius: "18px",
            padding: "14px 16px",
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em" }}>Progress</div>
              <div style={{ fontSize: "30px", fontWeight: 800 }}>{completion}%</div>
            </div>
            <div>
              <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em" }}>Done</div>
              <div style={{ fontSize: "30px", fontWeight: 800 }}>{props.completedTasks || 0}</div>
            </div>
          </div>
          <div style={{ marginTop: "12px", height: "10px", background: "rgba(148,163,184,0.14)", borderRadius: "999px", overflow: "hidden" }}>
            <div
              style={{
                width: `${completion}%`,
                height: "100%",
                background: "linear-gradient(90deg, #22d3ee 0%, #fb7185 100%)",
                borderRadius: "999px",
              }}
            />
          </div>
          <div style={{ marginTop: "10px", fontSize: "12px", color: "#9fb0c2" }}>
            {props.completedTasks || 0} done · {props.remainingTasks || 0} left
          </div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: desktopLayout ? "minmax(0, 1.3fr) minmax(340px, 0.95fr)" : "1fr",
          gap: "20px",
          alignItems: "start",
        }}
      >
        <div
          style={{
            background: "rgba(7,15,28,0.8)",
            border: "1px solid rgba(148,163,184,0.16)",
            borderRadius: "20px",
            overflow: "hidden",
            minHeight: "520px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "14px 16px",
              borderBottom: "1px solid rgba(148,163,184,0.12)",
              background: "linear-gradient(180deg, rgba(15,23,42,0.92), rgba(15,23,42,0.55))",
            }}
          >
            <div>
              <div style={{ fontSize: "12px", color: "#90a2b6", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                Workspace
              </div>
              <div style={{ fontSize: "16px", fontWeight: 700 }}>
                {props.currentTaskId ? `Focused on ${props.currentTaskId}` : "Waiting for your onboarding intro"}
              </div>
            </div>
            <div
              style={{
                background: "rgba(148,163,184,0.08)",
                border: "1px solid rgba(148,163,184,0.16)",
                borderRadius: "999px",
                padding: "6px 10px",
                fontSize: "12px",
                color: "#b9c7d6",
              }}
            >
              {props.workspaceMode === "live"
                ? "Agent live"
                : props.workspaceMode === "local_machine"
                  ? "Local machine"
                  : "Demo preview"}
            </div>
          </div>

          <WorkspacePreview {...props} />
        </div>

        <div style={{ display: "grid", gap: "18px" }}>
          <div
            style={{
              background: "rgba(15,23,42,0.76)",
              border: "1px solid rgba(148,163,184,0.16)",
              borderRadius: "20px",
              padding: "18px",
            }}
          >
            <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "8px" }}>
              Current step
            </div>
            <div style={{ fontSize: "22px", fontWeight: 800, lineHeight: 1.12 }}>
              {props.currentTaskId
                ? `Step ${props.currentTaskIndex || "--"} · ${props.currentTaskId} ${props.currentTask}`
                : "Introduce yourself to start onboarding"}
            </div>

            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "12px" }}>
              {props.currentTaskAutomation ? (
                <span style={{ ...badgeStyle("status"), borderRadius: "999px", padding: "4px 10px", fontSize: "12px", fontWeight: 700 }}>
                  {prettyLabel[props.currentTaskAutomation] || props.currentTaskAutomation}
                </span>
              ) : null}
              {props.currentTaskPriority ? (
                <span style={{ ...badgeStyle("status"), borderRadius: "999px", padding: "4px 10px", fontSize: "12px", fontWeight: 700 }}>
                  {prettyLabel[props.currentTaskPriority] || props.currentTaskPriority}
                </span>
              ) : null}
                    {props.currentTaskStatus ? (
                <span style={{ ...badgeStyle("status"), borderRadius: "999px", padding: "4px 10px", fontSize: "12px", fontWeight: 700 }}>
                  {prettyLabel[props.currentTaskStatus] || props.currentTaskStatus}
                </span>
                    ) : null}
                    {props.currentTaskPhase ? (
                      <span style={{ ...badgeStyle("status"), borderRadius: "999px", padding: "4px 10px", fontSize: "12px", fontWeight: 700 }}>
                        {String(props.currentTaskPhase).replace(/_/g, " ")}
                      </span>
                    ) : null}
                </div>

            {guidedStep.summary ? (
              <div
                style={{
                  marginTop: "14px",
                  background: "rgba(34,211,238,0.08)",
                  border: "1px solid rgba(34,211,238,0.16)",
                  borderRadius: "16px",
                  padding: "12px 14px",
                }}
              >
                <div style={{ fontSize: "11px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "4px" }}>
                  What to do now
                </div>
                <div style={{ fontSize: "14px", lineHeight: 1.55, color: "#d4e0eb" }}>{guidedStep.summary}</div>
              </div>
            ) : null}

            {guidedStep.what_to_do_now && guidedStep.what_to_do_now.length > 0 ? (
              <div style={{ marginTop: "16px" }}>
                <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "8px" }}>
                  Walkthrough
                </div>
                <div style={{ display: "grid", gap: "8px" }}>
                  {guidedStep.what_to_do_now.map((step, index) => (
                    <div
                      key={`${index}-${step}`}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "28px 1fr",
                        gap: "10px",
                        alignItems: "start",
                        background: "rgba(148,163,184,0.06)",
                        border: "1px solid rgba(148,163,184,0.12)",
                        borderRadius: "14px",
                        padding: "10px 12px",
                      }}
                    >
                      <div
                        style={{
                          width: "28px",
                          height: "28px",
                          borderRadius: "999px",
                          background: "rgba(249,115,22,0.18)",
                          color: "#fdba74",
                          display: "grid",
                          placeItems: "center",
                          fontSize: "12px",
                          fontWeight: 800,
                        }}
                      >
                        {index + 1}
                      </div>
                      <div style={{ fontSize: "13px", lineHeight: 1.55, color: "#d8e2ee" }}>{step}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {guidedStep.fastest_path ? (
              <div
                style={{
                  marginTop: "14px",
                  background: "rgba(249,115,22,0.1)",
                  border: "1px solid rgba(249,115,22,0.18)",
                  borderRadius: "16px",
                  padding: "12px 14px",
                }}
              >
                <div style={{ fontSize: "11px", color: "#fcd34d", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "4px" }}>
                  Fastest way to finish this step
                </div>
                <div style={{ fontSize: "13px", lineHeight: 1.5, color: "#fde68a" }}>{guidedStep.fastest_path}</div>
              </div>
            ) : null}

            {guidedStep.why_it_matters ? (
              <div style={{ marginTop: "10px", fontSize: "12px", lineHeight: 1.5, color: "#9fb0c2" }}>
                Why this matters: {guidedStep.why_it_matters}
              </div>
            ) : null}

            {props.stepTargets && props.stepTargets.length > 0 ? (
              <div style={{ marginTop: "14px" }}>
                <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "8px" }}>
                  Live targets
                </div>
                <div style={{ display: "grid", gap: "8px" }}>
                  {props.stepTargets.map((target) => (
                    <div
                      key={target}
                      style={{
                        background: "rgba(148,163,184,0.06)",
                        border: "1px solid rgba(148,163,184,0.12)",
                        borderRadius: "14px",
                        padding: "10px 12px",
                        fontSize: "13px",
                        lineHeight: 1.5,
                        color: "#dbe6f1",
                        overflowWrap: "anywhere",
                      }}
                    >
                      {target}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {props.currentTaskCategory ? (
              <div style={{ marginTop: "10px", fontSize: "13px", color: "#b7c5d4" }}>
                Category: <strong>{props.currentTaskCategory}</strong>
              </div>
            ) : null}

            {evidence.length > 0 ? (
              <div style={{ marginTop: "8px", fontSize: "13px", color: "#b7c5d4" }}>
                Completion proof: {evidence.join(", ")}
              </div>
            ) : null}

            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "18px" }}>
              <button
                style={buttonStyle(actionMeta.explain_task.tone)}
                onClick={() => triggerAction("explain_task")}
              >
                {actionLabels.explain_task || actionMeta.explain_task.label}
              </button>

              {availableActions.map((action) => {
                const meta = actionMeta[action];
                if (!meta) return null;
                return (
                  <button key={action} style={buttonStyle(meta.tone)} onClick={() => triggerAction(action)}>
                    {actionLabels[action] || meta.label}
                  </button>
                );
              })}
              <button style={buttonStyle(actionMeta.toggle_full_checklist.tone)} onClick={() => triggerAction("toggle_full_checklist")}>
                {props.showFullChecklist ? "Hide full checklist" : "Show full checklist"}
              </button>
            </div>

            {props.healthHint ? (
              <div
                style={{
                  marginTop: "16px",
                  background: badgeStyle("warning").bg,
                  border: `1px solid ${badgeStyle("warning").border}`,
                  color: badgeStyle("warning").color,
                  borderRadius: "16px",
                  padding: "12px 14px",
                  fontSize: "13px",
                  lineHeight: 1.45,
                }}
              >
                {props.healthHint}
              </div>
            ) : null}
          </div>

          <div
            style={{
              background: "rgba(15,23,42,0.72)",
              border: "1px solid rgba(148,163,184,0.16)",
              borderRadius: "20px",
              padding: "18px",
            }}
          >
            <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "10px" }}>
              Up next
            </div>

            {upcomingTasks.length === 0 ? (
              <div style={{ fontSize: "13px", color: "#9fb0c2" }}>
                No open tasks right now.
              </div>
            ) : (
              <div style={{ display: "grid", gap: "10px" }}>
                {upcomingTasks.map((task, index) => (
                  <div
                    key={task.taskId}
                    style={{
                      background: index === 0 ? "rgba(34,211,238,0.08)" : "rgba(148,163,184,0.06)",
                      border: index === 0
                        ? "1px solid rgba(34,211,238,0.16)"
                        : "1px solid rgba(148,163,184,0.12)",
                      borderRadius: "14px",
                      padding: "12px 14px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <span
                        style={{
                          width: "10px",
                          height: "10px",
                          borderRadius: "999px",
                          background: statusDot(task.status),
                          flexShrink: 0,
                        }}
                      />
                      <div style={{ fontSize: "13px", fontWeight: 700, lineHeight: 1.35 }}>
                        Step {task.index} · {task.taskId} {task.title}
                      </div>
                    </div>
                    <div style={{ marginTop: "6px", fontSize: "12px", color: "#9fb0c2" }}>
                      {prettyLabel[task.automation] || task.automation}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {currentTaskSources.length > 0 ? (
              <div style={{ marginTop: "16px" }}>
                <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>
                  Grounded from
                </div>
                <div style={{ display: "grid", gap: "6px" }}>
                  {currentTaskSources.map((source) => (
                    <div key={source} style={{ fontSize: "12px", color: "#d7e1ec" }}>
                      {source}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {milestone.total ? (
              <div style={{ marginTop: "16px" }}>
                <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>
                  Engineering milestone
                </div>
                <div style={{ fontSize: "14px", fontWeight: 700 }}>
                  {milestone.completed}/{milestone.total} checkpoints complete
                </div>
              </div>
            ) : null}
          </div>

          <div
            style={{
              background: "rgba(15,23,42,0.72)",
              border: "1px solid rgba(148,163,184,0.16)",
              borderRadius: "20px",
              padding: "18px",
            }}
          >
            <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "10px" }}>
              Activity and proof
            </div>

            {items.length === 0 ? (
              <div style={{ fontSize: "13px", color: "#9fb0c2" }}>
                No completion events yet. When you or the agent finish steps, proof will appear here.
              </div>
            ) : (
              <div style={{ display: "grid", gap: "10px" }}>
                {items.slice(-4).reverse().map((item) => (
                  <div
                    key={`${item.taskId}-${item.timestamp || item.title}`}
                    style={{
                      background: "rgba(148,163,184,0.08)",
                      border: "1px solid rgba(148,163,184,0.12)",
                      borderRadius: "14px",
                      padding: "12px 14px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", alignItems: "center" }}>
                      <div style={{ fontSize: "13px", fontWeight: 700, lineHeight: 1.35 }}>
                        {item.title}
                      </div>
                      <span
                        style={{
                          width: "10px",
                          height: "10px",
                          borderRadius: "999px",
                          background: statusDot(item.status),
                          flexShrink: 0,
                        }}
                      />
                    </div>
                    {item.detail ? (
                      <div style={{ marginTop: "6px", fontSize: "12px", color: "#9fb0c2", lineHeight: 1.5 }}>
                        {item.detail}
                      </div>
                    ) : null}
                    {item.timestamp ? (
                      <div style={{ marginTop: "8px", fontSize: "11px", color: "#73879b" }}>{item.timestamp}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}

            {props.latestTranscript ? (
              <div style={{ marginTop: "16px" }}>
                <div style={{ fontSize: "12px", color: "#8ba0b7", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "8px" }}>
                  Latest terminal log
                </div>
                <div
                  style={{
                    background: "rgba(8,13,23,0.9)",
                    border: "1px solid rgba(148,163,184,0.12)",
                    borderRadius: "14px",
                    padding: "12px 14px",
                    fontFamily: '"SFMono-Regular", "Menlo", monospace',
                    fontSize: "12px",
                    lineHeight: 1.6,
                    color: "#cfe9d5",
                    whiteSpace: "pre-wrap",
                    maxHeight: "220px",
                    overflow: "auto",
                  }}
                >
                  {props.latestTranscript}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
