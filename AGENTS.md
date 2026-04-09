# Repository Guidelines

## Project Structure & Module Organization
`api/` contains the FastAPI service entrypoint, routers, scheduler, persistence, and WebSocket handling. `workflow/` holds the LangGraph pipeline, state model, and task-specific skills such as search, extraction, article generation, and WeChat publishing. `frontend/src/` contains the React + Vite UI, split into `pages/`, `api/`, `store/`, and shared styles. `tests/` contains backend and workflow tests; persistent runtime data lives in `data/`, and generated logs go to `logs/`.

## Build, Test, and Development Commands
Set up the backend with `python -m venv .venv` and `.\\.venv\\Scripts\\activate`, then install dependencies with `pip install -r requirements.txt`. Run the API locally with `python main.py` or `uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload`. Run backend tests with `pytest`. For the frontend, use `cd frontend`, `npm install`, `npm run dev` for local development, `npm run build` for production assets, and `npm run lint` for ESLint checks.

## Coding Style & Naming Conventions
Follow existing Python conventions: 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and type hints on public functions. Keep FastAPI handlers and workflow nodes small and focused. In TypeScript/React, match the current style: 2-space indentation, no semicolons, `PascalCase` component filenames such as `TaskDetail.tsx`, and `camelCase` for functions, hooks, and Zustand store members.

## Testing Guidelines
Use `pytest` with `pytest-asyncio`; async settings are defined in `pytest.ini`. Place new tests in `tests/` and name them `test_<feature>.py`. Prefer focused unit tests around workflow skills, router behavior, scheduler logic, and WeChat integrations. Mock external APIs and avoid live network calls in default test runs.

## Commit & Pull Request Guidelines
Recent history favors short Chinese commit subjects in imperative form, for example `优化工作流，新增多轮对话文章结构`. Keep commits narrow and descriptive. Pull requests should summarize the user-visible change, list affected areas such as `api`, `workflow`, or `frontend`, link related issues, and include screenshots for UI changes. Mention any new `.env` keys, data migrations, or manual verification steps.

## Security & Configuration Tips
Never commit `.env`, API secrets, or production account data. Keep `.env.example` aligned with required settings. Treat `data/tasks.json` and `data/style_config.json` as local state, not hand-edited source files, and avoid committing generated contents from `logs/`, `frontend/dist/`, or `frontend/node_modules/`.
