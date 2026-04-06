# Contributing

## About this project

The **PMO Intelligence Engine** was created by **Kevin Blanco** — Senior Developer Advocate at Asana and Google Developer Expert (Cloud & AI/ML) — as a live demo for Google Cloud Next.

It demonstrates how A2A (Agent-to-Agent), MCP (Model Context Protocol), Vertex AI / Google ADK, BigQuery, and Asana can be combined into a production-grade enterprise AI pipeline.

## How to contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-idea`)
3. Make your changes and ensure all Dockerfiles build
4. Run `python bigquery/seed_data.py` to verify BigQuery integration
5. Open a pull request with a clear description of your changes

## Code conventions

**Asana API calls:** All calls to the Asana REST API must use the [Asana Python SDK](https://github.com/Asana/python-asana/) (`asana>=5.0.0`), not raw HTTP clients. Use `asana.TasksApi`, `asana.WebhooksApi`, `asana.StoriesApi`, etc.

**httpx exceptions:** Two files intentionally use `httpx` instead of the SDK — both are calling OAuth2 token endpoints (`/-/oauth_token`), not the Asana REST API:
- `agents/asana_context/token_manager.py` — MCP OAuth token refresh
- `asana/mcp_auth_setup.py` — one-time PKCE authorization code exchange

`httpx` is also used in `agents/orchestrator/a2a_client.py` for A2A calls between our own Cloud Run agents, which has nothing to do with Asana. Do not replace these with the SDK.

## Authorship note

This project is authored by Kevin Blanco in his capacity as a Google Developer Expert and Asana Developer Advocate. Contributions are welcome from the community under the Apache 2.0 license.

## Code of conduct

Be respectful, constructive, and collaborative. This is a community resource.
