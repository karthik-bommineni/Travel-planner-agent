# IRSA: the catalog-sync ServiceAccount can read the bucket. No long-lived AWS keys in the pod.

data "aws_iam_policy_document" "catalog_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:${local.catalog_sa_namespace}:${local.catalog_sa_name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "catalog_read" {
  statement {
    sid     = "ReadCatalogObject"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.catalog.arn}/catalog.sqlite",
    ]
  }

  statement {
    sid     = "ListBucket"
    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.catalog.arn,
    ]
  }
}

resource "aws_iam_role" "catalog_sync" {
  name               = "${var.cluster_name}-catalog-sync"
  assume_role_policy = data.aws_iam_policy_document.catalog_assume.json
}

resource "aws_iam_role_policy" "catalog_sync" {
  name   = "s3-catalog-read"
  role   = aws_iam_role.catalog_sync.id
  policy = data.aws_iam_policy_document.catalog_read.json
}
