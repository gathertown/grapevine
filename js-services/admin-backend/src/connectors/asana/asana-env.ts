function getAsanaClientId(): string {
  const value = process.env.ASANA_CLIENT_ID;
  if (!value) {
    throw new Error('ASANA_CLIENT_ID environment variable is required for Asana OAuth');
  }
  return value;
}

function getAsanaClientSecret(): string {
  const value = process.env.ASANA_CLIENT_SECRET;
  if (!value) {
    throw new Error('ASANA_CLIENT_SECRET environment variable is required for Asana OAuth');
  }
  return value;
}

export { getAsanaClientId, getAsanaClientSecret };
