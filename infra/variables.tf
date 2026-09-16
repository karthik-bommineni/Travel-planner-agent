variable "region" {
  description = "AWS region for the cluster, ECR, and catalog bucket."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name. Also prefixes VPC, ECR, and IAM names."
  type        = string
  default     = "travel-planner"
}

variable "cluster_version" {
  description = "Kubernetes version for EKS."
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "EC2 type for the managed node group. t3.large leaves room for the 4 GB catalog copy."
  type        = string
  default     = "t3.large"
}

variable "node_desired_size" {
  description = "How many worker EC2 instances to run. Start at 1."
  type        = number
  default     = 1
}
