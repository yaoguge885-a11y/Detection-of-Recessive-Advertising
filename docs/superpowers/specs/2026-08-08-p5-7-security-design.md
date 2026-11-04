# P5.7 Security Boundary Design

**Date:** 2026-08-08

**Status:** Proposed for written review

**Scope owner:** non-M1 engineering member

**Target effort:** 2-3 person-days

## 1. Goal

Close the P5.7 engineering security gate before any real Xiaohongshu,
Bilibili, or other platform URL adapter is enabled. The implementation must
make the requested controls executable and testable rather than documenting
them as future conventions.

P5.7 completion must prove all of the following:

1. every HTTP redirect target is revalidated before the next request;
2. DNS results cannot move a request onto loopback, link-local, private,
   reserved, or otherwise non-global addresses;
3. URL credentials, explicit ports, query strings, and fragments never leak
   into display, log, report, or run artifacts;
4. page content remains untrusted data and cannot become a system message;
5. page text cannot directly authorize or invoke tools;
6. URL-import media references cannot escape an approved cache root or use an
   unsafe/unsupported reference scheme;
7. MCP and the future A2A transport share timeout, allowlist, identity, and
   result-contract checks;
8. logs, readable reports, API/export results, and run JSON files do not leak
   Cookies, Tokens, authorization values, or original sensitive URLs.

The focused pre-change security-related regression baseline is `77 passed`
across current platform URL, MCP, Function Calling, service persistence, and
`PostRecord` tests. That baseline proves only that existing behavior is
stable; it does not close the missing controls above.

## 2. Explicit scope boundary

This design uses the user-approved boundary A:

- implement the security policy and an executable remote-capability boundary
  now;
- test the future A2A path with an injected fake transport using the same
  authorization and validation code;
- do not implement P5.5 agent discovery, remote task lifecycle, network
  transport, deployment, or a local-vs-A2A comparison;
- do not claim that a real remote A2A end-to-end call exists;
- do not connect to a real platform URL during P5.7 verification;
- do not change M1, M4, or M5 status.

P5.7 is an engineering security gate. Passing it is not formal M1 data
acceptance, P5.5 A2A completion, or M5 product acceptance.

## 3. Design principles

### 3.1 Fail closed at trust-boundary violations

Unsafe destinations, DNS policy violations, redirect-policy violations,
unregistered capability names, authorization failures, forged remote
identities, invalid result envelopes, and unsafe media references must fail
closed with stable public error codes.

Only transport failures such as timeout, process termination, or connection
failure may use an explicitly configured local fallback. A policy or protocol
violation must never be converted into a local execution through the fallback
path.

### 3.2 Validate at the point of use

Syntax validation alone does not establish a safe network destination. The
address used by the transport must be one of the addresses validated for that
request. Redirects start a new validation cycle.

### 3.3 Separate untrusted content from authority

Platform HTML, extracted post text, comments, captions, OCR, and metadata are
data. They do not define system prompts, capability grants, tool names,
runtime modes, or policy values.

### 3.4 Redact once at a shared outbound boundary

Analysis may use the normalized raw content in process memory, but every
persisted or user-exportable representation must pass through the same
recursive redactor. Individual report fields must not each invent their own
partial redaction rules.

## 4. Components

### 4.1 URL syntax and destination policy

Extend `impad/adapters/platforms/url_safety.py` so URL validation has two
explicit phases:

1. `validate_public_https_url()` performs deterministic syntax validation:
   HTTPS only, no credentials, no non-default port, normalized host, no
   fragment in the fetch URL, and a secret-free display representation.
2. an injected DNS resolver resolves the normalized host immediately before
   use. Empty results and any non-global address reject the entire target,
   including mixed public/private answer sets.

The resolved target records the normalized hostname, validated address set,
chosen connection address, secret-free display URL, and a SHA-256 source
reference. It does not expose raw credentials, query strings, or fragments in
its representation or exception text.

The transport receives the exact validated connection address and the
original normalized hostname separately. TLS verification and the HTTP Host
header continue to use the hostname; socket connection uses the validated
address. This prevents the HTTP stack from performing an unvalidated second
DNS lookup.

DNS answer rotation is allowed only when every answer remains global and the
transport connects to an address from the answer set validated for that
specific request. A public-to-private or mixed answer fails before network
I/O.

### 4.2 Redirect-safe fetcher

Add `impad/adapters/platforms/safe_fetch.py` with a small injectable boundary:

- `DNSResolver` resolves a hostname to address strings;
- `HTTPTransport.request_once()` performs exactly one request, never follows
  redirects, and connects to the supplied validated address;
- `SafeURLFetcher.fetch()` coordinates validation, resolution, the request,
  response-size limits, and redirect handling.

The fetcher:

- accepts at most five redirects;
- handles only the standard redirect statuses 301, 302, 303, 307, and 308;
- resolves a relative `Location` against the current URL;
- reruns URL syntax, port, credential, hostname, and DNS validation for every
  redirect target;
- rejects missing/malformed `Location`, redirect loops, excess redirects, and
  unsafe destinations with stable error codes;
- never includes raw `Location` or the source URL in public errors;
- applies a 10-second timeout to each hop and a 5 MiB
  (`5 * 1024 * 1024` byte) maximum to the final page response;
- returns content plus a safe final display URL and source hash, not a raw
  redirect history.

Change the platform adapter boundary to
`preview(source, *, fetcher: SafeURLFetcher) -> PostRecord`, and make
`URLImportService` supply its configured fetcher. Fixture adapters may ignore
the fetcher because they perform no network I/O. Real platform adapters must
use the injected fetcher and must not turn automatic redirect following back
on. P5.3/P5.4 adapters will be admitted only if every URL request enters
through this boundary.

### 4.3 Untrusted page-content envelope

Add `impad/security/content_boundary.py` with an immutable untrusted-content
envelope and one message builder for any future LLM-backed platform parsing.

The builder has these invariants:

- the system message is a code-owned constant;
- platform content is JSON-serialized as data in a user message;
- no platform field can supply a message role, system instruction, tool name,
  capability grant, or runtime mode;
- content containing strings such as `ignore previous instructions`, forged
  `<system>` tags, JSON tool calls, or A2A/MCP names remains byte-for-byte data
  in the user payload and is absent from all system messages.

The current deterministic `AnalysisService` does not call an LLM. Integration
tests must also prove that malicious post text alone does not produce a tool
call: tools execute only from an explicit `FunctionCallRequest` after the
existing planner and restricted caller authorize it.

This control is role separation plus capability enforcement. It does not
claim that keyword filtering can solve prompt injection.

### 4.4 Platform media-reference policy

Add `impad/adapters/platforms/media_safety.py` and apply it to adapter output
inside `URLImportService.preview()` before a preview is stored.

For URL-imported posts, an accepted media reference is exactly one of:

- an HTTPS reference whose URL and DNS destination pass the same public-target
  policy; or
- a relative cached-file path that resolves inside an explicitly configured
  cache root.

Reject:

- absolute local paths;
- `..` traversal after normalization;
- Windows drive, UNC, device, or alternate-data-stream paths;
- `file:`, `data:`, `javascript:`, FTP, and unknown schemes;
- NUL/control characters and overlong references;
- local paths when no cache root was configured;
- local symlink resolution that escapes the cache root;
- media type/reference combinations outside the runtime contract.

This policy is scoped to platform URL import. It does not silently remove the
existing manual-input ability to refer to a user-selected local image.

### 4.5 Shared MCP/future-A2A remote capability policy

Add `impad/orchestration/remote_policy.py` with protocol-neutral policy types
used directly by `MCPToolGateway` and exercised with a fake future A2A
transport.

Each remote call has:

- a requested local capability name;
- its registered remote name and input schema;
- an explicit per-run set of allowed capabilities;
- a positive deadline;
- the expected result capability name and envelope type.

The existing MCP client default remains 30 seconds. A shorter positive
per-call deadline in `RunContext` takes precedence. Fake-A2A security tests
use the same 30-second default without defining a real A2A transport. A
validated remote structured result may serialize to at most 1 MiB
(`1024 * 1024` bytes).

Before transport, the policy rejects unknown, unavailable, or ungranted
capabilities and unexpected arguments. After transport, it rejects results
whose capability/tool identity does not match the request, whose envelope
does not validate, or whose payload exceeds configured limits.

`MCPToolGateway` must distinguish:

- transport timeout/offline/process failure: optionally run the same
  registered local tool, increment fallback count, and record
  `mcp_transport_fallback`;
- authorization/protocol/identity failure: raise a stable fail-closed error,
  do not execute locally, and do not expose registry internals or remote
  payloads.

The fake A2A transport tests use the same policy to prove timeout, forged
capability/agent identity, unregistered names, and calls outside the grant are
rejected. This is P5.7 evidence for the future A2A boundary, not P5.5 transport
acceptance.

### 4.6 Shared output redaction and artifact scanner

Add `impad/security/redaction.py` with recursive redaction for mappings,
sequences, Pydantic dumps, and free text.

The redactor must cover:

- `Cookie` and `Set-Cookie` header forms;
- bearer/basic authorization values;
- access/refresh tokens, API keys, passwords, secrets, and session values;
- URLs containing credentials, explicit ports, query strings, or fragments;
- URL-encoded variants of the sensitive components;
- nested values in post text, comments, captions, media metadata, evidence,
  limitations, run events, and exception summaries.

Do not redact benign metrics such as `token_usage` merely because their field
name contains the word `token`. Sensitive-key matching is explicit and
bounded.

Apply the redactor before:

- `AnalysisResult` becomes an API/export result;
- `render_readable_report()` returns Markdown;
- `JsonRunStore.put()` serializes a run record;
- a public error or security event is emitted.

Keep source traceability through SHA-256 references and safe URLs. The exact
original sensitive URL and secret values must not be persisted.

Add `scripts/security/scan_p5_7_artifacts.py`. The scanner checks generated
`.json`, `.jsonl`, `.md`, and `.log` artifacts for secret/header patterns and
sensitive URLs. Findings contain only path, rule identifier, line number,
match length, and match hash; the scanner never echoes the matched secret.

## 5. Stable public failures

The implementation uses stable codes without embedding unsafe values:

| Code | Meaning |
| --- | --- |
| `unsafe_url_destination` | literal or DNS-resolved destination is non-global |
| `dns_resolution_failed` | no usable DNS result was produced |
| `unsafe_redirect` | redirect target or redirect metadata violates policy |
| `redirect_limit_exceeded` | redirect budget was exhausted |
| `response_too_large` | response exceeded the configured byte limit |
| `unsafe_media_reference` | URL-import media reference violates policy |
| `capability_not_allowed` | request is outside the explicit grant |
| `remote_protocol_violation` | remote identity or result contract is forged/invalid |
| `remote_timeout` | remote deadline elapsed and no permitted fallback succeeded |

Existing URL syntax codes such as `unsafe_url_scheme`,
`unsafe_url_authority`, and `unsafe_url_port` remain stable.

## 6. Test strategy and required evidence

All behavior changes use red-green TDD. Network tests use injected resolvers
and one-hop transports and do not contact the public Internet.

| Requirement | Required executable evidence |
| --- | --- |
| Redirect revalidation | public first hop redirecting to loopback, private IPv4/IPv6, credentialed URL, non-443 port, malformed/missing location, loop, and sixth hop all fail before the second unsafe request |
| DNS change/private blocking | public answer succeeds through its pinned address; private-only and mixed public/private answers fail; redirect host is resolved separately; transport never receives an unvalidated address |
| URL redaction | credential, port, query, fragment, encoded query value, and redirect location sentinels are absent from exceptions, preview JSON, API result, report, run JSON, and scanner output |
| Prompt isolation | malicious platform text occurs only in the user/data message; system message remains the exact static constant; analyzing malicious text without explicit calls executes no injected tool |
| Media safety | `../`, absolute, drive, UNC, device, ADS, `file:`, `data:`, private HTTPS, cache-root escape, and escaping symlink references fail; safe public HTTPS and in-root cache paths pass |
| MCP security | timeout/offline may auditably fall back; unknown/ungranted request, forged returned tool name, invalid envelope, and oversized payload fail closed without local execution |
| Future A2A security | fake A2A timeout, unknown/ungranted capability, forged agent/capability identity, and invalid result use the same policy and fail closed |
| Artifact secrecy | a malicious post containing Cookie, bearer token, API key, sensitive URL, encoded secret, comment/caption/evidence leakage produces sanitized API/report/run artifacts; scanner exits zero and no sentinel is present |

Tests must assert both the public result and negative side effects: adapter,
transport, fallback gateway, tool, or run-store calls that should not happen
must have a verified call count of zero.

## 7. Verification gates

P5.7 may be marked engineering-complete only when all of these are true:

1. each row in Section 6 has focused passing tests;
2. every new test was observed failing for the intended missing behavior
   before implementation;
3. the focused P5.7 suite passes;
4. the full default zero-key suite passes without a new warning;
5. `compileall`, `pip check`, and `git diff --check` pass;
6. the artifact scanner passes against malicious generated run/report/log
   fixtures and the actual test-output directory;
7. `HANDOFF.md`, `docs/已有功能测试指令库.md`, and
   `docs/隐性广告识别项目_分阶段计划表.md` record commands, current counts,
   exact covered controls, and the P5.5/M1/M4/M5 non-claims;
8. no real platform request, Cookie, token, or original sensitive URL is added
   to the repository.

## 8. Non-goals

- real Xiaohongshu or Bilibili capture;
- bypassing login, CAPTCHA, anti-bot, or platform controls;
- saving or replaying browser Cookies;
- a complete remote A2A implementation;
- replacing the existing tool implementations;
- adding RBAC/accounts, a general sandbox, or an external security proxy;
- changing CreatorShift, formal Gold data, M1, M4, or research metrics;
- claiming that prompt injection is solved by string filtering.
