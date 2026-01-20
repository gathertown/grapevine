import express from 'express';
import cors from 'cors';
import { ssmRouter } from './routes/ssm.js';
import { sqsRouter } from './routes/sqs.js';

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());

// Health check
app.get('/health', (_req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Routes
app.use('/api/ssm', ssmRouter);
app.use('/api/sqs', sqsRouter);

// Error handling middleware
app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error('Error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

// 404 handler
app.use('*', (_req, res) => {
  res.status(404).json({ error: 'Not found' });
});

app.listen(PORT, () => {
  console.log(`LocalStack UI Backend running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});
