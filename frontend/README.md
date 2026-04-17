# PrepPath Frontend

React + Vite UI for the three roles: executive, feeder, candidate.

## Run

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at http://localhost:5173 and proxies API calls to
http://localhost:8000 (the FastAPI backend in ../preppath).

Start the backend separately:

```bash
cd preppath
uvicorn main:app --reload
```

## Seed accounts

- executive: `exec@preppath.io` / `exec123`
- feeder:    `feeder@preppath.io` / `feeder123`
- candidate: `alex@example.com` / `candidate123`

## Routes

- `/login` — sign in (redirects by role)
- `/exec` — executive dashboard
- `/feeder/paths`, `/feeder/paths/:id`, `/feeder/candidates`
- `/candidate`, `/candidate/test/:assessmentId`, `/candidate/chat/:sectionId`, `/candidate/progress`
