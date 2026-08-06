# TaxLens Azure infrastructure

This directory contains the non-applied M6 Terraform foundation for a low-cost
development environment. It creates only shared platform resources:

- resource group;
- Log Analytics workspace;
- private Blob Storage containers for raw and normalized artifacts;
- Basic Azure Container Registry.

PostgreSQL Flexible Server, Container Apps, Key Vault, managed identities, and
Airflow service resources are intentionally separate follow-up modules. They
require the final networking, secret, image, and cost decisions rather than
being provisioned accidentally by the first plan.

## Prerequisites

- Terraform 1.8+;
- Azure CLI;
- an Azure subscription and permission to create resources.

Authenticate with Azure CLI, then provide a subscription ID through a local
`terraform.tfvars` file or `ARM_SUBSCRIPTION_ID`. Do not commit that file.

```powershell
az login
terraform init
terraform fmt -check
terraform validate
terraform plan -var="subscription_id=<subscription-id>"
```

Do not run `terraform apply` until the region, naming prefix, budget, and
PostgreSQL/Airflow deployment design have been explicitly confirmed.

## Phase 2 database inputs

Phase 2 adds a small PostgreSQL Flexible Server (`B_Standard_B1ms`) with the
`vector` extension enabled. Supply the administrator password and, optionally,
your current public IPv4 address without committing them:

```powershell
$env:TF_VAR_postgres_admin_password = "<local-only-password>"
$env:TF_VAR_postgres_allowed_ip = "<your-public-ip>"
```

Leaving `TF_VAR_postgres_allowed_ip` empty creates no firewall rule. The
development server is intentionally public-network enabled for this first
increment; production networking and secret management are later phases.
