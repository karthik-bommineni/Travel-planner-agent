# AWS infra (Terraform)

This folder creates the AWS pieces the app needs. You do **not** click together an S3 bucket and random EC2 boxes in the console.

| Resource | What it is |
|---|---|
| S3 bucket | Source of truth for `catalog.sqlite` (not in the Docker image) |
| ECR | Holds the app image |
| VPC | Two public subnets (no NAT, cheaper for learning) |
| EKS | Managed Kubernetes control plane |
| Node group | **These are the EC2 instances.** EKS launches and replaces them. Pods run here. |
| IAM role (IRSA) | Lets a Kubernetes ServiceAccount `s3:GetObject` the catalog. No access keys in the pod. |

State is local (`terraform.tfstate` is gitignored). For a real team you would later move state to S3 + DynamoDB locking.

## Cost

EKS control plane is billed while the cluster exists, plus the worker EC2. Tear down when you are done:

```bash
terraform destroy
```

## Commands

Install Terraform and the AWS CLI. Then `aws configure` with a user/role that can create VPC, EKS, IAM, S3, and ECR.

```bash
cd infra
copy terraform.tfvars.example terraform.tfvars   # PowerShell: Copy-Item
# edit region if you want
terraform init
terraform plan
terraform apply
```

After apply:

```bash
# 1. Upload catalog (from repo root; ~4 GB)
aws s3 cp ../data/catalog.sqlite s3://$(terraform output -raw catalog_bucket)/catalog.sqlite

# 2. Log Docker into ECR, build, push (linux/amd64)
# 3. Point kubectl at the cluster
aws eks update-kubeconfig --region $(terraform output -raw region) --name $(terraform output -raw cluster_name)
```

Kubernetes manifests live in `../k8s/` (Deployment, S3 copy init container, Service). Apply those after this stack exists and the image is in ECR.
