# ADR 0003: Collect the Ministry of Finance database from a machine in Vietnam

## Context

The Ministry of Finance database (`vbpq.mof.gov.vn`) is the best tax source: it records
legal status and effective dates, and about half its files are Word documents that need
no OCR. From Azure (East Asia, Hong Kong) its TCP connections time out, while the same
API answers in seconds from a Vietnamese network. The site appears to accept Vietnamese
IP addresses only, and Azure has no region in Vietnam.

## Decision

Ministry collection runs from a laptop in Vietnam, writing directly to the Azure
PostgreSQL database and Blob Storage (`collect_sources.py --source mof`). It only lists
and downloads; OCR and embedding then run in Azure through the `process_and_embed`
maintenance action. Airflow collects only from the government portal, which is reachable
from Azure.

## Consequences

- No proxy or VPN to pay for or maintain.
- New Ministry documents are not collected automatically; someone runs the command
  occasionally. Recent documents still arrive daily through the government portal.
- The laptop's public IP must be allowed in the PostgreSQL firewall during the run, and
  the rule should be removed afterwards.
- The script checks the database and storage before its ten-minute listing, caches the
  listing for 24 hours, and tolerates a dropped connection per document.

## Revisit trigger

Ministry updates need to be automatic. The alternative is a small proxy hosted in
Vietnam that Airflow's collection job calls.
