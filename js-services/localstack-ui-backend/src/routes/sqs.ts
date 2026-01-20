import { Router } from 'express';
import { LocalStackSQSClient } from '../aws-client.js';

const router = Router();
const sqsClient = new LocalStackSQSClient();

// List all queues
router.get('/queues', async (_req, res) => {
  try {
    const queues = await sqsClient.listQueues();
    return res.json(queues);
  } catch (error) {
    console.error('Error listing queues:', error);
    return res.status(500).json({ error: 'Failed to list queues' });
  }
});

// Get queue attributes
router.get('/queues/:queueUrl/attributes', async (req, res) => {
  try {
    const queueUrl = decodeURIComponent(req.params.queueUrl);
    const queue = await sqsClient.getQueueAttributes(queueUrl);

    if (!queue) {
      return res.status(404).json({ error: 'Queue not found' });
    }

    return res.json(queue);
  } catch (error) {
    console.error('Error getting queue attributes:', error);
    return res.status(500).json({ error: 'Failed to get queue attributes' });
  }
});

// Purge queue
router.post('/queues/:queueUrl/purge', async (req, res) => {
  try {
    const queueUrl = decodeURIComponent(req.params.queueUrl);
    const success = await sqsClient.purgeQueue(queueUrl);

    if (!success) {
      return res.status(500).json({ error: 'Failed to purge queue' });
    }

    return res.json({ message: 'Queue purged successfully' });
  } catch (error) {
    console.error('Error purging queue:', error);
    return res.status(500).json({ error: 'Failed to purge queue' });
  }
});

// Get messages from queue
router.get('/queues/:queueUrl/messages', async (req, res) => {
  try {
    const queueUrl = decodeURIComponent(req.params.queueUrl);
    const maxMessages = parseInt(req.query.maxMessages as string) || 10;

    const messages = await sqsClient.receiveMessages(queueUrl, maxMessages);

    // Transform messages to match frontend interface
    const transformedMessages = messages.map((msg) => ({
      messageId: msg.MessageId || '',
      receiptHandle: msg.ReceiptHandle || '',
      body: msg.Body || '',
      attributes: msg.Attributes,
      messageAttributes: msg.MessageAttributes,
    }));

    return res.json(transformedMessages);
  } catch (error) {
    console.error('Error getting messages:', error);
    return res.status(500).json({ error: 'Failed to get messages' });
  }
});

// Delete message
router.delete('/queues/:queueUrl/messages/:receiptHandle', async (req, res) => {
  try {
    const queueUrl = decodeURIComponent(req.params.queueUrl);
    const receiptHandle = decodeURIComponent(req.params.receiptHandle);

    const success = await sqsClient.deleteMessage(queueUrl, receiptHandle);

    if (!success) {
      return res.status(500).json({ error: 'Failed to delete message' });
    }

    return res.json({ message: 'Message deleted successfully' });
  } catch (error) {
    console.error('Error deleting message:', error);
    return res.status(500).json({ error: 'Failed to delete message' });
  }
});

// Send message
router.post('/queues/:queueUrl/messages', async (req, res) => {
  try {
    const queueUrl = decodeURIComponent(req.params.queueUrl);
    const { messageBody, messageAttributes, messageGroupId, messageDeduplicationId } = req.body;

    if (!messageBody) {
      return res.status(400).json({ error: 'messageBody is required' });
    }

    // Only require messageGroupId for FIFO queues
    const isFifoQueue = queueUrl.endsWith('.fifo');
    if (isFifoQueue && !messageGroupId) {
      return res.status(400).json({ error: 'messageGroupId is required for FIFO queues' });
    }

    const success = await sqsClient.sendMessage(
      queueUrl,
      messageBody,
      messageGroupId,
      messageAttributes,
      messageDeduplicationId
    );

    if (!success) {
      return res.status(500).json({ error: 'Failed to send message' });
    }

    return res.json({ message: 'Message sent successfully' });
  } catch (error) {
    console.error('Error sending message:', error);
    return res.status(500).json({ error: 'Failed to send message' });
  }
});

export { router as sqsRouter };
