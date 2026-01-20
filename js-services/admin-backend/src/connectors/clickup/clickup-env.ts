function getClickupClientId(): string {
  const value = process.env.CLICKUP_CLIENT_ID;
  if (!value) {
    throw new Error('CLICKUP_CLIENT_ID environment variable is required for Clickup OAuth');
  }
  return value;
}

function getClickupClientSecret(): string {
  const value = process.env.CLICKUP_CLIENT_SECRET;
  if (!value) {
    throw new Error('CLICKUP_CLIENT_SECRET environment variable is required for Clickup OAuth');
  }
  return value;
}

export { getClickupClientId, getClickupClientSecret };
