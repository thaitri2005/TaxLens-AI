# TaxLens Azure infrastructure

This directory contains the non-applied M6 Terraform foundation for a low-cost
development environment. It creates only shared platform resources:

- resource group;
- Log Analytics workspace;
- private Blob Storage container for raw and normalized artifacts;
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
