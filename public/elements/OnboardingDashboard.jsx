import React from "react";

export default function OnboardingDashboard(props) {
  const items = props.items || [];
  const health = props.health || {};

  return (
    <div
      style={{
        fontFamily: '"IBM Plex Sans", sans-serif',
        background:
          "linear-gradient(180deg, rgba(251,247,236,1) 0%, rgba(243,236,218,1) 100%)",
        border: "1px solid #d6c7a8",
        borderRadius: "18px",
        padding: "16px",
        color: "#1f2937",
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: "8px" }}>Live Verification</h3>
      <div style={{ fontSize: "14px", marginBottom: "12px" }}>
        <strong>Current task:</strong> {props.currentTask || "Waiting for task"}
      </div>
      <div style={{ fontSize: "14px", marginBottom: "12px" }}>
        <strong>Status:</strong> {props.latestStatus || "Idle"}
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
          gap: "8px",
          marginBottom: "12px",
        }}
      >
        {Object.keys(health).length === 0 ? (
          <div style={{ fontSize: "13px" }}>No health data yet.</div>
        ) : (
          Object.entries(health).map(([key, value]) => (
            <div
              key={key}
              style={{
                background: "#f7efe0",
                borderRadius: "10px",
                padding: "8px 10px",
                fontSize: "12px",
              }}
            >
              <strong>{key}</strong>
              <div>{value}</div>
            </div>
          ))
        )}
      </div>
      {props.streamUrl ? (
        <iframe
          src={props.streamUrl}
          title="sandbox-stream"
          style={{
            width: "100%",
            height: "220px",
            border: "1px solid #d4b483",
            borderRadius: "12px",
            background: "#fefefe",
            marginBottom: "12px",
          }}
        />
      ) : (
        <div
          style={{
            height: "120px",
            borderRadius: "12px",
            border: "1px dashed #b79c68",
            display: "grid",
            placeItems: "center",
            marginBottom: "12px",
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
              border: "1px solid #d4b483",
              display: "block",
            }}
          />
        </div>
      ) : null}
      <div style={{ display: "grid", gap: "8px" }}>
        {items.length === 0 ? (
          <div style={{ fontSize: "14px" }}>No verification entries yet.</div>
        ) : (
          items.map((item) => (
            <div
              key={item.taskId}
              style={{
                background: "#fffdf8",
                border: "1px solid #e2d5bc",
                borderRadius: "12px",
                padding: "10px 12px",
              }}
            >
              <div style={{ fontWeight: 700 }}>{item.title}</div>
              <div style={{ fontSize: "13px", textTransform: "capitalize" }}>{item.status}</div>
              <div style={{ fontSize: "13px", marginTop: "4px" }}>{item.detail}</div>
              {item.timestamp ? (
                <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "4px" }}>
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
