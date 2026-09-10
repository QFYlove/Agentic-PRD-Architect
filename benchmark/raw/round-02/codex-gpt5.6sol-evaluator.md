suzuya\@SuzuyadeMacBook-Pro Agentic-PRD-Architect-codex % ./.venv/bin/ruff format --check backend

./.venv/bin/ruff check backend

./.venv/bin/mypy backend

./.venv/bin/python -m pytest backend/tests -p no\:cacheprovider -q

npm run typecheck

npm run lint

npm run test\:run

npm run build

npx playwright test --project=chromium

Would reformat: **backend/tests/test\_node\_timings.py**

1 file would be reformatted, 43 files already formatted

**I001** [**\***] **Import block is un-sorted or un-formatted**

  **-->** backend/tests/test\_node\_timings.py:9:1

   **|**

** 7 |**   """

** 8 |**

** 9 |** **/** from \_\_future\_\_ import annotations

**10 |** **|**

**11 |** **|** from collections.abc import AsyncIterator

**12 |** **|**

**13 |** **|** import pytest

**14 |** **|**

**15 |** **|** from backend.prd\_document import PRD\_COMPLETION\_MARKER

**16 |** **|** from backend.prompts import (

**17 |** **|**     COMPOSITION\_RULES,

**18 |** **|**     GENERATOR\_SYSTEM\_PROMPT,

**19 |** **|**     OPTIMIZER\_SYSTEM\_PROMPT,

**20 |** **|** )

**21 |** **|** from backend.providers.base import ProviderTextEvent

**22 |** **|** from backend.providers.mock import MockLLMProvider

**23 |** **|** from backend.schemas import (

**24 |** **|**     CreateRunRequest,

**25 |** **|**     RevisionPlan,

**26 |** **|**     RunStatus,

**27 |** **|**     TokenUsage,

**28 |** **|** )

**29 |** **|** from backend.tests.helpers import make\_manager

**30 |** **|**

**31 |** **|** from backend.language import DEFAULT\_OUTPUT\_LANGUAGE

   **|** **|\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_^**

   **|**

**help**: **Organize imports**

Found 1 error.

[\*] 1 fixable with the \`--fix\` option.

**Success: no issues found in 21 source files**

........................................................................ [ 25%]

........................................................................ [ 51%]

........................................................................ [ 77%]

...............................................................          [100%]

**279 passed** in 9.49s

\> agentic-prd-architect\@0.1.0 typecheck

\> cross-env ASTRO\_TELEMETRY\_DISABLED=1 astro check

11:01:13 [types] Generated 1.90s

11:01:13 [check] Getting diagnostics for Astro files in /Users/suzuya/Documents/Agentic-PRD-Architect-codex...

**Result (61 files): **

\- **0 errors**

\- **0 warnings**

\- 0 hints



\> agentic-prd-architect\@0.1.0 lint

\> eslint . --ext .astro,.ts,.tsx --max-warnings 0



\> agentic-prd-architect\@0.1.0 test\:run

\> vitest run



** RUN ** v2.1.8 /Users/suzuya/Documents/Agentic-PRD-Architect-codex

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/runReducer.test.ts (32)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

   ❯ AgentDashboard state framework (18)

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     · hides manual recalibration once the run is terminal

     · follows the selected version through reviewer detail and its revision pla

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows the empty creation state without a run URL 1514ms

     ✓ shows an explicit creating state while POST /api/runs is pending 2117ms

     ✓ shows an explicit creating state while POST /api/runs is pending 2117ms

     ✓ shows an explicit creating state while POST /api/runs is pending 2117ms

     ✓ shows an explicit creating state while POST /api/runs is pending 2117ms

     ✓ shows an explicit creating state while POST /api/runs is pending 2117ms

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · offers manual recalibration while a live run is not connected

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     · hides manual recalibration once the run is terminal

     ⠙ hides manual recalibration once the run is terminal

     ⠹ hides manual recalibration once the run is terminal

     ⠸ hides manual recalibration once the run is terminal

     ⠼ hides manual recalibration once the run is terminal

     ⠴ hides manual recalibration once the run is terminal

     ⠦ hides manual recalibration once the run is terminal

     ⠧ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ hides manual recalibration once the run is terminal

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the GENERATING dashboard state

     ✓ renders the PAUSE\_REQUESTED dashboard state

     ✓ renders the PAUSED dashboard state 320ms

     ✓ renders the PAUSED dashboard state 320ms

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the PAUSED dashboard state 320ms

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the FAILED dashboard state

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the FAILED dashboard state

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the FAILED dashboard state

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the FAILED dashboard state

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the FAILED dashboard state

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the FAILED dashboard state

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the FAILED dashboard state

     ✓ renders the COMPLETED dashboard state 1402ms

     ✓ renders the FAILED dashboard state

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ hides manual recalibration once the run is terminal

     ✓ renders the FAILED dashboard state

     ✓ offers manual recalibration while a live run is not connected 649ms

     ✓ hides manual recalibration once the run is terminal

 ✓ src/components/AgentDashboard.test.tsx (18) 13192ms

 ✓ src/components/ConversationSidebar.test.tsx (2)

 ✓ src/components/components.test.tsx (13) 4210ms

 ✓ src/components/mermaid.test.tsx (17) 769ms

 ✓ src/components/panels.test.tsx (14) 2174ms

 ✓ src/components/versionDiff.test.tsx (15) 2570ms

 ✓ src/hooks/useAgentRun.test.tsx (16) 2409ms

 ✓ src/lib/api.test.ts (11)

 ✓ src/lib/contracts.test.ts (6)

 ✓ src/lib/diff.test.ts (11)

 ✓ src/lib/helpers.test.ts (6)

 ✓ src/lib/outcomeSummary.test.ts (11)

 ✓ src/lib/runFailures.test.ts (11)

 ✓ src/lib/runReducer.test.ts (32)

 ✓ src/lib/smoke.test.ts (1)

 Test Files  **15 passed** (15)

      Tests  **184 passed** (184)

   Start at  11:01:27

   Duration  20.81s (transform 5.16s, setup 11.41s, collect 26.02s, tests 25.81s, environment 36.56s, prepare 4.01s)



\> agentic-prd-architect\@0.1.0 build

\> cross-env ASTRO\_TELEMETRY\_DISABLED=1 astro check && cross-env ASTRO\_TELEMETRY\_DISABLED=1 astro build

11:01:50 [types] Generated 84ms

11:01:50 [check] Getting diagnostics for Astro files in /Users/suzuya/Documents/Agentic-PRD-Architect-codex...

**Result (61 files): **

\- **0 errors**

\- **0 warnings**

\- 0 hints

11:02:03 [types] Generated 72ms

11:02:03 [build] output: "server"

11:02:03 [build] directory: /Users/suzuya/Documents/Agentic-PRD-Architect-codex/dist/

11:02:03 [build] adapter: @astrojs/node

11:02:03 [build] Collecting build info...

11:02:03 [build] ✓ Completed in 106ms.

11:02:03 [build] Building server entrypoints...

11:02:03 [vite] ✓ built in 613ms

11:02:03 [build] ✓ Completed in 633ms.

 building client (vite) 

11:02:34 [vite] ✓ 4087 modules transformed.

11:02:38 [vite] dist/client/\_astro/array.BKyUJesY.js                              **    0.09 kB** │ gzip:   0.10 kB

11:02:38 [vite] dist/client/\_astro/clone.CSS31Gqq.js                              **    0.09 kB** │ gzip:   0.11 kB

11:02:38 [vite] dist/client/\_astro/AgentDashboard.BQf6pul8.js                     **    0.11 kB** │ gzip:   0.10 kB

11:02:38 [vite] dist/client/\_astro/channel.DKp4vqsW\.js                            **    0.12 kB** │ gzip:   0.13 kB

11:02:38 [vite] dist/client/\_astro/Tableau10.B-NsZVaP.js                          **    0.19 kB** │ gzip:   0.18 kB

11:02:38 [vite] dist/client/\_astro/init.Dmth1JHB.js                               **    0.38 kB** │ gzip:   0.19 kB

11:02:38 [vite] dist/client/\_astro/flowDiagram-v2-96b9c2cf.HwiPnJ3x.js            **    0.87 kB** │ gzip:   0.48 kB

11:02:38 [vite] dist/client/\_astro/line.CCnTgD9E.js                               **    0.96 kB** │ gzip:   0.47 kB

11:02:38 [vite] dist/client/\_astro/ordinal.DyD6k62E.js                            **    1.20 kB** │ gzip:   0.58 kB

11:02:38 [vite] dist/client/\_astro/svgDrawCommon-08f97a94.D\_n1C4F-.js             **    1.34 kB** │ gzip:   0.58 kB

11:02:38 [vite] dist/client/\_astro/band.CV1DfrAr.js                               **    1.54 kB** │ gzip:   0.68 kB

11:02:38 [vite] dist/client/\_astro/path.CXeFd1JH.js                               **    2.28 kB** │ gzip:   1.00 kB

11:02:38 [vite] dist/client/\_astro/arc.Q1U3ga9b.js                                **    3.45 kB** │ gzip:   1.48 kB

11:02:38 [vite] dist/client/\_astro/WorkflowDiagram.CpbZG\_ui.js                    **    3.69 kB** │ gzip:   1.73 kB

11:02:38 [vite] dist/client/\_astro/stateDiagram-v2-d93cdb3a.ZHviIAMk.js           **    4.99 kB** │ gzip:   2.38 kB

11:02:38 [vite] dist/client/\_astro/classDiagram-v2-f2320105.CrHLxVtX.js           **    5.03 kB** │ gzip:   2.26 kB

11:02:38 [vite] dist/client/\_astro/PRDViewer.BK5-XBqe.js                          **    5.64 kB** │ gzip:   2.74 kB

11:02:38 [vite] dist/client/\_astro/index.DJO9vBfz.js                              **    6.96 kB** │ gzip:   2.78 kB

11:02:38 [vite] dist/client/\_astro/infoDiagram-f8f76790.DhnoK0Vb.js               **    8.69 kB** │ gzip:   3.29 kB

11:02:38 [vite] dist/client/\_astro/classDiagram-70f12bd4.BLEegxvR.js              **    9.35 kB** │ gzip:   2.92 kB

11:02:38 [vite] dist/client/\_astro/styles-c10674c1.Ctqk8WUc.js                     **  10.10 kB** │ gzip:   3.70 kB

11:02:38 [vite] dist/client/\_astro/stateDiagram-587899a1.DCQNE3Th.js               **  10.23 kB** │ gzip:   3.56 kB

11:02:38 [vite] dist/client/\_astro/linear.D762KtEq.js                              **  10.48 kB** │ gzip:   4.37 kB

11:02:38 [vite] dist/client/\_astro/index-3862675e.DvWeoafE.js                      **  11.99 kB** │ gzip:   4.13 kB

11:02:38 [vite] dist/client/\_astro/VersionDiff.LwZMH1P4.js                         **  12.68 kB** │ gzip:   4.49 kB

11:02:38 [vite] dist/client/\_astro/pieDiagram-8a3498a8.CCQ6Gie7.js                 **  15.09 kB** │ gzip:   5.67 kB

11:02:38 [vite] dist/client/\_astro/time.mFRcw6XO.js                                **  15.14 kB** │ gzip:   4.93 kB

11:02:38 [vite] dist/client/\_astro/string.BvgSK4B4.js                              **  16.73 kB** │ gzip:   5.46 kB

11:02:38 [vite] dist/client/\_astro/graph.CHveHpkp.js                               **  17.48 kB** │ gzip:   6.29 kB

11:02:38 [vite] dist/client/\_astro/sankeyDiagram-04a897e0.DRFBEg-1.js              **  21.19 kB** │ gzip:   7.75 kB

11:02:38 [vite] dist/client/\_astro/flowDiagram-66a62f08.Wbl1WAuE.js                **  21.77 kB** │ gzip:   7.17 kB

11:02:38 [vite] dist/client/\_astro/journeyDiagram-49397b02.BK0Xqrnk.js             **  21.77 kB** │ gzip:   7.68 kB

11:02:38 [vite] dist/client/\_astro/timeline-definition-85554ec2.DEj4wg1r.js        **  22.73 kB** │ gzip:   7.96 kB

11:02:38 [vite] dist/client/\_astro/requirementDiagram-deff3bca.P\_nLclcJ.js         **  24.72 kB** │ gzip:   8.51 kB

11:02:38 [vite] dist/client/\_astro/styles-6aaf32cf.CoKF0m0X.js                     **  26.42 kB** │ gzip:   8.44 kB

11:02:38 [vite] dist/client/\_astro/layout.DQ8d\_oy-.js                              **  28.85 kB** │ gzip:  10.50 kB

11:02:38 [vite] dist/client/\_astro/quadrantDiagram-120e2f19.CMiX3hGt.js            **  29.51 kB** │ gzip:   8.38 kB

11:02:38 [vite] dist/client/\_astro/erDiagram-9861fffd.HbvKOKk5.js                  **  30.91 kB** │ gzip:  10.04 kB

11:02:38 [vite] dist/client/\_astro/edges-e0da2a9e.qaHItwLT.js                      **  34.31 kB** │ gzip:   8.91 kB

11:02:38 [vite] dist/client/\_astro/xychartDiagram-e933f94c.8LiqYeTj.js             **  36.16 kB** │ gzip:  10.01 kB

11:02:38 [vite] dist/client/\_astro/blockDiagram-38ab4fdb.B7XGFNQ-.js               **  37.32 kB** │ gzip:  11.98 kB

11:02:38 [vite] dist/client/\_astro/styles-9a916d00.C3Zjefxu.js                     **  37.86 kB** │ gzip:  12.59 kB

11:02:38 [vite] dist/client/\_astro/gitGraphDiagram-72cf32ee.CDI45Obh.js            **  38.84 kB** │ gzip:  11.63 kB

11:02:38 [vite] dist/client/\_astro/ganttDiagram-c361ad54.D7P6cJno.js               **  45.43 kB** │ gzip:  15.87 kB

11:02:38 [vite] dist/client/\_astro/flowDb-956e92f1.B5pOO-Zv.js                     **  46.74 kB** │ gzip:  15.27 kB

11:02:38 [vite] dist/client/\_astro/createText-2e5e7dd3.CwluXWXf.js                 **  60.07 kB** │ gzip:  17.82 kB

11:02:38 [vite] dist/client/\_astro/c4Diagram-3d4e48cf.gmZhU2PY.js                  **  68.51 kB** │ gzip:  19.21 kB

11:02:38 [vite] dist/client/\_astro/AgentDashboard.DaJEzOUB.js                      **  74.33 kB** │ gzip:  23.60 kB

11:02:38 [vite] dist/client/\_astro/sequenceDiagram-704730f1.C5LIJo0q.js            **  84.21 kB** │ gzip:  24.26 kB

11:02:38 [vite] dist/client/\_astro/client.CaOyRcmD.js                             **  135.60 kB** │ gzip:  43.80 kB

11:02:38 [vite] dist/client/\_astro/index.BSrdc0pO.js                              **  161.08 kB** │ gzip:  48.53 kB

11:02:38 [vite] dist/client/\_astro/mermaid.core.DeW1eGX0.js                       **  240.82 kB** │ gzip:  67.07 kB

11:02:38 [vite] dist/client/\_astro/katex.HP8lGamR.js                              **  258.47 kB** │ gzip:  77.57 kB

11:02:38 [vite] dist/client/\_astro/RadarScoreChart.CJEMFfQ1.js                    **  308.29 kB** │ gzip:  83.45 kB

11:02:38 [vite] dist/client/\_astro/mindmap-definition-fc14e90a.xnhinF7s.js        **  543.77 kB** │ gzip: 170.34 kB

11:02:38 [vite] dist/client/\_astro/flowchart-elk-definition-4a651766.ChrX82zH.js  **1,448.54 kB** │ gzip: 444.17 kB

11:02:38 [vite] ✓ built in 34.87s

11:02:38 [build] Rearranging server assets...

11:02:38 [build] Server built in **35.74s**

11:02:38 [build] **Complete!**

[WebServer] /bin/sh: .venvScriptspython.exe: command not found

Error: Process from config.webServer was not able to start. Exit code: 127

suzuya\@SuzuyadeMacBook-Pro Agentic-PRD-Architect-codex % 