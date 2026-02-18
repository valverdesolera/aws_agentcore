# Phase 1 — Infrastructure & Auth Foundation

## Summary

Provision all cloud infrastructure with Terraform so every subsequent phase has a stable, deployable target. This phase sets up the AWS Cognito user pool for user authorization, IAM roles for AgentCore execution, an ECR repository for the container image, and lays the groundwork for AgentCore Runtime deployment.

---

## Deployment Model

> **Important clarification:** The reviewer will run the Jupyter notebook against **your already-deployed endpoint** — they are not expected to run `terraform apply` themselves. The README deployment instructions exist for reproducibility/audit purposes. You deploy once to your own AWS account, keep the endpoint live, and the notebook's configuration cell is pre-filled with your live endpoint URL and Cognito pool IDs.

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| Terraform | >= 1.5 |
| AWS Provider for Terraform | >= 5.x |
| AWS CLI | v2, configured with credentials |
| AgentCore CLI (`bedrock-agentcore-starter-toolkit`) | Installed via pip — see Setup below |
| AWS Account | With permissions for Cognito, IAM, ECR, Bedrock AgentCore |

---

## Setup

### 0. Install Required CLIs

Both CLIs must be installed and configured before any infrastructure work begins.

**AWS CLI v2:**
```bash
# macOS (Homebrew)
brew install awscli

# Verify
aws --version   # expected: aws-cli/2.x.x
```

AWS CLI is already installed (`aws-cli/2.28.6`) and the `juanvalsol` profile is configured:

```
Profile:    juanvalsol
Account ID: 531241048046
IAM User:   example_dev
Region:     us-east-1
```

To use this profile for all commands:
```bash
export AWS_PROFILE=juanvalsol

# Verify identity
aws sts get-caller-identity
```

**AgentCore CLI (bedrock-agentcore-starter-toolkit):**
```bash
# Install into the project virtual environment (Python 3.10.14)
# The .venv is already created and AgentCore CLI is installed:
.venv/bin/pip install bedrock-agentcore-starter-toolkit

# When the venv is activated, you can call it directly:
source .venv/bin/activate
agentcore --help
```

> **Local environment:** The project uses Python 3.10.14 (set via `.python-version`) with a `.venv` virtual environment. AgentCore CLI (`bedrock-agentcore-starter-toolkit==0.3.0`) and its dependencies are already installed in `.venv`.

---

### 1. Terraform Project Structure

```
infrastructure/
├── main.tf                # Root module, provider configuration
├── variables.tf           # Input variables (region, project name, Langfuse keys)
├── outputs.tf             # Exported values (Cognito pool ID, client ID, ECR URL, secret ARN)
├── cognito.tf             # Cognito user pool + client
├── iam.tf                 # IAM roles and policies for AgentCore
├── ecr.tf                 # ECR repository for container image
├── secrets.tf             # Secrets Manager secret for Langfuse credentials
└── terraform.tfvars       # Environment-specific variable values (gitignored)
```

### 2. Provider Configuration

```hcl
# main.tf
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
```

### 3. Variables

```hcl
# variables.tf
variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used as prefix for resource naming"
  type        = string
  default     = "teilur-stock-agent"
}
```

---

## Requirements

### A. AWS Cognito User Pool

The Cognito user pool handles inbound user authorization. Users authenticate against this pool and receive JWT tokens used to call the FastAPI endpoint.

**Terraform resource:** `aws_cognito_user_pool`

```hcl
# cognito.tf
resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-user-pool"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = {
    Project = var.project_name
  }
}
```

**Terraform resource:** `aws_cognito_user_pool_client`

```hcl
resource "aws_cognito_user_pool_client" "app_client" {
  name         = "${var.project_name}-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  supported_identity_providers = ["COGNITO"]
}
```

**Key outputs needed by later phases:**
- `cognito_user_pool_id` — used by the AgentCore authorizer config (`--authorizer-config`) and local FastAPI JWT validation
- `cognito_user_pool_client_id` — used by the AgentCore authorizer config and by clients (notebook) to authenticate
- `cognito_user_pool_endpoint` — the issuer URL for JWT validation (format: `cognito-idp.REGION.amazonaws.com/POOL_ID`)

**Reference:**
- Terraform `aws_cognito_user_pool`: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cognito_user_pool
- Terraform `aws_cognito_user_pool_client`: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cognito_user_pool_client
- AWS Cognito JWT docs: https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-with-identity-providers.html

---

### B. IAM Roles

AgentCore Runtime requires an execution role with permissions to invoke Bedrock models, pull from ECR, and write CloudWatch logs.

```hcl
# iam.tf
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "agentcore_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "agentcore_execution" {
  name               = "${var.project_name}-agentcore-execution"
  assume_role_policy = data.aws_iam_policy_document.agentcore_assume_role.json

  tags = {
    Project = var.project_name
  }
}

resource "aws_iam_role_policy_attachment" "bedrock_full" {
  role       = aws_iam_role.agentcore_execution.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
}
# NOTE: AmazonBedrockFullAccess is used here for development convenience.
# For production, replace with a scoped inline policy granting only:
#   bedrock:InvokeModel, bedrock:InvokeModelWithResponseStream
# on specific model ARNs. See the official AgentCore Runtime permissions docs:
# https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html
```

> **Security note:** The trust policy includes `aws:SourceAccount` and `aws:SourceArn` conditions as recommended by the [AgentCore IAM docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html) to prevent cross-account confused deputy attacks.

**Required inline policies for AgentCore Runtime execution:**

The following policy grants the permissions that AgentCore Runtime needs to operate (ECR image pull, CloudWatch Logs, X-Ray tracing, CloudWatch metrics, and Secrets Manager access):

```hcl
# iam.tf (required — AgentCore Runtime operational permissions)
data "aws_iam_policy_document" "agentcore_runtime_ops" {
  # ECR image pull
  statement {
    sid     = "ECRImageAccess"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.agent.arn]
  }

  statement {
    sid       = "ECRTokenAccess"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # CloudWatch Logs
  statement {
    sid     = "LogsCreateGroup"
    actions = [
      "logs:DescribeLogStreams",
      "logs:CreateLogGroup",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
    ]
  }

  statement {
    sid       = "LogsDescribeGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
  }

  statement {
    sid     = "LogsWriteEvents"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
    ]
  }

  # X-Ray tracing
  statement {
    sid = "XRayAccess"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets",
    ]
    resources = ["*"]
  }

  # CloudWatch metrics
  statement {
    sid       = "CloudWatchMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }
}

resource "aws_iam_role_policy" "agentcore_runtime_ops" {
  name   = "${var.project_name}-runtime-ops"
  role   = aws_iam_role.agentcore_execution.id
  policy = data.aws_iam_policy_document.agentcore_runtime_ops.json
}
```

Additional permissions for Secrets Manager access are defined separately below (section C).

---

### C. AWS Secrets Manager

Store Langfuse credentials in Secrets Manager so they can be fetched at runtime by the AgentCore container — no plaintext secrets in environment variable flags.

**Terraform variable (value comes from `.tfvars` or CLI, never hardcoded):**

```hcl
# variables.tf (addition)
variable "langfuse_secret_key" {
  description = "Langfuse secret key (sk-lf-...)"
  type        = string
  sensitive   = true
}

variable "langfuse_public_key" {
  description = "Langfuse public key (pk-lf-...)"
  type        = string
  sensitive   = true
}

variable "langfuse_base_url" {
  description = "Langfuse base URL"
  type        = string
  default     = "https://us.cloud.langfuse.com"
}
```

**Secrets Manager resource:**

```hcl
# secrets.tf
resource "aws_secretsmanager_secret" "langfuse" {
  name        = "${var.project_name}/langfuse"
  description = "Langfuse API keys for the stock agent"

  tags = {
    Project = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "langfuse" {
  secret_id = aws_secretsmanager_secret.langfuse.id
  secret_string = jsonencode({
    LANGFUSE_SECRET_KEY = var.langfuse_secret_key
    LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
    LANGFUSE_BASE_URL   = var.langfuse_base_url
  })
}
```

**IAM policy granting the AgentCore execution role access to this secret:**

Add to `iam.tf` (after the existing role and attachment):

```hcl
# iam.tf (addition)
data "aws_iam_policy_document" "agentcore_secrets" {
  statement {
    sid       = "AllowLangfuseSecretRead"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.langfuse.arn]
  }
}

resource "aws_iam_role_policy" "agentcore_secrets" {
  name   = "${var.project_name}-secrets-policy"
  role   = aws_iam_role.agentcore_execution.id
  policy = data.aws_iam_policy_document.agentcore_secrets.json
}
```

**Output:**

```hcl
# outputs.tf (addition)
output "langfuse_secret_arn" {
  value = aws_secretsmanager_secret.langfuse.arn
}
```

**Supply the secret values at apply time (never commit to git):**

```bash
# terraform.tfvars  ← gitignored
langfuse_secret_key = "sk-lf-REPLACE-WITH-YOUR-SECRET-KEY"
langfuse_public_key = "pk-lf-REPLACE-WITH-YOUR-PUBLIC-KEY"
```

Or pass them via CLI:

```bash
terraform apply \
  -var="langfuse_secret_key=$LANGFUSE_SECRET_KEY" \
  -var="langfuse_public_key=$LANGFUSE_PUBLIC_KEY"
```

> **Add `terraform.tfvars` to `.gitignore`** alongside `.env`.

---

### D. ECR Repository

Container registry for the FastAPI application image that will be deployed to AgentCore Runtime.

```hcl
# ecr.tf
resource "aws_ecr_repository" "agent" {
  name                 = "${var.project_name}-agent"
  image_tag_mutability = "MUTABLE"
  force_delete         = true  # Allows terraform destroy even if images exist

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = {
        type = "expire"
      }
    }]
  })
}
```

**Reference:** https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecr_repository

---

### E. Outputs

```hcl
# outputs.tf
output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "cognito_user_pool_client_id" {
  value = aws_cognito_user_pool_client.app_client.id
}

output "cognito_user_pool_endpoint" {
  value = aws_cognito_user_pool.main.endpoint
}

output "ecr_repository_url" {
  value = aws_ecr_repository.agent.repository_url
}

output "ecr_repository_name" {
  value = aws_ecr_repository.agent.name
}

output "agentcore_execution_role_arn" {
  value = aws_iam_role.agentcore_execution.arn
}

output "langfuse_secret_arn" {
  value = aws_secretsmanager_secret.langfuse.arn
}
```

---

## Implementation Notes

1. **AgentCore Runtime is provisioned via the AgentCore CLI** (`agentcore configure` + `agentcore deploy`), not directly through Terraform. Terraform handles all the supporting resources (Cognito, IAM, ECR). The AgentCore CLI reads from a `.bedrock_agentcore.yaml` config file that references the Terraform-managed role ARN and ECR repo.

2. **Cognito Domain** — If OAuth flows or hosted UI are needed, add an `aws_cognito_user_pool_domain` resource. For this project, direct `USER_PASSWORD_AUTH` via the SDK is sufficient.

3. **State management** — Use an S3 backend + DynamoDB lock table for remote Terraform state if collaborating:
   ```hcl
   backend "s3" {
     bucket         = "teilur-terraform-state"
     key            = "infrastructure/terraform.tfstate"
     region         = "us-east-1"
     dynamodb_table = "terraform-locks"
   }
   ```

4. **AgentCore CLI integration** — After `terraform apply`, feed outputs into the AgentCore CLI:
    ```bash
    agentcore configure \
      --entrypoint src/agent_handler.py \
      --execution-role $(terraform output -raw agentcore_execution_role_arn) \
      --ecr $(terraform output -raw ecr_repository_name) \
      --authorizer-config '{"type":"COGNITO","userPoolId":"'$(terraform output -raw cognito_user_pool_id)'","clientId":"'$(terraform output -raw cognito_user_pool_client_id)'"}' \
      --request-header-allowlist "Authorization" \
      --non-interactive
    ```
    > **Note:** The `--ecr` flag expects a **repository name** (e.g., `teilur-stock-agent-agent`), not a full URL. The `--authorizer-config` flag tells AgentCore to validate Cognito JWTs before requests reach the handler (see Phase 6 for details). The exact JSON schema for `--authorizer-config` should be verified against the AgentCore CLI at deploy time, as the official docs describe the flag as "OAuth authorizer configuration as JSON string" without specifying the schema.

---

## Verification Checklist

- [ ] `terraform init` succeeds
- [ ] `terraform plan` shows expected resources (Cognito pool, client, IAM role, ECR repo)
- [ ] `terraform apply` completes with no errors
- [ ] Cognito user pool is visible in AWS Console
- [ ] A test user can be created in the pool via AWS CLI:
  ```bash
  aws cognito-idp admin-create-user \
    --user-pool-id <POOL_ID> \
    --username testuser@example.com
  ```
- [ ] ECR repository is visible and accepts a `docker push`
- [ ] IAM role trust policy is correctly scoped to `bedrock-agentcore.amazonaws.com`
- [ ] Secrets Manager secret `teilur-stock-agent/langfuse` is visible in AWS Console with the correct key/value pairs
- [ ] `terraform.tfvars` is listed in `.gitignore` and never committed
