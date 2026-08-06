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

The release workflow does not run `terraform apply`. The current Terraform
state is local to the development workspace, so automatic apply from GitHub
Actions would risk creating competing state. Configure a remote Azure Blob
Terraform backend and protected deployment environment before adding an
automated plan/apply workflow. Until then, update the ignored
`infra/terraform/terraform.tfvars`, run the reviewed local Terraform plan, and
approve the apply explicitly.
