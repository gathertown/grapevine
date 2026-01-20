/**
 * Snowflake SQL API Client
 * Low-level HTTP client for executing SQL queries against Snowflake's REST API
 */

export interface SnowflakeSqlApiResponse {
  statementHandle: string;
  statementStatusUrl: string;
  sqlText: string;
  resultSetMetaData?: {
    numRows: number;
    format: string;
    rowType: Array<{ name: string; type: string }>;
  };
  data?: Array<Array<string | number | boolean | null>>;
  code?: string;
  message?: string;
}

export interface SnowflakeQueryOptions {
  /** The SQL statement to execute */
  statement: string;
  /** Query timeout in seconds (default: 60) */
  timeout?: number;
  /** Database to use for the query */
  database?: string;
  /** Schema to use for the query */
  schema?: string;
  /** Warehouse to use for the query */
  warehouse?: string;
  /** Role to use for the query */
  role?: string;
}

/**
 * Executes a SQL statement using the Snowflake SQL API
 *
 * @param accountIdentifier - Snowflake account identifier (e.g., "myorg-account123")
 * @param accessToken - OAuth access token
 * @param options - Query options including the SQL statement
 * @returns The API response with query results
 * @throws Error if the API request fails
 *
 * @see https://docs.snowflake.com/en/developer-guide/sql-api/reference
 */
export async function executeSnowflakeQuery(
  accountIdentifier: string,
  accessToken: string,
  options: SnowflakeQueryOptions
): Promise<SnowflakeSqlApiResponse> {
  const apiUrl = `https://${accountIdentifier}.snowflakecomputing.com/api/v2/statements`;

  const requestBody: Record<string, unknown> = {
    statement: options.statement,
    timeout: options.timeout ?? 60,
  };

  // Add optional context parameters if provided
  if (options.database) {
    requestBody.database = options.database;
  }
  if (options.schema) {
    requestBody.schema = options.schema;
  }
  if (options.warehouse) {
    requestBody.warehouse = options.warehouse;
  }
  if (options.role) {
    requestBody.role = options.role;
  }

  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'User-Agent': 'Grapevine/1.0',
      'X-Snowflake-Authorization-Token-Type': 'OAUTH',
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Snowflake SQL API error: ${response.status} ${text}`);
  }

  return response.json();
}
