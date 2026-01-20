#! /bin/bash

# util to login to AWS
aws-login () {
  AWS_PROFILE=${1:-$AWS_PROFILE} \
  && echo "AWS_PROFILE=${AWS_PROFILE}" \
  && aws sso login --profile "${AWS_PROFILE}" \
  && eval $(aws configure export-credentials --format env --profile "${AWS_PROFILE}") \
  && (aws sts get-caller-identity --output json --profile "${AWS_PROFILE}" | cat)
}

# Get AWS profile from first argument or default to platform-team
AWS_PROFILE=${1:-"platform-team"}

# start docker if it's not running
if ! docker info > /dev/null 2>&1; then
  echo "🐳 Docker is not running, starting it..."
  open -a Docker

  echo "⏳ Waiting for Docker to start..."
  until docker info > /dev/null 2>&1; do
    sleep 2
  done
  echo "✅ Docker is now running"
fi

echo "🔨 Building Docker image for gather-coworker-bot..."
docker build --platform linux/amd64 -t gathertown/gather-coworker-bot .

# Check if the build failed
if [ $? -ne 0 ]; then
  echo "❌ Docker build failed! Aborting deployment."
  exit 1
fi

echo "🚀 Pushing Docker image to registry..."
docker push gathertown/gather-coworker-bot

# Check if the push failed
if [ $? -ne 0 ]; then
  echo "❌ Docker push failed! Aborting deployment."
  exit 1
fi

echo "🔑 Authenticating with AWS..."
aws-login "$AWS_PROFILE"

echo "📦 Applying deployment configuration..."
kubectl apply -f deployment.yaml

echo "♻️ Restarting Kubernetes deployment..."
kubectl rollout restart -n gather-gpt deployment/coworker

echo "✅ Deployment completed successfully!"
