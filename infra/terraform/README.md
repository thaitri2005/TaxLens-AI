# TaxLens Azure infrastructure

Terraform for the development environment in `taxlens-dev-rg`. What it creates and how
it is configured is described in [docs/deployment.md](../../docs/deployment.md).

| File | Contents |
| --- | --- |
| `main.tf` | Resource group, Log Analytics, storage (Blob containers, Airflow log share), Container Registry, PostgreSQL with `vector`, Key Vault and secrets, managed identity and RBAC, API and web Container Apps |
| `airflow.tf` | Airflow metadata database, scheduler and webserver Container Apps (when `airflow_enabled`) |
| `variables.tf`, `outputs.tf`, `versions.tf` | Inputs, outputs, providers, and the remote state backend |

## Normal use

Deployments run through GitHub Actions (**Plan or deploy Azure infrastructure**), which
supplies the image tags and secrets; see [docs/ci-cd.md](../../docs/ci-cd.md). Run
Terraform locally only to inspect or recover.

## Local use

Requires Terraform 1.8+ and the Azure CLI. State is in the private `terraform-state`
container of `taxlensdevartifacts`, authenticated with Azure AD; your identity needs
`Storage Blob Data Contributor` on that account.

```powershell
az login
terraform init
terraform plan
```

Put inputs in an ignored `terraform.tfvars` (never commit it):

```hcl
subscription_id         = "<subscription id>"
postgres_admin_password = "<password>"
postgres_allowed_ip     = ""            # your public IP for laptop runs, or empty
hf_token                = "<Hugging Face token>"
auth_internal_token     = "<random secret>"
nextauth_secret         = "<random secret>"
api_image               = "taxlensdevacr.azurecr.io/taxlens-api:<commit sha>"
web_image               = "taxlensdevacr.azurecr.io/taxlens-web:<commit sha>"
airflow_enabled         = true
airflow_image           = "taxlensdevacr.azurecr.io/taxlens-airflow:<commit sha>"
airflow_admin_password  = "<password>"
airflow_internal_token  = "<random secret>"
```

Review every plan before `terraform apply`. State contains secret values, which is why it
is kept only in the private backend.

For a laptop collection run, prefer a temporary firewall rule with the Azure CLI
([docs/operations.md](../../docs/operations.md)) over changing `postgres_allowed_ip`.
