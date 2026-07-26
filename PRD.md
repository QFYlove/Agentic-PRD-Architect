# 🎯 GOAL: Build "Agentic PRD Architect" Showcase Web Application

## 1. Executive Summary & Objective

You are an expert AI Engineer and Full-Stack Developer. Your goal is to build a full-stack, production-grade web application called **"Agentic PRD Architect"** to showcase an advanced **Agentic Loop (Generator-Evaluator-Optimizer Pattern)**.

The application will take a brief product idea from a user, generate a draft PRD, critique it across three distinct agent perspectives (Tech Lead, UX Designer, Business Strategist), automatically refine it through an iterative loop until a quality threshold (85/100) is met, and stream the entire reasoning & loop process to the frontend in real time.

---

## 2. Tech Stack & System Architecture

- **Frontend**: Astro 4.x (SSR Mode) + React 18 + TailwindCSS + Lucide Icons + Mermaid.js (for state machine visualization) + Recharts (for radar scoring chart).
- **Backend**: Python 3.11+ + FastAPI + LangGraph + OpenAI-compatible SDK adapter. The first release supports DeepSeek and GLM through configurable Chat Completions endpoints.
- **Communication Protocol**: Server-Sent Events (SSE) for real-time streaming of structured Agent execution steps, loop iterations, and partial PRD outputs. Hidden model reasoning is never exposed.

### File Structure to Generate:

```text
agentic-prd-architect/
├── backend/
│   ├── main.py                  # FastAPI server with SSE endpoint
│   ├── workflow.py              # LangGraph StateMachine & Loop Logic
│   ├── prompts.py               # System prompts for Generator, Critics, Optimizer
│   ├── schemas.py               # Pydantic data models for State & Output
│   └── requirements.txt         # Python dependencies
├── src/
│   ├── layouts/Layout.astro     # Main Astro layout
│   ├── pages/index.astro        # Main page loading the React Island
│   ├── components/
│   │   ├── AgentDashboard.tsx   # React Island: Main UI container
│   │   ├── AgentTrace.tsx       # Shows structured real-time agent events
│   │   ├── RadarScoreChart.tsx  # Recharts radar chart for Tech/UX/Biz scores
│   │   ├── WorkflowDiagram.tsx  # Dynamic rendering of state machine progress
│   │   └── PRDViewer.tsx        # Render markdown PRD output with version history
├── package.json
└── astro.config.mjs
```

---

## 3. Agentic Loop Architecture & State Machine

### 3.1 State Schema Definition (`backend/schemas.py`)

Define the state `PRDState` using Pydantic / TypedDict:

```python
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class EvaluationResult(BaseModel):
    tech_score: int = Field(..., ge=0, le=100, description="Technical feasibility & edge case score")
    ux_score: int = Field(..., ge=0, le=100, description="UX, loading, and edge case score")
    biz_score: int = Field(..., ge=0, le=100, description="Metrics, ROI, and business strategy score")
    overall_score: int = Field(..., ge=0, le=100, description="Average score")
    tech_feedback: List[str] = Field(default_factory=list, description="Critique on architecture, APIs, errors")
    ux_feedback: List[str] = Field(default_factory=list, description="Critique on loading, empty states, user flows")
    biz_feedback: List[str] = Field(default_factory=list, description="Critique on KPI metrics and feature ROI")

class PRDState(BaseModel):
    user_idea: str
    target_audience: Optional[str] = None
    current_iteration: int = 1
    max_iterations: int = 3
    quality_threshold: int = 85
    
    current_prd: str = ""
    prd_history: List[Dict[str, Any]] = [] # [{"version": 1, "content": "...", "scores": {...}}]
    
    eval_result: Optional[EvaluationResult] = None
    status: str = "IDLE" # "GENERATING", "EVALUATING", "OPTIMIZING", "COMPLETED", "FAILED"
    logs: List[str] = []
    total_tokens_used: int = 0
    estimated_cost_usd: float = 0.0
```

### 3.2 Loop Logic Diagram

```text
[User Input] --> (Node 1: Draft Generator)
                      │
                      ▼
               (Node 2: Multi-Role Evaluator)
                      │
                      ├─── Evaluate: Tech Lead + UX Designer + Biz Strategist
                      │
                      ▼
            [Decision Node: Quality Check]
                      │
       ┌──────────────┴──────────────┐
       │ Score >= 85 OR              │ Score < 85 AND
       │ Iteration >= 3              │ Iteration < 3
       ▼                             ▼
(Node 4: Complete Output)    (Node 3: Optimizer Agent)
                                     │
                                     └──── Feed feedback back to Generator ───┐
                                                                              │
                                     ┌────────────────────────────────────────┘
                                     ▼
                           (Re-run Node 1: Regenerate Draft vN)
```

---

## 4. Prompts Specification (`backend/prompts.py`)

### Generator Agent Prompt:

> You are a Principal Product Manager. Generate a structured, professional PRD in Markdown format for the given idea: "{user_idea}".
> If critique feedback is provided, explicitly fix every single point mentioned in the feedback.
> Structure required:
>
> 1. Product Overview & Core Goal
> 2. Key User Stories & Happy Path
> 3. Technical Constraints & API Contracts
> 4. Edge Cases, Failures, and Recovery Flows (Loading, Empty, Error, Timeout)
> 5. Success Metrics (North Star Metric & Counter-metrics)

### Evaluator Agents Prompt (Structured Output via Function Calling / Structured JSON):

> You are a panel of 3 experts critiquing a PRD draft:
>
> 1. **Tech Lead**: Looks for missing API details, concurrency risks, scaling bottlenecks, data sync issues.
> 2. **UX Designer**: Looks for missing empty states, network latency handling, reverse/cancellation flows, error messaging.
> 3. **Biz Strategist**: Looks for unclear KPIs, lack of guardrail metrics, undefined user value.
>    Output strict JSON with numerical scores (0-100) and actionable bullet points for improvement.

---

## 5. Implementation Steps for Codex

### Step 1: Initialize Backend (`backend/`)

1. Create `requirements.txt` with: `fastapi`, `uvicorn`, `langgraph`, `openai`, `pydantic`, `pydantic-settings`, `sse-starlette`. The OpenAI SDK is used as an OpenAI-compatible client for DeepSeek and GLM.
2. Implement `workflow.py`: Build the LangGraph workflow with Generator, three independent Reviewer nodes, Aggregator, and Optimizer.
3. Implement `main.py`: Create POST endpoint `/api/generate-prd-stream` returning an SSE `EventSourceResponse`. As each node in the LangGraph executes, yield JSON events:
      `json
   {
     "event": "node_execution",
     "data": {
       "node": "evaluate_draft",
       "iteration": 1,
       "prd": "...",
       "scores": {"tech": 65, "ux": 70, "biz": 80, "overall": 71.6},
       "feedback": ["Missing network error fallback logic", "No counter-metric for user retention"],
       "logs": "Running 3-perspective critique agent panel..."
     }
   }
   `

### Step 2: Initialize Frontend (`src/`)

1. Set up Astro with React integration (`npx astro add react tailwind`).
2. Create `AgentDashboard.tsx` with a dual-column layout:
      - **Left Column (Agent Workflow & Telemetry)**:
        - Real-time Status Badge (`IDLE` -> `GENERATING_V1` -> `CRITIQUING` -> `OPTIMIZING_V2` -> `COMPLETED`).
        - **Mermaid.js Diagram**: Highlights the active node dynamically in green.
        - **Recharts Radar Chart**: Shows scores for Tech, UX, and Biz across iterations (v1 vs v2 vs v3).
        - **Token Cost Tracker**: Displays real-time estimated cost ($) and elapsed time (s).
      - **Right Column (Live PRD Stream & Version Toggle)**:
        - Version Selector Tabs (`Draft v1 (71分)`, `Draft v2 (88分) [Selected]`).
        - Live Markdown renderer with custom syntax highlighting.
        - "Download PRD.md" button.

### Step 3: Implement Fallback & Safety Guardrails

1. **JSON Parsing Guardrail**: If the Evaluator Agent returns malformed JSON, automatically retry with a fallback parser (do not break the SSE stream).
2. **Infinite Loop Guardrail**: Hard stop at `max_iterations = 3`, even if the score is below 85.
3. **User Refinement Overrides**: Add a "Pause Loop" button allowing the user to manually edit the prompt before the Optimizer Agent runs.

---

## 6. Verification & Test Plan

Test the complete application with the following prompt:

> **Test Prompt**: _"Build a micro-subscription feature for a podcast app that lets listeners pay $0.10 per episode."_

**Expected Execution Behavior**:

1. **Iteration 1**: Generator creates basic PRD. Evaluator gives ~60-70 points (Critique: _"Missing handling for micropayment gateway failure, network retry logic, and fraud prevention"_).
2. **Iteration 2**: Optimizer Agent receives critique, adds section 4.2 "Gateway Error & Retry Fallbacks". Evaluator re-evaluates -> Scores increase to 88/100.
3. **Completion**: Loop terminates successfully. The Radar Chart updates visually, showing clear score progression from v1 to v2.

---

## 7. Deliverables Checklist for Codex

- [ ] Working FastAPI backend with streaming SSE endpoint.
- [ ] Astro + React frontend with responsive Tailwind design.
- [ ] Live visual rendering of the Agentic Loop (Mermaid state node highlighting + Recharts score comparison).
- [ ] Clean code structure with robust error handling and log telemetry.

---

## 8. Critical Implementation Details & Boilerplate

### 8.1 Backend CORS & Structured Output Config (`backend/main.py` & `backend/workflow.py`)

- **CORS Setup**: FastAPI MUST include CORS middleware allowing `http://localhost:4321` and `[http://127.0.0.1:4321](http://127.0.0.1:4321)`.
- **Structured Output**: For Node 2 (Multi-Role Evaluator), force Pydantic structure using `llm.with_structured_output(EvaluationResult)` or `response_format={"type": "json_object"}`.
- **Mock Mode Support**: Read `ENABLE_MOCK_LLM` from `.env`. If `True`, return pre-canned streaming responses with simulated 2-second delays for visual testing without API costs.

### 8.2 Frontend Dependencies & SSR Directives

- **Additional NPM Packages**: Make sure `package.json` includes `react-markdown`, `remark-gfm`, `mermaid`, `recharts`, `lucide-react`.
- **Astro Island Directives**: In `src/pages/index.astro`, load client-heavy React components with `client:only="react"` to prevent SSR DOM error crashes (`window is not defined`):

  ```astro
  <AgentDashboard client:only="react" />
  Mermaid Initialization: Wrap mermaid.contentLoaded() or mermaid.render() inside a React useEffect with client checking.

  8.3 SSE Wire Format Specification
  Ensure backend yields chunks using standard SSE syntax:
  ```

  data: {"event": "node_execution", "data": {...}}\n\n
  Front-end fetch or EventSource / fetch-event-source MUST handle stream reconnection and render token deltas smoothly.
