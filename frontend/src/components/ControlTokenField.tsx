import { useState } from "react";

import { getControlToken, setControlToken } from "../api/client";

/** Bearer token for control actions; stored in sessionStorage for this tab only. */
export function ControlTokenField() {
  const [hasToken, setHasToken] = useState(() => getControlToken() !== null);
  const [draft, setDraft] = useState("");

  if (hasToken) {
    return (
      <p className="token-row">
        Token de control activo{" "}
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            setControlToken(null);
            setHasToken(false);
          }}
        >
          Olvidar
        </button>
      </p>
    );
  }

  return (
    <form
      className="token-row"
      onSubmit={(event) => {
        event.preventDefault();
        if (draft.trim()) {
          setControlToken(draft.trim());
          setDraft("");
          setHasToken(true);
        }
      }}
    >
      <label htmlFor="control-token">Token de control</label>
      <input
        id="control-token"
        type="password"
        autoComplete="off"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="TERMINAL_ADMIN_TOKEN"
      />
      <button type="submit">Usar</button>
    </form>
  );
}
