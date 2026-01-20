#!/usr/bin/env bash

# Calculate expected application name based on PR number
APP_NAME="cc-devenv-$GITHUB_PR_NUMBER"

echo "Waiting for ArgoCD application '$APP_NAME' to be synced..."

# Wait up to 10 minutes for the application to be synced and healthy
TIMEOUT=600
INTERVAL=10
DESIRED_READY_TIMES=3

TIMES=0
ELAPSED=0

while [[ $ELAPSED -lt $TIMEOUT ]]; do
  # Get application status
  STATUS=$(kubectl get application "$APP_NAME" -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "NotFound")
  HEALTH=$(kubectl get application "$APP_NAME" -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")

  if [[ "$STATUS" == "Synced" && "$HEALTH" == "Healthy" ]]; then
    if [[ $TIMES -lt $DESIRED_READY_TIMES ]]; then
      echo "ℹ️ Application is synced and healthy" \
        "waiting to be observed for $DESIRED_READY_TIMES times" \
        "($TIMES/$DESIRED_READY_TIMES)..."

      TIMES=$((++TIMES))

      sleep $INTERVAL
      ELAPSED=$((ELAPSED + INTERVAL))
      continue
    fi

    echo "✅ Application is synced and healthy!"
    exit
  fi

  TIMES=0

  # Calculate remaining time in human-friendly format
  REMAINING=$((TIMEOUT - ELAPSED))
  REMAINING_MINUTES=$((REMAINING / 60))
  REMAINING_SECONDS=$((REMAINING % 60))

  if [[ $REMAINING_MINUTES -gt 0 ]]; then
    MAX_TIME="${REMAINING_MINUTES}m${REMAINING_SECONDS}s"
  else
    MAX_TIME="${REMAINING_SECONDS}s"
  fi

  echo "Application status: Sync=$STATUS, Health=$HEALTH - continuing to wait... (max: $MAX_TIME)"

  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo "❌ Timeout waiting for application to be synced and healthy"
kubectl get application "$APP_NAME" -n argocd -o yaml || true
exit 1
