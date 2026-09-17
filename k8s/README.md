# Kubernetes manifests

These files run the travel planner on the EKS cluster from `infra/`. Terraform builds AWS (S3, ECR, nodes). This folder tells Kubernetes how to run the container.

| File | What it is |
|---|---|
| `namespace.yaml` | A folder named `travel-planner` inside the cluster |
| `serviceaccount.yaml` | Identity `catalog-sync`. IRSA annotation must match Terraform’s role ARN |
| `configmap.yaml` | Non-secret settings: sqlite path, S3 URI, Gemini model |
| `secret.example.yaml` | Template for `GEMINI_API_KEY`. Do not commit a real key |
| `deployment.yaml` | One pod: init container copies sqlite from S3, then uvicorn serves the app |
| `service.yaml` | Stable in-cluster name `travel-planner` on port 80 → container 8000 |
| `ingress.yaml` | Optional public ALB. Apply only after AWS Load Balancer Controller is installed |
| `kustomization.yaml` | Lists the default files so you can `kubectl apply -k k8s` |

After apply, the UI streams tool calls (`POST /chat/stream`) and Prometheus scrapes `GET /metrics`.

`replicas: 1` on purpose. Each extra replica would copy another 4 GB.

## Fill in the placeholders

From `infra/` after `terraform apply`:

```bash
cd infra
terraform output -raw catalog_bucket
terraform output -raw catalog_sync_role_arn
terraform output -raw ecr_repository_url
```

1. In `serviceaccount.yaml`, set `eks.amazonaws.com/role-arn` to the role ARN.
2. In `configmap.yaml`, set `CATALOG_S3_URI` to `s3://<bucket>/catalog.sqlite`.
3. Upload the file if you have not: `aws s3 cp data/catalog.sqlite s3://<bucket>/catalog.sqlite`
4. Point the image at ECR, for example:

```bash
cd k8s
# replace the image name with terraform output ecr_repository_url
```

Edit `kustomization.yaml` `images.newName` to the ECR URL (no tag in `newName`; tag stays `0.1.0`), or change `image:` in `deployment.yaml`.

## Secret

```bash
kubectl create namespace travel-planner --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic travel-planner -n travel-planner --from-literal=GEMINI_API_KEY=your-key
```

## Apply

```bash
# kubeconfig from: terraform output -raw configure_kubectl
kubectl apply -k k8s
kubectl -n travel-planner rollout status deployment/travel-planner
kubectl -n travel-planner port-forward svc/travel-planner 8000:80
```

Open http://127.0.0.1:8000/

Optional internet URL (after ALB controller):

```bash
kubectl apply -f k8s/ingress.yaml
```

## ECR pull

Build and push `linux/amd64` to the ECR repo from Terraform. EKS nodes need permission to pull (the EKS module node role usually includes ECR read).
