# AlphaGen web

The dashboard for AlphaGen: a list of hypotheses, the reasoning trail behind each one, and the approval gate for the owner.

Vite + React 19 + TypeScript, Tailwind CSS 4, TanStack Query, Clerk.

```bash
npm install
npm run dev      # http://localhost:5173, expects the API from the repo root README
npm run lint
npm run build
```

Environment (`.env.local`): `VITE_CLERK_PUBLISHABLE_KEY` and `VITE_API_BASE_URL` (default `http://localhost:8000`).

Design notes live at the top of `src/index.css`: green, red, and amber are semantic only, the blue accent is the only interaction colour, and serif type marks text quoted verbatim from a filing.
