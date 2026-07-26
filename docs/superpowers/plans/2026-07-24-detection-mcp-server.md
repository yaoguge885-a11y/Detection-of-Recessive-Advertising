# Detection MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose all seven detection tools through a real MCP server while preserving the LocalToolGateway contract.

**Architecture:** Use the official MCP Python SDK stable v1 low-level Server API because tool schemas already exist dynamically in ToolSpec. Keep a pure DetectionMCPService for mapping names and results; wire it to stdio transport without duplicating analysis logic.

**Tech Stack:** Python 3.10+, `mcp>=1.27,<2`, Pydantic 2, pytest/pytest-asyncio.

## Global Constraints

- One Detection server, not one server per tool.
- Tool business logic remains in existing modules.
- MCP tool names and schemas come from ToolSpec.
- Default tests use local processes only and never require keys or internet.
- MCP errors must not expose private exception text.

---

### Task 1: Dependency and service mapping

**Files:**
- Modify: `implicit-ad-agent/pyproject.toml`
- Create: `implicit-ad-agent/impad/protocols/__init__.py`
- Create: `implicit-ad-agent/impad/protocols/mcp/__init__.py`
- Create: `implicit-ad-agent/impad/protocols/mcp/detection_server.py`
- Create: `implicit-ad-agent/tests/protocols/__init__.py`
- Create: `implicit-ad-agent/tests/protocols/mcp/__init__.py`
- Create: `implicit-ad-agent/tests/protocols/mcp/test_detection_service.py`

**Interfaces:**
- Produces: `DetectionMCPService.list_tools()` and `DetectionMCPService.call_tool()`.
- Consumes: `LocalToolGateway`, `TOOL_SPECS_V1`, `RunContext`.

- [x] **Step 1: Add and install dependency**

Add:

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.27,<2"]
```

Install into the existing venv:

```powershell
.\.venv\Scripts\python.exe -m pip install "mcp>=1.27,<2"
```

- [x] **Step 2: Write failing service tests**

Verify:

- exactly seven MCP names are listed;
- input schema equals ToolSpec input schema;
- output schema equals ToolResult JSON schema;
- calling `detection.analyze_text_intent` returns a valid ToolResult dict;
- unknown MCP names raise a bounded public error.

- [x] **Step 3: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/protocols/mcp/test_detection_service.py -q
```

Expected: missing module.

- [x] **Step 4: Implement service**

Create `DetectionMCPTool` metadata and a service that maps `mcp_name → ToolSpec.name`, delegates to LocalToolGateway, and returns `model_dump(mode="json")`.

- [x] **Step 5: Verify GREEN**

Run the service tests and expect all to pass.

---

### Task 2: Real MCP protocol server and session test

**Files:**
- Modify: `implicit-ad-agent/impad/protocols/mcp/detection_server.py`
- Create: `implicit-ad-agent/tests/protocols/mcp/test_detection_protocol.py`

**Interfaces:**
- Produces: `create_detection_server()` and `run_stdio()`.

- [x] **Step 1: Write failing protocol test**

Use the official SDK to connect a ClientSession to the server, initialize, list tools, and call `detection.analyze_text_intent`. Assert:

```python
assert len(tools.tools) == 7
assert ToolResult.model_validate(result.structuredContent).tool_name == "analyze_text_intent"
```

- [x] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/protocols/mcp/test_detection_protocol.py -q
```

- [x] **Step 3: Implement low-level Server wiring**

Register `list_tools` with each ToolSpec input schema and ToolResult output schema. Register `call_tool` to return structured content. Add stdio `main()` using SDK initialization options.

- [x] **Step 4: Verify GREEN**

Run both MCP test files and expect all to pass.

---

### Task 3: MCP module gate

- [x] **Step 1: Run protocol tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/protocols/mcp -q
```

- [x] **Step 2: Run full suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 3: Compile**

```powershell
.\.venv\Scripts\python.exe -m compileall -q impad/protocols tests/protocols
```

