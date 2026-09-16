output "region" {
  value = var.region
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "catalog_bucket" {
  description = "Upload the sqlite file here: aws s3 cp data/catalog.sqlite s3://<this>/catalog.sqlite"
  value       = aws_s3_bucket.catalog.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "catalog_sync_role_arn" {
  description = "Annotate ServiceAccount catalog-sync with this role ARN."
  value       = aws_iam_role.catalog_sync.arn
}

output "configure_kubectl" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}
