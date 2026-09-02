# React + Vite — Traffic Control System Frontend

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.

## Known Fixes

### AI Summary 404

`AISummary.jsx` previously constructed the API URL with a double slash (`${config.API_BASE_URL}/ai/summary` → `http://127.0.0.1:8000//ai/summary`), which returned a 404. The leading `/` was removed to produce the correct single-slash path (`${config.API_BASE_URL}ai/summary`).

### WebSocket cleanup race

`EventsProvider` created the WebSocket directly inside `useEffect`. During React 18 StrictMode's synchronous effect→cleanup→effect cycle, the cleanup closed the WebSocket before it had time to connect, producing a "closed before connection established" console error. Fixed by deferring WebSocket creation with `setTimeout(fn, 0)` — StrictMode's cleanup cancels the first timer before it fires, so only the second (real) effect run creates a connection.

### Traffic analysis double-nested auth headers

`Devices.jsx` `openTraffic` called `authHeaders(token)` (which returns `{ headers: { Authorization: ... } }`) then re-wrapped it in `{ headers }`, producing `headers.headers` — the Authorization token was never sent with the traffic analysis request. Fixed by passing the config object directly, matching the pattern used elsewhere in the component.

### Traffic analysis double data URI prefix

`Devices.jsx` rendered the traffic analysis image with `src={`data:image/jpeg;base64,${trafficImg}`}`, but the backend's `image_base64` field already includes the full data URI prefix, resulting in `data:image/jpeg;base64,data:image/jpeg;base64,...` and an `ERR_INVALID_URL`. Fixed by using `trafficImg` directly as the `src`.
