# CI/CD workflow

TaxLens uses GitHub Actions for repeatable validation and manually controlled
Azure image releases.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`:

- Ruff, MyPy, and Pytest for the backend;
- a production Next.js build;
- Terraform provider initialization, formatting, and validation without a
  backend or cloud mutation.

The CI credentials used for the frontend build are test-only placeholders.
They never contain production authentication or inference secrets.

## Image releases

`.github/workflows/release-images.yml` is manually triggered and protected by
the `azure-release` GitHub environment. It uses Azure OIDC and requires these
repository/environment secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

The workflow publishes API, web, and Airflow images under an immutable commit
SHA tag by default. A release summary prints the three image references for
the reviewed Terraform update.

## Infrastructure apply boundary

Terraform state now uses the private Azure Blob backend configured in
`infra/terraform/versions.tf`. The one-time migration must be completed from a
local authenticated shell with `terraform init -migrate-state`; answer `yes`
when Terraform asks to copy the existing local state. Do not delete the local
state until the remote state can be listed and a read-only plan succeeds.

`.github/workflows/deploy.yml` accepts an already-published image tag, creates
temporary Terraform variables from GitHub secrets, initializes the remote
backend, and produces a reviewable plan artifact. Set `apply` to `true` only
when the plan is approved; the apply job is protected by the `azure-deploy`
GitHub environment.

Configure these additional GitHub secrets before using the deployment workflow:
`TF_VAR_POSTGRES_ADMIN_PASSWORD`, `TF_VAR_HF_TOKEN`,
`TF_VAR_AUTH_INTERNAL_TOKEN`, `TF_VAR_NEXTAUTH_SECRET`,
`TF_VAR_AIRFLOW_ADMIN_PASSWORD`, `TF_VAR_AIRFLOW_INTERNAL_TOKEN`, and
optionally `TF_VAR_POSTGRES_ALLOWED_IP` to preserve the development PostgreSQL
firewall rule.
The GitHub OIDC principal also needs `Storage Blob Data Contributor` on the
Terraform state storage account. The local developer role assignment does not
automatically grant that permission to GitHub Actions.
