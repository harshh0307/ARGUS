param(
    [string]$Region = "us-east-1",
    [string]$Environment = "dev",
    [string]$BucketPrefix = "argus-tfstate",
    [string]$GitHubRepo = "harshh0307/ARGUS",
    [string]$PolicyName = "ArgusDeployPolicy"
)

$ErrorActionPreference = "Stop"

Write-Host "== Argus AWS bootstrap ==" -ForegroundColor Cyan
Write-Host "Region: $Region | Env: $Environment | Repo: $GitHubRepo"

# ---------- 1. Terraform state bucket ----------
$bucket = "$BucketPrefix-$Environment"
try {
    aws s3api head-bucket --region $Region --bucket $bucket 2>$null | Out-Null
    Write-Host "OK   state bucket exists: $bucket" -ForegroundColor Green
} catch {
    Write-Host "CREATE state bucket: $bucket"
    aws s3api create-bucket --region $Region --bucket $bucket --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
    aws s3api put-bucket-versioning --region $Region --bucket $bucket --versioning-configuration Status=Enabled | Out-Null
    aws s3api put-public-access-block --region $Region --bucket $bucket --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true | Out-Null
    Write-Host "OK   bucket created (versioned, public access blocked)" -ForegroundColor Green
}

# ---------- 2. DynamoDB lock table ----------
$lockTable = "terraform-lock-$Environment"
try {
    aws dynamodb describe-table --region $Region --table-name $lockTable 2>$null | Out-Null
    Write-Host "OK   lock table exists: $lockTable" -ForegroundColor Green
} catch {
    Write-Host "CREATE lock table: $lockTable"
    aws dynamodb create-table --region $Region --table-name $lockTable `
        --attribute-definitions AttributeName=LockID,AttributeType=S `
        --key-schema AttributeName=LockID,KeyType=HASH `
        --billing-mode PAY_PER_REQUEST | Out-Null
    aws dynamodb wait table-exists --region $Region --table-name $lockTable
    Write-Host "OK   lock table created (on-demand billing)" -ForegroundColor Green
}

# ---------- 3. GitHub OIDC provider ----------
$oidcUrl = "https://token.actions.githubusercontent.com"
$thumbprint = "6938fd4d98bab03faadb97b34396831e3780aea1"
$thumbprint2 = "dfe7234a1e16b2f7eaa2c9e5cd8c5c2f2d5a6b7c"
$providerArn = $null
try {
    $providerArn = (aws iam get-open-id-connect-provider --open-id-connect-provider-arn "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):oidc-provider/token.actions.githubusercontent.com" --query Arn --output text 2>$null)
    if ($providerArn) {
        Write-Host "OK   OIDC provider exists" -ForegroundColor Green
    }
} catch {
    Write-Host "CREATE OIDC provider"
    aws iam create-open-id-connect-provider `
        --url $oidcUrl `
        --client-id-list "sts.amazonaws.com" `
        --thumbprint-list $thumbprint $thumbprint2 | Out-Null
    $providerArn = "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):oidc-provider/token.actions.githubusercontent.com"
    Write-Host "OK   OIDC provider created" -ForegroundColor Green
}

$account = aws sts get-caller-identity --query Account --output text

# ---------- 4. Deploy role (assumed by GitHub Actions) ----------
$roleName = "github-actions-$Environment"
$assumePolicy = @{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect    = "Allow"
            Principal = @{ Federated = $providerArn }
            Action    = "sts:AssumeRoleWithWebIdentity"
            Condition = @{
                StringEquals = @{
                    "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
                }
                StringLike = @{
                    "token.actions.githubusercontent.com:sub" = "repo:$GitHubRepo:*"
                }
            }
        }
    )
} | ConvertTo-Json -Depth 6

$roleArn = $null
try {
    $roleArn = (aws iam get-role --role-name $roleName --query Role.Arn --output text 2>$null)
    if ($roleArn) {
        Write-Host "OK   role exists: $roleName" -ForegroundColor Green
    }
} catch {
    Write-Host "CREATE role: $roleName"
    aws iam create-role --role-name $roleName --assume-role-policy-document $assumePolicy | Out-Null
    $roleArn = "arn:aws:iam::$account`:$roleName"
    Write-Host "OK   role created" -ForegroundColor Green
}

# ---------- 5. Attach permissions (recreate policy to keep in sync) ----------
$policyArn = "arn:aws:iam::$account`:policy/$PolicyName"

$policyDocument = @{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect   = "Allow"
            Action   = @("s3:GetObject", "s3:PutObject", "s3:ListBucket")
            Resource = @("arn:aws:s3:::$bucket", "arn:aws:s3:::$bucket/*")
        },
        @{
            Effect   = "Allow"
            Action   = @("dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem")
            Resource = "arn:aws:dynamodb:$Region`:$account`:table/$lockTable"
        },
        @{
            Effect   = "Allow"
            Action   = @("ecr:*", "ecs:*", "iam:PassRole", "logs:*", "elasticache:*", "rds:*", "s3:*", "ssm:*", "ec2:*", "elasticloadbalancing:*", "cloudwatch:*")
            Resource = "*"
        }
    )
} | ConvertTo-Json -Depth 6

$policyExists = $true
try {
    aws iam get-policy --policy-arn $policyArn 2>$null | Out-Null
} catch {
    $policyExists = $false
}

if (-not $policyExists) {
    Write-Host "CREATE policy: $PolicyName"
    aws iam create-policy --policy-name $PolicyName --policy-document $policyDocument | Out-Null
} else {
    $ver = aws iam list-policy-versions --policy-arn $policyArn --query "Versions[?IsDefaultVersion==\`"true\`"].VersionId" --output text
    if ($ver -eq "v1") {
        aws iam create-policy-version --policy-arn $policyArn --policy-document $policyDocument --set-as-default | Out-Null
        aws iam delete-policy-version --policy-arn $policyArn --version-id v1 | Out-Null
    } else {
        Write-Host "WARN policy has >1 version; leaving as-is" -ForegroundColor Yellow
    }
}

Write-Host "ATTACH policy to role"
aws iam attach-role-policy --role-name $roleName --policy-arn $policyArn 2>$null
aws iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser" 2>$null
aws iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/AmazonECS_FullAccess" 2>$null

# ---------- 6b. Create GitHub Actions variables ----------
Write-Host ""
Write-Host "== GitHub secrets ==" -ForegroundColor Cyan
Write-Host "Add these two secrets to https://github.com/$GitHubRepo/settings/secrets/actions :"
Write-Host "  AWS_DEPLOY_ROLE_ARN = $roleArn"
Write-Host "  TF_STATE_BUCKET     = $bucket"

# ---------- 6. Upload secrets ----------
Write-Host ""
Write-Host "== Uploading .env secrets to SSM Parameter Store ==" -ForegroundColor Cyan
& "$PSScriptRoot\upload-secrets.ps1" -Region $Region -Prefix "/argus"

# ---------- 7. Summary ----------
Write-Host ""
Write-Host "== Bootstrap complete ==" -ForegroundColor Green
Write-Host "Add these to your GitHub repo secrets:"
Write-Host "  AWS_DEPLOY_ROLE_ARN = $roleArn"
Write-Host "  TF_STATE_BUCKET     = $bucket"
Write-Host ""
Write-Host "Then deploy with:"
Write-Host "  terraform -chdir=infra/terraform init -backend-config=`"bucket=$bucket`" -backend-config=`"key=argus/terraform.tfstate`" -backend-config=`"region=$Region`""
Write-Host "  terraform -chdir=infra/terraform apply"