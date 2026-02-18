output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "cognito_user_pool_client_id" {
  value = aws_cognito_user_pool_client.app_client.id
}

output "cognito_user_pool_endpoint" {
  description = "Issuer URL for JWT validation (format: cognito-idp.REGION.amazonaws.com/POOL_ID)"
  value       = aws_cognito_user_pool.main.endpoint
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
