# EKS control plane is AWS-managed. The node group is the EC2 fleet Kubernetes schedules pods on.

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.public_subnets

  cluster_endpoint_public_access = true

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    default = {
      name           = "${var.cluster_name}-nodes"
      instance_types = [var.node_instance_type]
      min_size       = 1
      max_size       = 2
      desired_size   = var.node_desired_size
      disk_size      = 40
      subnet_ids     = module.vpc.public_subnets
    }
  }
}
