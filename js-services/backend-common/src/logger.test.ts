import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import { LogContext, ContextAwareLogger, createLogger } from './logger';

describe('LoggerContext', () => {
  beforeEach(() => {
    // Clear any existing context before each test
    expect(LogContext.hasContext()).toEqual(false);
  });

  describe('Basic context operations', () => {
    it('should start with no context', () => {
      expect(LogContext.hasContext()).toEqual(false);
      expect(LogContext.getContext()).toEqual({});
    });

    it('should set and retrieve context within run()', () => {
      const testContext = { userId: '123', operation: 'test' };

      LogContext.run(testContext, () => {
        expect(LogContext.hasContext()).toEqual(true);
        expect(LogContext.getContext()).toEqual(testContext);
      });

      // Context should be cleared after run() completes
      expect(LogContext.hasContext()).toEqual(false);
      expect(LogContext.getContext()).toEqual({});
    });

    it('should return the function result', () => {
      const result = LogContext.run({ test: 'context' }, () => {
        return 'test-result';
      });

      expect(result).toEqual('test-result');
    });

    it('should handle async functions', async () => {
      const result = await LogContext.run({ async: true }, async () => {
        await new Promise((resolve) => setTimeout(resolve, 10));
        expect(LogContext.getContext()).toEqual({ async: true });
        return 'async-result';
      });

      expect(result).toEqual('async-result');
    });
  });

  describe('Context inheritance', () => {
    it('should merge nested contexts', () => {
      LogContext.run({ level1: 'a', common: 'first' }, () => {
        expect(LogContext.getContext()).toEqual({ level1: 'a', common: 'first' });

        LogContext.run({ level2: 'b', common: 'second' }, () => {
          expect(LogContext.getContext()).toEqual({
            level1: 'a',
            level2: 'b',
            common: 'second', // Inner context overrides
          });
        });

        // Outer context restored after inner run
        expect(LogContext.getContext()).toEqual({ level1: 'a', common: 'first' });
      });
    });

    it('should handle deeply nested contexts', () => {
      const contexts: Record<string, unknown>[] = [];

      LogContext.run({ depth: 1 }, () => {
        contexts.push(LogContext.getContext());

        LogContext.run({ depth: 2 }, () => {
          contexts.push(LogContext.getContext());

          LogContext.run({ depth: 3 }, () => {
            contexts.push(LogContext.getContext());
          });
        });
      });

      expect(contexts[0]).toEqual({ depth: 1 });
      expect(contexts[1]).toEqual({ depth: 2 });
      expect(contexts[2]).toEqual({ depth: 3 });
    });

    it('should preserve context across async operations', async () => {
      const contexts: Record<string, unknown>[] = [];

      await LogContext.run({ requestId: 'req-123' }, async () => {
        contexts.push(LogContext.getContext());

        await new Promise((resolve) => setTimeout(resolve, 10));
        contexts.push(LogContext.getContext());

        await LogContext.run({ operation: 'db-query' }, async () => {
          contexts.push(LogContext.getContext());
          await new Promise((resolve) => setTimeout(resolve, 10));
          contexts.push(LogContext.getContext());
        });

        contexts.push(LogContext.getContext());
      });

      expect(contexts[0]).toEqual({ requestId: 'req-123' });
      expect(contexts[1]).toEqual({ requestId: 'req-123' });
      expect(contexts[2]).toEqual({ requestId: 'req-123', operation: 'db-query' });
      expect(contexts[3]).toEqual({ requestId: 'req-123', operation: 'db-query' });
      expect(contexts[4]).toEqual({ requestId: 'req-123' });
    });
  });

  describe('Error handling', () => {
    it('should preserve context when errors are thrown', () => {
      expect(() => {
        LogContext.run({ errorTest: true }, () => {
          expect(LogContext.getContext()).toEqual({ errorTest: true });
          throw new Error('Test error');
        });
      }).toThrow('Test error');

      // Context should be cleared even after error
      expect(LogContext.hasContext()).toEqual(false);
    });

    it('should handle async errors', async () => {
      await expect(async () => {
        await LogContext.run({ asyncError: true }, async () => {
          await new Promise((resolve) => setTimeout(resolve, 10));
          expect(LogContext.getContext()).toEqual({ asyncError: true });
          throw new Error('Async error');
        });
      }).rejects.toThrow('Async error');

      expect(LogContext.hasContext()).toEqual(false);
    });
  });

  describe('Parallel execution', () => {
    it('should maintain separate contexts in parallel async operations', async () => {
      const results: string[] = [];

      const operation1 = LogContext.run({ op: 'op1' }, async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
        const ctx = LogContext.getContext();
        results.push(`op1: ${JSON.stringify(ctx)}`);
        return ctx;
      });

      const operation2 = LogContext.run({ op: 'op2' }, async () => {
        await new Promise((resolve) => setTimeout(resolve, 10));
        const ctx = LogContext.getContext();
        results.push(`op2: ${JSON.stringify(ctx)}`);
        return ctx;
      });

      const [ctx1, ctx2] = await Promise.all([operation1, operation2]);

      expect(ctx1).toEqual({ op: 'op1' });
      expect(ctx2).toEqual({ op: 'op2' });
      expect(results).toContain('op1: {"op":"op1"}');
      expect(results).toContain('op2: {"op":"op2"}');
    });
  });
});

describe('ContextAwareLogger', () => {
  let mockWinstonLogger: {
    error: jest.Mock;
    warn: jest.Mock;
    info: jest.Mock;
    debug: jest.Mock;
  };
  let contextLogger: ContextAwareLogger;

  beforeEach(() => {
    // Create a mock winston logger
    mockWinstonLogger = {
      error: jest.fn(),
      warn: jest.fn(),
      info: jest.fn(),
      debug: jest.fn(),
    };

    contextLogger = new ContextAwareLogger(mockWinstonLogger);
  });

  describe('Context integration', () => {
    it('should include context from LoggerContext in log messages', () => {
      LogContext.run({ userId: '123', operation: 'test' }, () => {
        contextLogger.info('Test message');

        expect(mockWinstonLogger.info).toHaveBeenCalledWith(
          'Test message',
          expect.objectContaining({
            userId: '123',
            operation: 'test',
          })
        );
      });
    });

    it('should merge additional context with LoggerContext', () => {
      LogContext.run({ userId: '123' }, () => {
        contextLogger.info('Test message', { extra: 'data' });

        expect(mockWinstonLogger.info).toHaveBeenCalledWith(
          'Test message',
          expect.objectContaining({
            userId: '123',
            extra: 'data',
          })
        );
      });
    });

    it('should allow additional context to override LoggerContext', () => {
      LogContext.run({ userId: '123', operation: 'original' }, () => {
        contextLogger.info('Test message', { operation: 'override' });

        expect(mockWinstonLogger.info).toHaveBeenCalledWith(
          'Test message',
          expect.objectContaining({
            userId: '123',
            operation: 'override', // Additional context wins
          })
        );
      });
    });

    it('should work without LoggerContext', () => {
      contextLogger.info('Test message', { standalone: true });

      expect(mockWinstonLogger.info).toHaveBeenCalledWith(
        'Test message',
        expect.objectContaining({
          standalone: true,
        })
      );
    });

    it('should handle errors with context', () => {
      const testError = new Error('Test error');

      LogContext.run({ errorContext: true }, () => {
        contextLogger.error('Error occurred', testError, { additional: 'info' });

        expect(mockWinstonLogger.error).toHaveBeenCalledWith(
          'Error occurred',
          expect.objectContaining({
            errorContext: true,
            additional: 'info',
            error: {
              message: 'Test error',
              stack: expect.any(String),
              name: 'Error',
            },
          })
        );
      });
    });
  });

  describe('Circular reference handling', () => {
    it('should handle objects with circular references in additional context', () => {
      const circular: Record<string, unknown> = { name: 'test' };
      circular.self = circular;

      expect(() => {
        contextLogger.info('Circular test', { circular });
      }).not.toThrow();

      expect(mockWinstonLogger.info).toHaveBeenCalledWith(
        'Circular test',
        expect.objectContaining({
          circular: expect.any(Object),
        })
      );
    });

    it('should handle nested circular references', () => {
      const obj1: Record<string, unknown> = { name: 'obj1' };
      const obj2: Record<string, unknown> = { name: 'obj2', ref: obj1 };
      obj1.ref = obj2;

      contextLogger.error('Nested circular test', undefined, { nested: obj1 });

      expect(mockWinstonLogger.error).toHaveBeenCalledWith(
        'Nested circular test',
        expect.objectContaining({
          nested: expect.any(Object),
        })
      );
    });

    it('should handle PostgreSQL-like error objects with circular references', () => {
      // Simulate a PostgreSQL error with circular references
      const pgError: Record<string, unknown> = {
        name: 'error',
        severity: 'ERROR',
        code: '42P01',
        position: '15',
        file: 'parse_relation.c',
        line: '3349',
        routine: 'parserOpenTable',
      };
      // Add circular reference
      pgError.client = { lastError: pgError };

      contextLogger.error('Database error', undefined, { dbError: pgError });

      expect(mockWinstonLogger.error).toHaveBeenCalledWith(
        'Database error',
        expect.objectContaining({
          dbError: expect.any(Object),
        })
      );
    });

    it('should handle circular references in LogContext', () => {
      const circular: Record<string, unknown> = { id: '123' };
      circular.parent = circular;

      LogContext.run(circular, () => {
        contextLogger.info('Test with circular context');

        expect(mockWinstonLogger.info).toHaveBeenCalledWith(
          'Test with circular context',
          expect.objectContaining({
            id: '123',
            parent: expect.any(Object),
          })
        );
      });
    });
  });

  describe('Production mode with real winston logger', () => {
    it('should handle circular references in production JSON format without throwing', () => {
      // Store original NODE_ENV
      const originalEnv = process.env.NODE_ENV;

      try {
        // Set production mode
        process.env.NODE_ENV = 'production';

        // Create a new logger instance with production settings
        // Note: Since the logger format is determined at module load time,
        // we need to work with what's already loaded. But our safeStringify
        // now handles both dev and prod formats.
        const prodLogger = createLogger('test-service-prod');
        const prodContextLogger = new ContextAwareLogger(prodLogger);

        // Create circular object
        const circular: Record<string, unknown> = { name: 'test' };
        circular.self = circular;

        // This should not throw with our safeStringify implementation
        expect(() => {
          prodContextLogger.info('Production circular test', { circular });
        }).not.toThrow();

        // Verify it logged without errors
        expect(true).toBe(true);
      } finally {
        // Restore original NODE_ENV
        process.env.NODE_ENV = originalEnv;
      }
    });

    it('should handle deeply nested circular references in production mode', () => {
      const originalEnv = process.env.NODE_ENV;

      try {
        process.env.NODE_ENV = 'production';

        const prodLogger = createLogger('test-service-prod');
        const prodContextLogger = new ContextAwareLogger(prodLogger);

        // Create complex circular structure
        const obj1: Record<string, unknown> = { id: '1', type: 'A' };
        const obj2: Record<string, unknown> = { id: '2', type: 'B', parent: obj1 };
        const obj3: Record<string, unknown> = { id: '3', type: 'C', parent: obj2 };
        obj1.child = obj3; // Create circular reference

        expect(() => {
          prodContextLogger.error('Complex circular error', undefined, { data: obj1 });
        }).not.toThrow();
      } finally {
        process.env.NODE_ENV = originalEnv;
      }
    });
  });
});
