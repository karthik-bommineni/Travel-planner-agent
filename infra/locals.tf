data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  catalog_sa_namespace = "travel-planner"
  catalog_sa_name      = "catalog-sync"
}
