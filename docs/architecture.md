# SignalHub v1 Architecture

## Goal

Turn public information about target accounts into evidence-backed account intelligence, prioritisation, and sales-ready recommendations with a human review workflow.

## Core flow

Account -> source discovery -> ingestion -> LanceDB retrieval -> claims/signals -> opportunity analysis -> briefs -> deterministic evidence validation -> human review.

## Agents

1. Research Agent: discovers and collects relevant sources.
2. Signal Agent: extracts structured signals from evidence.
3. Opportunity Agent: turns verified intelligence into potential Mastek opportunity areas.
4. Brief Agent: produces detailed pre-sales and concise sales briefs from verified evidence.

The Evidence Validator is deterministic and sits outside the agent layer.

## Storage

PostgreSQL stores application/domain data. LanceDB stores document chunks, embeddings, and retrieval metadata.

## External connector

HubSpot is the first external integration. It is isolated behind a connector boundary so future sources can be added without changing the domain model.

## Automation

Scheduled refresh, content-hash change detection, signal-triggered alerts/research requests, and weekly account-change digests.
