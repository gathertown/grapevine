import { TenantSlackApp } from './TenantSlackApp';
import { SSMClient } from '@corporate-context/backend-common';
import { logger, LogContext } from './utils/logger';

/**
 * Manages Slack App instances for multiple tenants with caching and lifecycle management.
 *
 * Each tenant gets their own Slack App instance with credentials fetched from SSM.
 * Implements LRU caching with automatic expiry and cleanup to manage memory usage.
 */
export class TenantSlackAppManager {
  private tenantApps = new Map<string, TenantSlackApp>();
  private ssmClient = new SSMClient();
  private readonly maxCacheSize: number = 100;

  async getTenantSlackApp(tenantId: string): Promise<TenantSlackApp> {
    // Check if we have a cached app for this tenant
    const cached = this.tenantApps.get(tenantId);
    if (cached) {
      return cached;
    }

    // Create new app for this tenant
    const tenantApp = await TenantSlackApp.create(tenantId, this.ssmClient);

    // Cache management - remove oldest if we're at capacity
    if (this.tenantApps.size >= this.maxCacheSize) {
      const oldestTenant = this.findOldestTenant();
      if (oldestTenant) {
        const oldApp = this.tenantApps.get(oldestTenant);
        if (oldApp) {
          await oldApp.stop();
        }
        this.tenantApps.delete(oldestTenant);
      }
    }

    this.tenantApps.set(tenantId, tenantApp);
    return tenantApp;
  }

  private findOldestTenant(): string | undefined {
    // Just return the first entry (oldest by insertion)
    const firstEntry = this.tenantApps.entries().next();
    return firstEntry.done ? undefined : firstEntry.value[0];
  }

  /**
   * Restart a specific tenant's Slack app with fresh credentials.
   * This gracefully stops the existing app and creates a new one with updated tokens.
   */
  async restartTenantSlackApp(tenantId: string): Promise<TenantSlackApp> {
    return LogContext.run({ tenant_id: tenantId }, async () => {
      logger.info('Restarting Slack app for tenant', { operation: 'tenant-app-restart' });

      // Stop and remove existing app if it exists
      const existingApp = this.tenantApps.get(tenantId);
      if (existingApp) {
        logger.info('Stopping existing Slack app for tenant', { operation: 'tenant-app-stop' });
        await existingApp.stop();
        this.tenantApps.delete(tenantId);
      }

      // Create new app with fresh credentials
      logger.info('Creating new Slack app for tenant', { operation: 'tenant-app-create' });
      const newTenantApp = await TenantSlackApp.create(tenantId, this.ssmClient);

      // Cache the new app
      this.tenantApps.set(tenantId, newTenantApp);

      logger.info('Successfully restarted Slack app for tenant', {
        operation: 'tenant-app-restart-complete',
      });
      return newTenantApp;
    });
  }

  async shutdown(): Promise<void> {
    logger.info('Shutting down all tenant Slack apps...', { operation: 'tenant-apps-shutdown' });
    const shutdownPromises: (void | Promise<void>)[] = [];

    for (const [tenantId, tenantApp] of this.tenantApps.entries()) {
      shutdownPromises.push(
        LogContext.run({ tenant_id: tenantId }, async () => {
          logger.info('Stopping Slack app for tenant', { operation: 'tenant-app-shutdown' });
          return tenantApp.stop();
        })
      );
    }

    await Promise.all(shutdownPromises);
    this.tenantApps.clear();
    logger.info('All tenant Slack apps shut down', { operation: 'tenant-apps-shutdown-complete' });
  }

  getCacheSize(): number {
    return this.tenantApps.size;
  }

  getCachedTenants(): string[] {
    return Array.from(this.tenantApps.keys());
  }
}

// Singleton instance
let appManager: TenantSlackAppManager | null = null;

export function getTenantSlackAppManager(): TenantSlackAppManager {
  if (!appManager) {
    appManager = new TenantSlackAppManager();
  }
  return appManager;
}
