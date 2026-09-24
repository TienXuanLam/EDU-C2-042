# EDU-C2-042 — Education Learning-Resource Metadata Exchange Validator Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: EDU (education)

## Overview

Validates a learning-resource catalogue export (JSON/XML/CSV) submitted by a
curriculum coordinator, LMS content admin, digital textbook publisher, or
education-board data officer against an institution-approved exchange profile,
curriculum code list, and controlled vocabulary/accessibility rules, then produces a
structured Markdown report with per-record findings, severity, and advisory
LLM-drafted remediation hints. The agent is strictly read-only/advisory: it never
publishes, licenses, alters, or transmits any resource or catalogue record, and it
processes resource discovery metadata only — no student/learner data or PII is
involved.

**The bundled exchange profile, curriculum code list, controlled vocabulary, and
accessibility profile in `config/config.yaml` are illustrative, not sourced
institutional data.** No concrete approved profile, curriculum code list, or
vocabulary table from a real institution/MEXT/publisher was available at build time.
Every deploying institution must supply and review its own approved profile/code-list/
vocabulary pack before relying on this agent's output for real cross-institution
exchange decisions.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |
| Azure OpenAI | A resource with a chat-capable deployment — `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` |

```bash
pip install -e .
```

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and operational documentation
```

See `docs/` for the design spec and test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
