/**
 * API Client for authenticated requests
 * Automatically handles auth tokens and common error scenarios
 */

// In development, Vite proxy handles /api routes. In production, same-origin.
const API_BASE_URL = '';

type TokenProvider = () => Promise<string | null>;

interface RequestOptions extends Omit<RequestInit, 'body'> {
  headers?: Record<string, string>;
  body?: unknown;
}

class ApiClient {
  private authToken: string | null = null;
  private tokenProvider: TokenProvider | null = null;

  /**
   * Set the token provider function that returns a fresh access token
   */
  setTokenProvider(provider: TokenProvider): void {
    this.tokenProvider = provider;
  }

  /**
   * Get the current auth token, refreshing if necessary
   */
  async getAuthToken(): Promise<string | null> {
    if (this.tokenProvider) {
      try {
        this.authToken = await this.tokenProvider();
        return this.authToken;
      } catch (error) {
        console.error('Failed to get auth token:', error);
        return null;
      }
    }
    return this.authToken;
  }

  /**
   * Prepare headers for a request, optionally including authentication
   */
  private async prepareHeaders(
    baseHeaders: Record<string, string> = {},
    includeAuth: boolean = true
  ): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...baseHeaders,
    };

    if (includeAuth) {
      const token = await this.getAuthToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
    }

    return headers;
  }

  /**
   * Core HTTP request method - handles the actual fetch call and error processing
   */
  private async httpRequest(
    endpoint: string,
    options: RequestOptions = {},
    includeAuth: boolean = true
  ): Promise<Response> {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers = await this.prepareHeaders(options.headers, includeAuth);

    const response = await fetch(url, {
      ...options,
      headers,
      body: options.body ? JSON.stringify(options.body) : null,
    });

    // Handle common error scenarios for authenticated requests
    if (includeAuth) {
      if (response.status === 401) {
        console.warn('Unauthorized request - token may be expired');
        throw new ApiError('Authentication required', 401);
      }

      if (response.status === 403) {
        console.warn('Forbidden request - insufficient permissions');
        throw new ApiError('Insufficient permissions', 403);
      }
    }

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.error || errorData.message || errorMessage;
      } catch {
        // If response body is not JSON, use status text
      }
      throw new ApiError(errorMessage, response.status);
    }

    return response;
  }

  /**
   * Make an authenticated API request (includes Authorization header)
   */
  async authenticatedRequest(endpoint: string, options: RequestOptions = {}): Promise<Response> {
    return this.httpRequest(endpoint, options, true);
  }

  /**
   * Make an unauthenticated API request (no Authorization header)
   */
  async unauthenticatedRequest(endpoint: string, options: RequestOptions = {}): Promise<Response> {
    return this.httpRequest(endpoint, options, false);
  }

  /**
   * Make an authenticated GET request
   */
  async get<T = unknown>(endpoint: string, options: Omit<RequestOptions, 'body'> = {}): Promise<T> {
    const response = await this.authenticatedRequest(endpoint, {
      method: 'GET',
      ...options,
    });
    return response.json();
  }

  /**
   * Make an authenticated POST request
   */
  async post<T = unknown>(
    endpoint: string,
    data: unknown = null,
    options: Omit<RequestOptions, 'body'> = {}
  ): Promise<T> {
    const response = await this.authenticatedRequest(endpoint, {
      method: 'POST',
      body: data,
      ...options,
    });
    return response.json();
  }

  /**
   * Make an authenticated PUT request
   */
  async put<T = unknown>(
    endpoint: string,
    data: unknown = null,
    options: Omit<RequestOptions, 'body'> = {}
  ): Promise<T> {
    const response = await this.authenticatedRequest(endpoint, {
      method: 'PUT',
      body: data,
      ...options,
    });
    return response.json();
  }

  /**
   * Make an authenticated PATCH request
   */
  async patch<T = unknown>(
    endpoint: string,
    data: unknown = null,
    options: Omit<RequestOptions, 'body'> = {}
  ): Promise<T> {
    const response = await this.authenticatedRequest(endpoint, {
      method: 'PATCH',
      body: data,
      ...options,
    });
    return response.json();
  }

  /**
   * Make an authenticated DELETE request
   */
  async delete<T = unknown>(
    endpoint: string,
    options: Omit<RequestOptions, 'body'> = {}
  ): Promise<T> {
    const response = await this.authenticatedRequest(endpoint, {
      method: 'DELETE',
      ...options,
    });
    return response.json();
  }
}

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// Create and export a singleton instance
export const apiClient = new ApiClient();
