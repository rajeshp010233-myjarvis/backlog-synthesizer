output "public_ip" {
  description = "Elastic IP — use this as your app URL"
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  description = "EC2 instance ID — set as GitHub Secret EC2_INSTANCE_ID"
  value       = aws_instance.app.id
}

output "aws_account_id" {
  description = "AWS account ID — set as GitHub Secret AWS_ACCOUNT_ID"
  value       = local.account_id
}

output "aws_region" {
  description = "Deployed region — set as GitHub Secret AWS_REGION"
  value       = var.aws_region
}

output "ecr_backend_url" {
  description = "ECR URL for the backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  description = "ECR URL for the frontend image"
  value       = aws_ecr_repository.frontend.repository_url
}

output "ecr_mcp_url" {
  description = "ECR URL for the mcp-server image"
  value       = aws_ecr_repository.mcp_server.repository_url
}

output "github_actions_access_key_id" {
  description = "AWS_ACCESS_KEY_ID — set as GitHub Secret"
  value       = aws_iam_access_key.github_actions.id
}

output "github_actions_secret_access_key" {
  description = "AWS_SECRET_ACCESS_KEY — set as GitHub Secret (sensitive)"
  value       = aws_iam_access_key.github_actions.secret
  sensitive   = true
}

output "github_secrets_summary" {
  description = "Copy these values into GitHub → Settings → Secrets → Actions"
  value = <<-EOT
    ┌─────────────────────────────────────────────────────────┐
    │         GitHub Actions Secrets to configure             │
    ├──────────────────────────┬──────────────────────────────┤
    │ Secret name              │ Value                        │
    ├──────────────────────────┼──────────────────────────────┤
    │ AWS_REGION               │ ${var.aws_region}
    │ AWS_ACCOUNT_ID           │ ${local.account_id}
    │ EC2_INSTANCE_ID          │ ${aws_instance.app.id}
    │ AWS_ACCESS_KEY_ID        │ ${aws_iam_access_key.github_actions.id}
    │ AWS_SECRET_ACCESS_KEY    │ (run: terraform output -raw github_actions_secret_access_key)
    └──────────────────────────┴──────────────────────────────┘

    App URL: http://${aws_eip.app.public_ip}
  EOT
}
