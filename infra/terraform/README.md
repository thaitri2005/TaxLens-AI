# TaxLens Azure infrastructure

This directory contains the applied M6 Terraform infrastructure for a low-cost
development environment. It currently manages:

- resource group;
- Log Analytics workspace;
- private Blob Storage containers for raw and normalized artifacts;
- Basic Azure Container Registry;
- PostgreSQL Flexible Server with the `vector` extension;
- Key Vault, managed identity, and scoped RBAC assignments.

Container Apps and Airflow service resources remain separate follow-up phases.
They require the final networking, image, and cost decisions rather than being
provisioned accidentally by an earlier plan.

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
the proposed resource changes have been explicitly reviewed.

Phase 3 adds Key Vault, a user-assigned application identity, and RBAC for
secrets, Blob Storage, and ACR pull access. The Hugging Face token is supplied
through the ignored `terraform.tfvars` file and becomes a Key Vault secret.
Terraform state contains sensitive secret resource values and must be stored
privately when remote state is introduced.

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
