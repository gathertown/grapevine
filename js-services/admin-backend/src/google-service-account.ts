import { google, iam_v1, pubsub_v1, cloudresourcemanager_v1 } from 'googleapis';
import { logger, LogContext } from './utils/logger.js';

interface ServiceAccountDetails {
  tenantId: string;
  serviceAccountEmail: string;
  uniqueId: string;
  projectId: string;
  name: string;
  privateKeyData?: string;
  existed?: boolean;
}

export class GoogleServiceAccountManager {
  private projectId: string;
  private projectNumber: string | null = null;
  private iam: iam_v1.Iam;
  private pubsub: pubsub_v1.Pubsub;
  private cloudResourceManager: cloudresourcemanager_v1.Cloudresourcemanager;

  constructor() {
    const controlServiceAccountJson = process.env.GOOGLE_DRIVE_CONTROL_SERVICE_ACCOUNT;
    if (!controlServiceAccountJson) {
      throw new Error('GOOGLE_DRIVE_CONTROL_SERVICE_ACCOUNT environment variable not set');
    }

    let serviceAccountInfo: Record<string, unknown>;
    try {
      serviceAccountInfo = JSON.parse(controlServiceAccountJson);
    } catch {
      throw new Error('Invalid GOOGLE_DRIVE_CONTROL_SERVICE_ACCOUNT JSON');
    }

    this.projectId = serviceAccountInfo.project_id as string;

    const auth = new google.auth.GoogleAuth({
      credentials: serviceAccountInfo,
      scopes: ['https://www.googleapis.com/auth/cloud-platform'],
    });

    this.iam = google.iam({ version: 'v1', auth });
    this.pubsub = google.pubsub({ version: 'v1', auth });
    this.cloudResourceManager = google.cloudresourcemanager({ version: 'v1', auth });
  }

  /**
   * Get the project number for the current project.
   * The project number is needed to construct the Pub/Sub service agent email.
   */
  private async getProjectNumber(): Promise<string> {
    if (this.projectNumber) {
      return this.projectNumber;
    }

    try {
      const response = await this.cloudResourceManager.projects.get({
        projectId: this.projectId,
      });

      const projectNumber = response.data.projectNumber;
      if (!projectNumber) {
        throw new Error('Project number not found in response');
      }

      this.projectNumber = projectNumber;
      logger.info(`Retrieved project number: ${projectNumber}`);
      return projectNumber;
    } catch (error) {
      logger.error('Failed to get project number', { error: String(error) });
      throw error;
    }
  }

  /**
   * Get the Pub/Sub service agent email for the current project.
   * Format: service-{PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com
   */
  private async getPubSubServiceAgentEmail(): Promise<string> {
    const projectNumber = await this.getProjectNumber();
    return `service-${projectNumber}@gcp-sa-pubsub.iam.gserviceaccount.com`;
  }

  /**
   * Create a service account for a tenant.
   * @param tenantId - The tenant identifier
   * @param createKey - Whether to create and return a key for the service account
   */
  async createTenantServiceAccount(
    tenantId: string,
    createKey: boolean = true
  ): Promise<ServiceAccountDetails> {
    return LogContext.run(
      { tenant_id: tenantId, operation: 'create-service-account', createKey },
      async () => {
        if (!tenantId) {
          throw new Error('Tenant ID is required');
        }

        const accountId = `tenant-${tenantId}`;

        const accountDetails: ServiceAccountDetails = {
          tenantId,
          serviceAccountEmail: '',
          uniqueId: '',
          projectId: this.projectId,
          name: '',
        };

        try {
          const createResponse = await this.iam.projects.serviceAccounts.create({
            name: `projects/${this.projectId}`,
            requestBody: {
              accountId,
              serviceAccount: {
                displayName: tenantId,
                description: `Service account for tenant ${tenantId}`,
              },
            },
          });

          const createdAccount = createResponse.data;

          logger.info(`Successfully created service account for tenant ${tenantId}`, {
            accountEmail: createdAccount.email,
            uniqueId: createdAccount.uniqueId,
          });

          accountDetails.serviceAccountEmail = createdAccount.email || '';
          accountDetails.uniqueId = createdAccount.uniqueId || '';
          accountDetails.name = createdAccount.name || '';
        } catch (error) {
          const errorCode = (error as { code?: number })?.code;
          if (errorCode === 409) {
            logger.info(
              `Service account for tenant ${tenantId} already exists. Fetching details...`
            );

            try {
              const getResponse = await this.iam.projects.serviceAccounts.get({
                name: `projects/${this.projectId}/serviceAccounts/${accountId}@${this.projectId}.iam.gserviceaccount.com`,
              });

              const existingAccount = getResponse.data;
              logger.info('Found existing account', {
                accountEmail: existingAccount.email,
                uniqueId: existingAccount.uniqueId,
              });

              accountDetails.serviceAccountEmail = existingAccount.email || '';
              accountDetails.uniqueId = existingAccount.uniqueId || '';
              accountDetails.name = existingAccount.name || '';
              accountDetails.existed = true;
            } catch (getError) {
              throw new Error(`Service account exists but could not fetch details: ${getError}`);
            }
          } else {
            throw error;
          }
        }

        if (createKey && accountDetails.name) {
          try {
            logger.info('Creating service account key...');

            if (!accountDetails.existed) {
              await new Promise((resolve) => setTimeout(resolve, 2000));
            }

            const keyResponse = await this.iam.projects.serviceAccounts.keys.create({
              name: accountDetails.name,
              requestBody: {
                privateKeyType: 'TYPE_GOOGLE_CREDENTIALS_FILE',
                keyAlgorithm: 'KEY_ALG_RSA_2048',
              },
            });

            if (keyResponse.data.privateKeyData) {
              const privateKeyJson = Buffer.from(
                keyResponse.data.privateKeyData,
                'base64'
              ).toString('utf-8');
              accountDetails.privateKeyData = privateKeyJson;
              logger.info(`Service account key created successfully for tenant ${tenantId}`);
            }
          } catch (keyError) {
            logger.error(`Warning: Could not create service account key`, {
              error: String(keyError),
            });
          }
        }

        return accountDetails;
      }
    );
  }

  /**
   * Grant the control service account and Pub/Sub service agent permission to act as the tenant service account.
   * The Pub/Sub service agent needs Token Creator role to mint OIDC tokens for push authentication.
   * @param tenantServiceAccountEmail - The email of the tenant's service account
   */
  async grantActAsPermission(tenantServiceAccountEmail: string): Promise<void> {
    return LogContext.run(
      { operation: 'grant-actAs-permission', tenantServiceAccountEmail },
      async () => {
        const controlServiceAccountJson = process.env.GOOGLE_DRIVE_CONTROL_SERVICE_ACCOUNT;
        if (!controlServiceAccountJson) {
          throw new Error('GOOGLE_DRIVE_CONTROL_SERVICE_ACCOUNT environment variable not set');
        }
        const controlServiceAccountInfo = JSON.parse(controlServiceAccountJson);
        const controlServiceAccountEmail = controlServiceAccountInfo.client_email;

        // Get the Pub/Sub service agent email (needs Token Creator to mint OIDC tokens)
        const pubSubServiceAgentEmail = await this.getPubSubServiceAgentEmail();

        // Define which members need which roles on the tenant service account
        // - Control SA needs both roles for general service account operations
        // - Pub/Sub service agent needs Token Creator to mint OIDC tokens for push subscriptions
        const roleBindings: { role: string; members: string[] }[] = [
          {
            role: 'roles/iam.serviceAccountUser',
            members: [`serviceAccount:${controlServiceAccountEmail}`],
          },
          {
            role: 'roles/iam.serviceAccountTokenCreator',
            members: [
              `serviceAccount:${controlServiceAccountEmail}`,
              `serviceAccount:${pubSubServiceAgentEmail}`,
            ],
          },
        ];

        try {
          // Get current IAM policy for the tenant service account
          const getIamPolicyResponse = await this.iam.projects.serviceAccounts.getIamPolicy({
            resource: `projects/${this.projectId}/serviceAccounts/${tenantServiceAccountEmail}`,
          });

          const policy = getIamPolicyResponse.data;

          if (!policy.bindings) {
            policy.bindings = [];
          }

          let policyUpdated = false;

          for (const { role, members } of roleBindings) {
            for (const memberToAdd of members) {
              const existingBinding = policy.bindings.find((b) => b.role === role);

              if (existingBinding) {
                // Binding for this role exists - add member if not already present
                if (!existingBinding.members?.includes(memberToAdd)) {
                  existingBinding.members = existingBinding.members || [];
                  existingBinding.members.push(memberToAdd);
                  logger.info(`Adding ${memberToAdd} to existing ${role} binding...`);
                  policyUpdated = true;
                } else {
                  logger.info(`${role} permission for ${memberToAdd} already exists. Skipping...`);
                }
              } else {
                // No binding for this role - create new one
                const newBinding = {
                  role,
                  members: [memberToAdd],
                };
                policy.bindings.push(newBinding);
                logger.info(`Adding ${role} permission binding for ${memberToAdd}...`);
                policyUpdated = true;
              }
            }
          }

          if (!policyUpdated) {
            logger.info('All required permissions already exist.');
            return;
          }

          // Set the updated policy
          await this.iam.projects.serviceAccounts.setIamPolicy({
            resource: `projects/${this.projectId}/serviceAccounts/${tenantServiceAccountEmail}`,
            requestBody: { policy },
          });

          logger.info(
            `Granted required roles on '${tenantServiceAccountEmail}' to control SA and Pub/Sub service agent.`
          );
        } catch (error) {
          logger.error(`Failed to grant actAs permission: ${error}`);
          throw error;
        }
      }
    );
  }

  /**
   * Set up a Pub/Sub topic and subscription for a tenant.
   * @param tenantId - The tenant identifier
   * @param webhookUrl - The HTTPS URL for the webhook endpoint
   */
  async setupPubSubForTenant(tenantId: string, webhookUrl: string): Promise<string> {
    return LogContext.run({ tenant_id: tenantId, operation: 'setup-pubsub' }, async () => {
      if (!tenantId || !webhookUrl) {
        throw new Error('Tenant ID and webhook URL are required');
      }

      const topicName = `tenant-${tenantId}-google-email-webhook`;
      const topicPath = `projects/${this.projectId}/topics/${topicName}`;
      const subscriptionName = `tenant-${tenantId}-google-email-webhook-subscription`;
      const subscriptionPath = `projects/${this.projectId}/subscriptions/${subscriptionName}`;
      const tenantServiceAccountEmail = `tenant-${tenantId}@${this.projectId}.iam.gserviceaccount.com`;

      await this.grantActAsPermission(tenantServiceAccountEmail);

      try {
        await this.pubsub.projects.topics.create({
          name: topicPath,
        });
        logger.info(`Pub/Sub topic '${topicName}' created.`);
      } catch (error) {
        if ((error as { code?: number }).code === 409) {
          logger.info(`Pub/Sub topic '${topicName}' already exists.`);
        } else {
          throw error;
        }
      }

      const pushConfig = {
        pushEndpoint: webhookUrl,
        oidcToken: {
          serviceAccountEmail: tenantServiceAccountEmail,
          // Set audience to the webhook URL for security validation
          // The webhook handler must validate that aud == webhookUrl
          audience: webhookUrl,
        },
      };

      try {
        await this.pubsub.projects.subscriptions.create({
          name: subscriptionPath,
          requestBody: {
            topic: topicPath,
            pushConfig,
            ackDeadlineSeconds: 10,
            expirationPolicy: {}, //this sets it to never expire if there is no activity on the subscription
            retryPolicy: {
              //this prevents from blasting the webhook with messages if it's not available
              minimumBackoff: '10s',
              maximumBackoff: '600s',
            },
          },
        });
        logger.info(
          `Pub/Sub subscription '${subscriptionName}' created with endpoint '${webhookUrl}'.`
        );
      } catch (error) {
        if ((error as { code?: number }).code === 409) {
          logger.info(
            `Pub/Sub subscription '${subscriptionName}' already exists. Checking current push config.`
          );

          try {
            const currentSubscription = await this.pubsub.projects.subscriptions.get({
              subscription: subscriptionPath,
            });

            const currentPushConfig = currentSubscription.data.pushConfig;
            const hasOidcToken = !!currentPushConfig?.oidcToken?.serviceAccountEmail;

            logger.info(`Current subscription config for '${subscriptionName}'`, {
              hasOidcToken,
              currentEndpoint: currentPushConfig?.pushEndpoint,
              currentOidcServiceAccount: currentPushConfig?.oidcToken?.serviceAccountEmail || null,
            });

            if (!hasOidcToken) {
              logger.warn(
                `Subscription '${subscriptionName}' is missing OIDC authentication. Updating push config.`
              );
            }

            await this.pubsub.projects.subscriptions.modifyPushConfig({
              subscription: subscriptionPath,
              requestBody: {
                pushConfig,
              },
            });

            logger.info(
              `Pub/Sub subscription '${subscriptionName}' push config updated with OIDC authentication.`
            );
          } catch (modifyError) {
            logger.error(`Failed to update push config for subscription '${subscriptionName}'`, {
              error: String(modifyError),
            });
            throw modifyError;
          }
        } else {
          throw error;
        }
      }

      const serviceAccountEmail = 'gmail-api-push@system.gserviceaccount.com';
      const binding = {
        role: 'roles/pubsub.publisher',
        members: [`serviceAccount:${serviceAccountEmail}`],
      };

      try {
        const getIamPolicyResponse = await this.pubsub.projects.topics.getIamPolicy({
          resource: topicPath,
        });

        const policy = getIamPolicyResponse.data;

        if (!policy.bindings) {
          policy.bindings = [];
        }

        const memberToAdd = binding.members[0] || '';
        const existingBinding = policy.bindings.find((b) => b.role === binding.role);

        if (existingBinding) {
          // Binding for this role exists - add member if not already present
          if (!existingBinding.members?.includes(memberToAdd)) {
            existingBinding.members = existingBinding.members || [];
            existingBinding.members.push(memberToAdd);
          } else {
            logger.info('IAM binding already exists. Skipping...');
          }
        } else {
          // No binding for this role - create new one
          policy.bindings.push(binding);
        }

        await this.pubsub.projects.topics.setIamPolicy({
          resource: topicPath,
          requestBody: { policy },
        });

        logger.info(
          `Granted 'pubsub.publisher' role to '${serviceAccountEmail}' on topic '${topicName}'.`
        );
      } catch (error) {
        logger.error(`Failed to set IAM policy on topic: ${error}`);
        throw error;
      }

      return topicPath;
    });
  }
}

/**
 * Extract the client_id from a Google service account JSON.
 * Returns the client_id if found, otherwise returns the fallback value.
 *
 * @param serviceAccount - The service account JSON (string, object, or unknown)
 * @param fallback - Fallback value if client_id cannot be extracted
 * @param context - Optional logging context (e.g., { tenant_id: string })
 * @returns The client_id or fallback value
 */
export function extractServiceAccountClientId(
  serviceAccount: unknown,
  fallback: string,
  context?: Record<string, unknown>
): string {
  try {
    if (!serviceAccount) {
      logger.warn('Service account is null or undefined', context);
      return fallback;
    }

    const serviceAccountData =
      typeof serviceAccount === 'string'
        ? JSON.parse(serviceAccount)
        : (serviceAccount as Record<string, unknown>);

    if (
      typeof serviceAccountData === 'object' &&
      serviceAccountData !== null &&
      'client_id' in serviceAccountData &&
      typeof serviceAccountData.client_id === 'string'
    ) {
      return serviceAccountData.client_id;
    }

    logger.warn('Service account does not contain a valid client_id', context);
    return fallback;
  } catch (error) {
    logger.error('Error parsing service account for client_id', error, context);
    return fallback;
  }
}
