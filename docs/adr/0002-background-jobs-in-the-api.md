# ADR 0002: Run long jobs inside the API, polled by Airflow

## Context

Collection, OCR, and embedding take from minutes to several hours. They need Tesseract
and the embedding model, which are already in the API image. Azure Container Apps
closes HTTP requests after 240 seconds, and the API scales to zero when idle.

The first design had each Airflow task hold one HTTP request open for the whole job.
Any job longer than 240 seconds (OCR of a single long scan) failed, and the API then
scaled down and killed the orphaned process.

## Decision

The API starts each job as a subprocess and returns a job ID at once. Airflow polls the
job every 20 seconds, printing new output lines into the task log, until it completes or
fails. An identical request to a running job reattaches to it. Jobs run at lower CPU
priority than requests and are limited to six hours.

## Consequences

- No extra always-on worker; the API image stays the only place with OCR and the model.
- Polling keeps the API awake during a job, so scale-to-zero needs no special handling.
- Jobs share the API's single vCPU and 2 GiB of memory with web requests, so job code
  must keep memory bounded (embedding pages through chunks instead of loading them all).
- An API restart loses running jobs. Every script is resumable, so Airflow's retry
  continues the work.
- Two different jobs can run at once (the daily DAG and a maintenance run); avoid
  overlapping long backfills with the 10:00 (+07) daily run.

## Revisit trigger

Jobs regularly approach six hours, or OCR load makes the site noticeably slow. The next
step is a Container Apps Job running the same image and scripts.
