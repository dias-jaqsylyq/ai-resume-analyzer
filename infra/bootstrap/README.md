# infra/bootstrap

One-time setup, applied locally by the account owner. Everything else is deployed by GitHub Actions.

```bash
cd infra/bootstrap
export AWS_PROFILE=resume-admin
terraform init
terraform plan
terraform apply

gh variable set AWS_ROLE_ARN    --body "$(terraform output -raw role_arn)"
gh variable set AWS_REGION      --body "$(terraform output -raw region)"
gh variable set TF_STATE_BUCKET --body "$(terraform output -raw state_bucket)"
```

State for this stack is local (`terraform.tfstate`, git-ignored). Keep a private backup copy of it.
The state bucket has `prevent_destroy`; remove that block deliberately if you ever tear the project down.
