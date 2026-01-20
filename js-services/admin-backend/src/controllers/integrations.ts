import { Router } from 'express';
import { randomBytes } from 'crypto';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { getSqsClient, isSqsConfigured } from '../jobs/sqs-client.js';
import getFavicon from 'get-website-favicon';
import sharp from 'sharp';
import { logger, LogContext } from '../utils/logger.js';
import { getConfigValue, saveConfigValue } from '../config/index.js';
import { updateIntegrationStatus, trackIntegrationRequested } from '../utils/notion-crm.js';
import { getOrInitializeRedis } from '../redis-client.js';
import { installConnector } from '../dal/connector-utils.js';
import { ConnectorType } from '../types/connector.js';

const integrationsRouter = Router();

/**
 * POST /api/integrations/track-request
 * Track when a user requests/starts setting up an integration
 */
integrationsRouter.post('/track-request', requireAdmin, async (req, res) => {
  return LogContext.run(
    { operation: 'track-integration-request', endpoint: '/integrations/track-request' },
    async () => {
      try {
        const tenantId = req.user?.tenantId;
        if (!tenantId) {
          return res.status(400).json({ error: 'No tenant found for organization' });
        }

        const { integration } = req.body;
        if (!integration) {
          return res.status(400).json({ error: 'Integration type is required' });
        }

        // Track the integration request in Notion CRM
        await trackIntegrationRequested(tenantId, integration);

        res.json({ success: true });
      } catch (error) {
        logger.error('Error tracking integration request', error);
        res.status(500).json({
          error: 'Failed to track integration request',
          details: process.env.NODE_ENV === 'development' ? error.message : undefined,
        });
      }
    }
  );
});

// Helper function to fetch company logo/favicon
async function fetchCompanyLogo(domain: string): Promise<{ blob: Blob; url: string } | null> {
  return LogContext.run({ domain, operation: 'fetch-company-logo' }, async () => {
    logger.info(`Attempting to fetch logo for domain: ${domain}`);

    try {
      // Use get-website-favicon library to find favicon
      const faviconResult = await getFavicon(`https://${domain}`);

      if (faviconResult) {
        logger.info(`✅ Found favicon URL: ${faviconResult.url}`, {
          faviconUrl: faviconResult.url,
        });

        // Fetch the actual favicon
        const response = await fetch(faviconResult.url);
        if (response.ok) {
          logger.info(`✅ Successfully downloaded favicon from: ${faviconResult.url}`, {
            logoSize: response.headers.get('content-length'),
            contentType: response.headers.get('content-type'),
          });

          // Convert to PNG with transparency for OpenAI requirements
          const originalBuffer = await response.arrayBuffer();
          const pngBuffer = await sharp(Buffer.from(originalBuffer))
            .png()
            .resize(1024, 1024, {
              fit: 'contain',
              background: { r: 0, g: 0, b: 0, alpha: 0 }, // transparent background
            })
            .toBuffer();

          logger.info(`✅ Converted to PNG with transparency: ${pngBuffer.length} bytes`, {
            pngSize: pngBuffer.length,
          });
          return {
            blob: new Blob([new Uint8Array(pngBuffer)], { type: 'image/png' }),
            url: faviconResult.url,
          };
        } else {
          logger.warn(`❌ Failed to download favicon: ${response.status} ${response.statusText}`, {
            status: response.status,
          });
        }
      }
    } catch (e) {
      logger.error(`❌ Error fetching favicon with library`, e);
    }

    // Fallback to favicon services
    // Clean domain for services that don't want protocols
    const cleanDomain = domain.replace(/^https?:\/\//, '');

    const fallbackServices = [
      `https://icon.horse/icon/${cleanDomain}`,
      `https://favicons.githubusercontent.com/${cleanDomain}`,
      `https://www.google.com/s2/favicons?domain=${cleanDomain}&sz=256`,
    ];

    for (const serviceUrl of fallbackServices) {
      try {
        logger.info(`Trying fallback service: ${serviceUrl}`, { serviceUrl });
        const response = await fetch(serviceUrl);
        if (response.ok && response.headers.get('content-type')?.includes('image')) {
          logger.info(`✅ Successfully found logo from service: ${serviceUrl}`, {
            serviceUrl,
            logoSize: response.headers.get('content-length'),
            contentType: response.headers.get('content-type'),
          });

          // Convert to PNG with transparency for OpenAI requirements
          const originalBuffer = await response.arrayBuffer();
          const pngBuffer = await sharp(Buffer.from(originalBuffer))
            .png()
            .resize(1024, 1024, {
              fit: 'contain',
              background: { r: 0, g: 0, b: 0, alpha: 0 }, // transparent background
            })
            .toBuffer();

          logger.info(
            `✅ Converted fallback service image to PNG with transparency: ${pngBuffer.length} bytes`,
            { pngSize: pngBuffer.length }
          );
          return {
            blob: new Blob([new Uint8Array(pngBuffer)], { type: 'image/png' }),
            url: serviceUrl,
          };
        } else {
          logger.warn(`❌ Service failed: ${serviceUrl} - ${response.status}`, {
            serviceUrl,
            status: response.status,
          });
        }
      } catch (e) {
        logger.error(`❌ Error with service ${serviceUrl}`, e, { serviceUrl });
        continue;
      }
    }

    logger.warn(`❌ No logo found for domain: ${domain} after trying all methods`);
    return null;
  });
}

// Icon generation endpoint
integrationsRouter.post('/generate-icon', requireAdmin, async (req, res) => {
  return LogContext.run(
    { operation: 'generate-icon', endpoint: '/integrations/generate-icon' },
    async () => {
      try {
        const { domain, prompt } = req.body;

        // Basic validation
        if (!domain || !prompt) {
          return res.status(400).json({
            error: 'Domain and prompt are required',
          });
        }

        // Get tenant ID from authenticated user
        const tenantId = req.user?.tenantId;
        if (!tenantId) {
          return res.status(400).json({
            error: 'No tenant found for organization',
          });
        }

        // Check if OpenAI API key is configured in environment
        const openaiApiKey = process.env.OPENAI_API_KEY;
        if (!openaiApiKey) {
          return res.status(500).json({
            error: 'OpenAI API key not configured in environment',
          });
        }

        // Try to fetch the company's logo
        const logoResult = await fetchCompanyLogo(domain);

        if (logoResult) {
          logger.info('Using company logo to generate app icon with OpenAI gpt-4.1', {
            logoUrl: logoResult.url,
            domain,
          });

          try {
            // Convert blob to base64 for OpenAI API
            const buffer = await logoResult.blob.arrayBuffer();
            const base64Image = Buffer.from(buffer).toString('base64');

            // Use OpenAI's gpt-4.1 for image generation with reference
            const response = await fetch('https://api.openai.com/v1/responses', {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${openaiApiKey}`,
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                model: 'gpt-4.1',
                input: [
                  {
                    role: 'user',
                    content: [
                      {
                        type: 'input_text',
                        text: `We are taking in a company's logo and transforming it into a new icon. Let's make sure to keep the visual detail of the original logo as much as possible, keeping it large and prominent, while being liberally about changing its background. ${prompt}.`,
                      },
                      {
                        type: 'input_image',
                        image_url: `data:image/png;base64,${base64Image}`,
                      },
                    ],
                  },
                ],
                tools: [{ type: 'image_generation' }],
              }),
            });

            if (response.ok) {
              const data = (await response.json()) as {
                output?: Array<{
                  type: string;
                  result: string;
                }>;
              };
              logger.debug('OpenAI response received', { responseData: data });

              // Extract image data from response
              const imageData = data.output
                ?.filter((output) => output.type === 'image_generation_call')
                ?.map((output) => output.result);

              if (imageData && imageData.length > 0) {
                const imageBase64 = imageData[0];

                // Convert base64 to data URL for frontend
                const iconUrl = `data:image/png;base64,${imageBase64}`;

                logger.info(
                  `✅ Icon generated successfully with OpenAI gpt-4.1 for ${domain} using logo from ${logoResult.url}`,
                  { domain, logoUrl: logoResult.url }
                );

                return res.json({
                  success: true,
                  iconUrl,
                  originalIconUrl: logoResult.url,
                  message: `Icon generated from company logo using OpenAI gpt-4.1 (${logoResult.url})`,
                });
              } else {
                logger.warn('No image data found in OpenAI response');
                return res.status(500).json({
                  error: 'OpenAI did not generate an image. Please try again.',
                });
              }
            } else {
              const errorData = await response.text();
              logger.error('OpenAI API request failed', {
                status: response.status,
                statusText: response.statusText,
                errorDetails: errorData,
              });

              return res.status(500).json({
                error: 'Failed to generate icon with OpenAI. Please try again.',
              });
            }
          } catch (openaiError) {
            logger.error('OpenAI processing error', openaiError);

            return res.status(500).json({
              error: 'Error connecting to OpenAI. Please try again.',
            });
          }
        } else {
          logger.warn('No logo found for domain', { domain });
          return res.status(404).json({
            error: `Could not find a logo for ${domain}. Please ensure the domain is correct and the website has a favicon.`,
          });
        }
      } catch (error) {
        logger.error('Error generating icon', error, { domain: req.body?.domain });
        res.status(500).json({
          error: 'Internal server error. Please try again.',
        });
      }
    }
  );
});

// Notion setup initialization endpoint - generates nonce for secure webhook verification token storage
integrationsRouter.post('/notion/init-setup', requireAdmin, async (req, res) => {
  return LogContext.run(
    { operation: 'notion-init-setup', endpoint: '/notion/init-setup' },
    async () => {
      try {
        // Get tenant ID from authenticated user
        const tenantId = req.user?.tenantId;
        if (!tenantId) {
          return res.status(400).json({
            error: 'No tenant found for organization',
          });
        }

        // Get Redis client
        const redisClient = getOrInitializeRedis();
        if (!redisClient) {
          logger.error('Redis not configured - cannot initialize Notion setup');
          return res.status(500).json({
            error: 'Redis not configured - missing REDIS_PRIMARY_ENDPOINT',
          });
        }

        // Generate cryptographically secure random nonce (32 bytes = 64 hex chars)
        const nonce = randomBytes(32).toString('hex');

        // Store nonce in Redis with 2 week TTL
        const timestamp = new Date().toISOString();
        const redisKey = `notion:setup:nonce:${nonce}`;
        const redisValue = `${tenantId}:${timestamp}`;
        const ttlSeconds = 14 * 24 * 60 * 60; // 2 weeks

        await redisClient.setex(redisKey, ttlSeconds, redisValue);

        logger.info(`Generated Notion setup nonce for tenant ${tenantId}`, {
          tenant_id: tenantId,
          nonce: `${nonce.substring(0, 8)}...`, // Log partial nonce for debugging
          expiresIn: '2 weeks',
        });

        // Calculate expiry timestamp
        const expiresAt = new Date(Date.now() + ttlSeconds * 1000).toISOString();

        res.json({
          success: true,
          nonce,
          expiresAt,
          message: 'Notion setup nonce generated successfully',
        });
      } catch (error) {
        logger.error('Error generating Notion setup nonce', error);

        res.status(500).json({
          error: 'Failed to generate setup nonce',
          details: process.env.NODE_ENV === 'development' ? error.message : undefined,
        });
      }
    }
  );
});

// Notion API ingest job endpoint
integrationsRouter.post('/notion/start-ingest', requireAdmin, async (req, res) => {
  return LogContext.run(
    { operation: 'notion-start-ingest', endpoint: '/notion/start-ingest' },
    async () => {
      try {
        // Get tenant ID from authenticated user
        const tenantId = req.user?.tenantId;
        if (!tenantId) {
          return res.status(400).json({
            error: 'No tenant found for organization',
          });
        }

        // Check if SQS is configured
        if (!isSqsConfigured()) {
          logger.error('SQS not configured - Notion ingest cannot be started');
          return res.status(500).json({
            error: 'SQS not configured - missing AWS credentials or region',
          });
        }

        const sqsClient = getSqsClient();

        logger.info(`Sending Notion API ingest job to SQS queue for tenant ${tenantId}`, {
          tenant_id: tenantId,
        });

        // Send the Notion API ingest job to SQS
        await sqsClient.sendNotionApiIngestJob(tenantId);

        logger.info('Notion API ingest job queued successfully', { tenant_id: tenantId });

        // Mark Notion setup as complete
        await saveConfigValue('NOTION_COMPLETE', 'true', tenantId);
        logger.info('Marked Notion setup as complete', { tenant_id: tenantId });

        // Fetch the Notion bot user ID to use as external ID
        const notionToken = await getConfigValue('NOTION_TOKEN', tenantId);
        if (!notionToken) {
          throw new Error('Notion token not found');
        }

        const response = await fetch('https://api.notion.com/v1/users/me', {
          headers: {
            Authorization: `Bearer ${notionToken}`,
            'Notion-Version': '2022-06-28',
          },
        });

        if (!response.ok) {
          throw new Error(
            `Failed to fetch Notion bot user: ${response.status} ${response.statusText}`
          );
        }

        const data = (await response.json()) as { id?: string };
        if (!data.id) {
          throw new Error('Notion bot user ID not found in response');
        }

        const botUserId = data.id;
        logger.info('Retrieved Notion bot user ID', {
          tenant_id: tenantId,
          bot_user_id: botUserId,
        });

        await installConnector({
          tenantId,
          type: ConnectorType.Notion,
          externalId: botUserId,
        });

        // Update Notion CRM - Notion integration connected
        await updateIntegrationStatus(tenantId, 'notion', true);

        // Generate a simple job reference for tracking
        const jobRef = `notion-api-ingest-${tenantId}-${Date.now()}`;

        res.json({
          success: true,
          message: 'Notion API ingest job has been queued successfully.',
          jobId: jobRef,
          jobStatus: 'queued',
        });
      } catch (sqsError) {
        logger.error('Error sending Notion ingest job to SQS', sqsError);

        res.status(500).json({
          error: `Failed to queue Notion ingest job: ${sqsError.message}`,
        });
      }
    }
  );
});

export { integrationsRouter };
