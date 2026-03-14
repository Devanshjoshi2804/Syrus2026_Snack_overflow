import React from "react";

export default function OnboardingDashboard(props) {
  const items = props.items || [];
  const health = props.health || {};
  const totalTasks = props.totalTasks || 0;
  const completedTasks = props.completedTasks || 0;
  const progressPct = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  const healthColor = (value) => {
    const v = (value || "").toLowerCase();
    if (["yes", "configured", "memory", "qdrant", "mock", "available"].some((k) => v.includes(k)))
      return "#22c55e";
    if (["missing", "no", "unreachable"].some((k) => v.includes(k)))
      return "#ef4444";
    return "#f59e0b";
  };

  const statusIcon = (status) => {
    const s = (status || "").toLowerCase();
    if (s === "completed") return "✅";
    if (s === "skipped") return "⏭️";
    if (s === "in_progress") return "🔄";
    if (s === "blocked") return "🚫";
    return "⬜";
  };

  return (
    <div
      style={{
        fontFamily: '"Inter", "IBM Plex Sans", sans-serif',
        background:
          "linear-gradient(135deg, rgba(15,23,42,1) 0%, rgba(30,41,59,1) 100%)",
        border: "1px solid rgba(148,163,184,0.2)",
        borderRadius: "18px",
        padding: "20px",
        color: "#e2e8f0",
      }}
    >
      <h3
        style={{
          marginTop: 0,
          marginBottom: "12px",
          background: "linear-gradient(90deg, #60a5fa, #a78bfa)",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          fontSize: "18px",
          fontWeight: 700,
        }}
      >
        🤖 OnboardAI Dashboard
      </h3>

      {/* Progress Bar */}
      {totalTasks > 0 && (
        <div style={{ marginBottom: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "6px" }}>
            <span>Progress</span>
            <span style={{ fontWeight: 700, color: "#60a5fa" }}>{progressPct}%</span>
          </div>
          <div
            style={{
              height: "8px",
              background: "rgba(148,163,184,0.2)",
              borderRadius: "4px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${progressPct}%`,
                height: "100%",
                background: "linear-gradient(90deg, #60a5fa, #a78bfa)",
                borderRadius: "4px",
                transition: "width 0.5s ease",
              }}
            />
          </div>
        </div>
      )}

      <div style={{ fontSize: "14px", marginBottom: "12px" }}>
        <strong>Current task:</strong> {props.currentTask || "Waiting for introduction"}
      </div>
      <div style={{ fontSize: "14px", marginBottom: "12px" }}>
        <strong>Status:</strong> {props.latestStatus || "Idle"}
      </div>

      {/* Health Badges */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "6px",
          marginBottom: "14px",
        }}
      >
        {Object.entries(health).map(([key, value]) => (
          <span
            key={key}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              background: "rgba(148,163,184,0.1)",
              borderRadius: "20px",
              padding: "4px 10px",
              fontSize: "11px",
              border: `1px solid ${healthColor(value)}40`,
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: healthColor(value),
                display: "inline-block",
              }}
            />
            <strong>{key}</strong>: {value}
          </span>
        ))}
      </div>

      {/* Stream or placeholder */}
      {props.streamUrl ? (
        <iframe
          src={props.streamUrl}
          title="sandbox-stream"
          style={{
            width: "100%",
            height: "200px",
            border: "1px solid rgba(148,163,184,0.2)",
            borderRadius: "12px",
            background: "#0f172a",
            marginBottom: "12px",
          }}
        />
      ) : (
        <div
          style={{
            height: "80px",
            borderRadius: "12px",
            border: "1px dashed rgba(148,163,184,0.3)",
            display: "grid",
            placeItems: "center",
            marginBottom: "12px",
            fontSize: "13px",
            color: "#94a3b8",
          }}
        >
          Stream unavailable in current mode
        </div>
      )}

      {props.latestScreenshotArtifact ? (
        <div style={{ marginBottom: "12px" }}>
          <div style={{ fontSize: "13px", fontWeight: 700, marginBottom: "6px" }}>
            Latest browser capture
          </div>
          <img
            src={props.latestScreenshotArtifact}
            alt="latest-browser-capture"
            style={{
              width: "100%",
              borderRadius: "12px",
              border: "1px solid rgba(148,163,184,0.2)",
              display: "block",
            }}
          />
        </div>
      ) : null}

      {/* Verification entries */}
      <div style={{ display: "grid", gap: "8px" }}>
        {items.length === 0 ? (
          <div style={{ fontSize: "13px", color: "#94a3b8" }}>No verification entries yet.</div>
        ) : (
          items.map((item) => (
            <div
              key={item.taskId}
              style={{
                background: "rgba(148,163,184,0.08)",
                border: "1px solid rgba(148,163,184,0.15)",
                borderRadius: "12px",
                padding: "10px 12px",
              }}
            >
              <div style={{ fontWeight: 700, fontSize: "13px" }}>
                {statusIcon(item.status)} {item.title}
              </div>
              <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "2px" }}>{item.detail}</div>
              {item.timestamp ? (
                <div style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>
                  {item.timestamp}
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
