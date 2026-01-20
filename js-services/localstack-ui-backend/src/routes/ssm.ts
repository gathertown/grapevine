import { Router, Request, Response } from 'express';
import { ParameterType, Parameter, ParameterMetadata } from '@aws-sdk/client-ssm';
import { LocalStackSSMClient } from '../aws-client.js';
import { SSMParameter, CreateParameterRequest, UpdateParameterRequest } from '../types/index.js';

const router = Router();
const ssmClient = new LocalStackSSMClient();

// Helper function to convert AWS Parameter to our SSMParameter type
function convertParameter(awsParam: Parameter): SSMParameter {
  return {
    name: awsParam.Name || '',
    value: awsParam.Value || '',
    type: (awsParam.Type as 'String' | 'StringList' | 'SecureString') || 'String',
    description: undefined, // Parameter type doesn't include Description
    version: awsParam.Version || 1,
    lastModifiedDate: awsParam.LastModifiedDate
      ? awsParam.LastModifiedDate.toISOString()
      : new Date().toISOString(),
    keyId: undefined, // Parameter type doesn't include KeyId
  };
}

// Helper function to convert AWS ParameterMetadata to our SSMParameter type (for listing)
function convertParameterMetadata(metadata: ParameterMetadata): SSMParameter {
  return {
    name: metadata.Name || '',
    value: '***', // Value not available in metadata, would need separate GetParameter call
    type: (metadata.Type as 'String' | 'StringList' | 'SecureString') || 'String',
    description: metadata.Description,
    version: metadata.Version || 1,
    lastModifiedDate: metadata.LastModifiedDate
      ? metadata.LastModifiedDate.toISOString()
      : new Date().toISOString(),
    keyId: metadata.KeyId,
  };
}

// GET /api/ssm/parameters - List all parameters
router.get('/parameters', async (req: Request, res: Response) => {
  try {
    const prefix = req.query.prefix as string;

    // Get parameters from AWS SSM
    const parameterMetadata = await ssmClient.listParameters(prefix);

    // Convert metadata to our SSMParameter format
    const parameters = parameterMetadata.map(convertParameterMetadata);

    res.json(parameters);
  } catch (error) {
    console.error('Error listing parameters:', error);
    res.status(500).json({ error: 'Failed to list parameters' });
  }
});

// GET /api/ssm/parameters/:name - Get specific parameter
router.get('/parameters/:name', async (req: Request, res: Response) => {
  try {
    const paramName = decodeURIComponent(req.params.name || '');

    // Get from AWS SSM
    const awsParam = await ssmClient.getParameter(paramName);
    if (!awsParam) {
      res.status(404).json({ error: 'Parameter not found' });
      return;
    }

    const parameter = convertParameter(awsParam);
    res.json(parameter);
  } catch (error) {
    console.error('Error getting parameter:', error);
    res.status(500).json({ error: 'Failed to get parameter' });
  }
});

// POST /api/ssm/parameters - Create parameter
router.post('/parameters', async (req: Request, res: Response) => {
  try {
    const { name, value, type, description }: CreateParameterRequest = req.body;

    if (!name || !value) {
      res.status(400).json({ error: 'Name and value are required' });
      return;
    }

    // Convert string type to ParameterType enum
    let paramType: ParameterType;
    switch (type) {
      case 'String':
        paramType = ParameterType.STRING;
        break;
      case 'StringList':
        paramType = ParameterType.STRING_LIST;
        break;
      case 'SecureString':
        paramType = ParameterType.SECURE_STRING;
        break;
      default:
        paramType = ParameterType.STRING;
    }

    // Create in AWS SSM
    const success = await ssmClient.putParameter(name, value, paramType, description, false);

    if (!success) {
      res.status(500).json({ error: 'Failed to create parameter' });
      return;
    }

    // Get the created parameter to return full details
    const awsParam = await ssmClient.getParameter(name);
    if (!awsParam) {
      res.status(500).json({ error: 'Parameter created but could not retrieve details' });
      return;
    }

    const parameter = convertParameter(awsParam);
    res.status(201).json(parameter);
  } catch (error) {
    console.error('Error creating parameter:', error);
    res.status(500).json({ error: 'Failed to create parameter' });
  }
});

// PUT /api/ssm/parameters/:name - Update parameter
router.put('/parameters/:name', async (req: Request, res: Response) => {
  try {
    const paramName = decodeURIComponent(req.params.name || '');
    const { value, description }: UpdateParameterRequest = req.body;

    if (!value) {
      res.status(400).json({ error: 'Value is required' });
      return;
    }

    // Get existing parameter to preserve type
    const existingAwsParam = await ssmClient.getParameter(paramName);
    if (!existingAwsParam) {
      res.status(404).json({ error: 'Parameter not found' });
      return;
    }

    // Convert string type to ParameterType enum
    let paramType: ParameterType;
    switch (existingAwsParam.Type) {
      case 'String':
        paramType = ParameterType.STRING;
        break;
      case 'StringList':
        paramType = ParameterType.STRING_LIST;
        break;
      case 'SecureString':
        paramType = ParameterType.SECURE_STRING;
        break;
      default:
        paramType = ParameterType.STRING;
    }

    // Update in AWS SSM
    const success = await ssmClient.putParameter(paramName, value, paramType, description, true);

    if (!success) {
      res.status(500).json({ error: 'Failed to update parameter' });
      return;
    }

    // Get the updated parameter to return full details
    const updatedAwsParam = await ssmClient.getParameter(paramName);
    if (!updatedAwsParam) {
      res.status(500).json({ error: 'Parameter updated but could not retrieve details' });
      return;
    }

    const parameter = convertParameter(updatedAwsParam);
    res.json(parameter);
  } catch (error) {
    console.error('Error updating parameter:', error);
    res.status(500).json({ error: 'Failed to update parameter' });
  }
});

// DELETE /api/ssm/parameters/:name - Delete parameter
router.delete('/parameters/:name', async (req: Request, res: Response) => {
  try {
    const paramName = decodeURIComponent(req.params.name || '');

    // Delete from AWS SSM
    const success = await ssmClient.deleteParameter(paramName);

    if (!success) {
      res.status(500).json({ error: 'Failed to delete parameter' });
      return;
    }

    res.status(204).send();
  } catch (error) {
    console.error('Error deleting parameter:', error);
    res.status(500).json({ error: 'Failed to delete parameter' });
  }
});

export { router as ssmRouter };
