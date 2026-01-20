/**
 * Mailgun Client Configuration
 * Handles Mailgun SDK initialization for sending emails
 *
 * NOTE: Mailgun is optional. Without it configured, invitation emails cannot be sent.
 * Set MAILGUN_API_KEY and MAILGUN_DOMAIN environment variables to enable email sending.
 */

import Mailgun from 'mailgun.js';
import formData from 'form-data';

let mailgun: ReturnType<Mailgun['client']> | null = null;

// Initialize Mailgun client if API key is available
if (process.env.MAILGUN_API_KEY && process.env.MAILGUN_DOMAIN) {
  try {
    const mg = new Mailgun(formData);
    mailgun = mg.client({
      username: 'api',
      key: process.env.MAILGUN_API_KEY,
    });
    console.log('✅ Mailgun initialized successfully');
  } catch (error) {
    console.error('❌ Failed to initialize Mailgun:', error);
  }
} else {
  console.warn(
    '⚠️  Mailgun not configured - email invitations will be disabled.\n' +
      '   To enable email invitations, set MAILGUN_API_KEY and MAILGUN_DOMAIN environment variables.'
  );
}

/**
 * Check if Mailgun is properly configured and ready to send emails.
 * Returns true if both MAILGUN_API_KEY and MAILGUN_DOMAIN are set and client initialized.
 */
function isMailgunConfigured(): boolean {
  return mailgun !== null && !!process.env.MAILGUN_DOMAIN;
}

/**
 * Get the Mailgun client instance
 */
function getMailgunClient(): ReturnType<Mailgun['client']> | null {
  return mailgun;
}

/**
 * Send an email using Mailgun template.
 * Throws an error if Mailgun is not configured.
 */
async function sendTemplateEmail(
  to: string,
  templateName: string,
  templateVariables: Record<string, string>
): Promise<void> {
  const domain = process.env.MAILGUN_DOMAIN;
  if (!mailgun || !domain) {
    throw new Error(
      'Email sending is disabled. Mailgun is not configured. ' +
        'To enable email invitations, set MAILGUN_API_KEY and MAILGUN_DOMAIN environment variables.'
    );
  }

  const fromEmail = process.env.MAILGUN_FROM_EMAIL || `noreply@${domain}`;

  try {
    const result = await mailgun.messages.create(domain, {
      from: fromEmail,
      to,
      template: templateName,
      'h:X-Mailgun-Variables': JSON.stringify(templateVariables),
    });

    console.log('Email sent successfully:', result.id);
  } catch (error) {
    console.error('Failed to send email:', error);
    throw new Error('Failed to send invitation email');
  }
}

export { mailgun, getMailgunClient, isMailgunConfigured, sendTemplateEmail };
