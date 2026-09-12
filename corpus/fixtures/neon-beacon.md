# Neon Beacon Fixture

This document exists only so the local RAG smoke test has a known fact to retrieve.

## Project identity

The internal project beacon code for **nemoclaw-rag-base** is `NEON-BEACON-42`.

Operators should be able to ask "What is the project beacon code?" and recover that exact token from the index without calling a model.

## Stack notes

- NemoClaw orchestrates onboarding and lifecycle.
- OpenShell provides the sandbox, gateway, and policy surface.
- Hermes is the default agent profile for this base project.
- OpenClaw remains available as an alternate harness profile.
